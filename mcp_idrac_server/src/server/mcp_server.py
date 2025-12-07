# Licensed to You under the Apache License, Version 2.0

"""Main MCP server implementation for Redfish API tools."""

import os
from typing import Dict, Any, Optional
from pathlib import Path

from fastmcp import FastMCP

from ..parsers.openapi_parser import OpenApiParser
from ..parsers.tool_config_parser import ToolConfigParser
from ..parsers.workflow_parser import WorkflowParser
from ..clients.redfish_client import RedfishClient, RedfishAPIError
from ..auth.authentication import AuthenticationFactory
from ..generators.tool_generator import ToolGenerator
from ..generators.workflow_executor import WorkflowExecutor
from ..models.tool_definition import ToolDefinition


class RedfishMCPServer:
    """
    MCP server for Dell iDRAC Redfish API management.

    This server dynamically creates and registers MCP tools based on
    OpenAPI specifications and tool configuration files.
    """

    def __init__(
        self,
        openapi_file: str,
        tools_config_file: str,
        workflows_config_file: Optional[str] = None,
        server_name: str = "idrac-redfish-server",
    ):
        """
        Initialize the Redfish MCP server.

        Args:
            openapi_file: Path to OpenAPI specification file
            tools_config_file: Path to tools configuration YAML
            workflows_config_file: Path to workflows configuration YAML (optional)
            server_name: Name of the MCP server
        """
        self.openapi_file = openapi_file
        self.tools_config_file = tools_config_file
        self.workflows_config_file = workflows_config_file
        self.server_name = server_name

        # Initialize FastMCP server
        self.mcp = FastMCP(server_name)

        # Parse configurations
        self.openapi_parser = OpenApiParser(openapi_file)
        self.config_parser = ToolConfigParser(tools_config_file)

        # Get configuration
        self.config = self.config_parser.get_config()

        # Validate tool definitions against OpenAPI spec
        self._validate_tools()

        # Set up authentication handlers
        # We support both basic auth (username+password) and token auth (auth_token)
        # The Redfish client auto-selects the handler based on provided credentials
        auth_config = self.config.authentication
        self.basic_auth_handler = AuthenticationFactory.create_handler(auth_method="basic")
        self.token_auth_handler = AuthenticationFactory.create_handler(
            auth_method="token",
            token_header=auth_config.token_header,
        )

        # Set up Redfish client (base_url is now provided per-request via idrac_ip parameter)
        # Pass both auth handlers - client selects based on credentials.token presence
        self.redfish_client = RedfishClient(
            basic_auth_handler=self.basic_auth_handler,
            token_auth_handler=self.token_auth_handler,
            verify_ssl=self.config.server.verify_ssl,
            timeout=self.config.server.timeout,
            max_retries=self.config.server.max_retries,
        )

        # Initialize tool generator
        self.tool_generator = ToolGenerator(self.redfish_client)

        # Tool registry for workflow executor (maps tool name -> function)
        self.tool_registry: Dict[str, Any] = {}

        # Register tools
        self._register_tools()

        # Parse and register workflows (if config provided)
        if self.workflows_config_file:
            self.workflow_parser = WorkflowParser(self.workflows_config_file)
            self._validate_workflows()
            self.workflow_executor = WorkflowExecutor(self.tool_registry)
            self._register_workflows()
        else:
            self.workflow_parser = None
            self.workflow_executor = None

    def _validate_tools(self) -> None:
        """Validate that all configured tools reference valid API operations."""
        operation_ids = self.openapi_parser.list_operation_ids()
        valid_tools, invalid_tools = self.config_parser.validate_against_openapi(
            operation_ids
        )

        if invalid_tools:
            print(f"Warning: The following tools reference invalid operation IDs:")
            for tool_name in invalid_tools:
                tool = self.config.get_tool_by_name(tool_name)
                if tool:
                    print(f"  - {tool_name}: {tool.operation_id}")

    def _register_tools(self) -> None:
        """Register all enabled tools with the MCP server."""
        enabled_tools = self.config.get_enabled_tools()

        for tool_def in enabled_tools:
            # Get the corresponding API operation
            api_operation = self.openapi_parser.get_operation(tool_def.operation_id)

            if not api_operation:
                print(
                    f"Warning: Skipping tool '{tool_def.name}' - "
                    f"operation '{tool_def.operation_id}' not found"
                )
                continue

            # Generate the tool function
            tool_func = self.tool_generator.generate_tool(tool_def, api_operation)

            # Generate tool schema
            tool_schema = self.tool_generator.generate_tool_schema(
                tool_def, api_operation
            )

            # Register the tool with FastMCP
            self.mcp.tool(
                name=tool_schema["name"],
                description=tool_schema["description"],
            )(tool_func)

            # Add to tool registry for workflow executor
            self.tool_registry[tool_def.name] = tool_func

            # Verify the tool is callable (debug check)
            if not callable(tool_func):
                print(f"ERROR: Tool '{tool_def.name}' is not callable (type: {type(tool_func).__name__})")

            print(f"Registered tool: {tool_def.name}")

    def _validate_workflows(self) -> None:
        """Validate that all workflows reference valid tools."""
        if not self.workflow_parser:
            return

        available_tools = [tool.name for tool in self.config.tools]
        valid_workflows, invalid_workflows = self.workflow_parser.validate_against_tools(
            available_tools
        )

        if invalid_workflows:
            print(f"Warning: {len(invalid_workflows)} workflow(s) reference invalid tools")

    def _register_workflows(self) -> None:
        """Register all enabled workflows as MCP tools."""
        if not self.workflow_parser or not self.workflow_executor:
            return

        enabled_workflows = self.workflow_parser.get_enabled_workflows()

        for workflow in enabled_workflows:
            # Create a wrapper function for this workflow
            workflow_func = self._create_workflow_function(workflow)

            # Generate explicit schema (same pattern as regular tools)
            workflow_schema = self._generate_workflow_schema(workflow)

            # Register with FastMCP - use same pattern as regular tools
            # The schema is embedded in the function signature via annotations,
            # but we also generate the explicit schema for reference
            self.mcp.tool(
                name=workflow_schema["name"],
                description=workflow_schema["description"],
            )(workflow_func)

            print(f"Registered workflow: {workflow.name} ({len(workflow.steps)} steps)")

    def _generate_workflow_schema(self, workflow) -> Dict[str, Any]:
        """
        Generate MCP tool schema for a workflow.

        This ensures workflows have the same schema structure as regular tools,
        making them fully compatible with MCP protocol and HTTP transport.

        Args:
            workflow: WorkflowDefinition

        Returns:
            Tool schema dictionary with inputSchema compatible with MCP protocol
        """
        # Build parameters schema following MCP protocol format
        parameters = {
            "type": "object",
            "properties": {},
            "required": [],
        }

        # Add mandatory idrac_ip parameter (same as regular tools)
        parameters["properties"]["idrac_ip"] = {
            "type": "string",
            "description": "iDRAC IP address or hostname. Protocol prefix (https://) is optional.",
        }
        parameters["required"].append("idrac_ip")

        # Add optional authentication parameters (same as regular tools)
        # Either (username + password) OR auth_token must be provided
        parameters["properties"]["username"] = {
            "type": "string",
            "description": "iDRAC username for Basic Authentication (required with password)",
        }
        parameters["properties"]["password"] = {
            "type": "string",
            "description": "iDRAC password for Basic Authentication (required with username)",
        }
        parameters["properties"]["auth_token"] = {
            "type": "string",
            "description": "iDRAC auth token for Token Authentication (alternative to username/password)",
        }

        # Add workflow-specific input parameters
        for input_def in workflow.inputs:
            param_schema = {
                "type": input_def.type if hasattr(input_def, 'type') and input_def.type else "string",
                "description": input_def.description,
            }

            # Add default value if specified
            if input_def.default is not None:
                param_schema["default"] = input_def.default

            parameters["properties"][input_def.name] = param_schema

            # Add to required list if parameter is required
            if input_def.required:
                parameters["required"].append(input_def.name)

        return {
            "name": workflow.name,
            "description": f"[WORKFLOW] {workflow.description}",
            "inputSchema": parameters,
        }

    def _create_workflow_function(self, workflow):
        """
        Create a callable function for a workflow.

        Args:
            workflow: WorkflowDefinition

        Returns:
            Callable function with proper signature
        """
        import inspect
        from typing import Annotated

        # Build parameter list for function signature
        required_params = [
            inspect.Parameter(
                'idrac_ip',
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=Annotated[str, "iDRAC IP address or hostname"]
            ),
        ]

        optional_params = [
            inspect.Parameter(
                'username',
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=Annotated[Optional[str], "iDRAC username for Basic Auth"],
                default=None
            ),
            inspect.Parameter(
                'password',
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=Annotated[Optional[str], "iDRAC password for Basic Auth"],
                default=None
            ),
            inspect.Parameter(
                'auth_token',
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=Annotated[Optional[str], "iDRAC auth token for Token Auth"],
                default=None
            ),
        ]

        # Add workflow-specific input parameters
        for input_def in workflow.inputs:
            if input_def.required:
                required_params.append(
                    inspect.Parameter(
                        input_def.name,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        annotation=Annotated[str, input_def.description],
                        default=inspect.Parameter.empty
                    )
                )
            else:
                optional_params.append(
                    inspect.Parameter(
                        input_def.name,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        annotation=Annotated[Optional[str], input_def.description],
                        default=input_def.default
                    )
                )

        # Combine parameters
        params = required_params + optional_params
        sig = inspect.Signature(params, return_annotation=Dict[str, Any])

        # Create the workflow function
        def workflow_function(*args, **kwargs):
            """Execute workflow."""
            # Bind arguments
            try:
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                arguments = dict(bound.arguments)
            except TypeError as e:
                raise ValueError(f"Invalid workflow arguments: {e}")

            # Extract credentials with proper error handling
            idrac_ip = arguments.pop('idrac_ip', None)
            if not idrac_ip:
                raise ValueError(
                    "Missing required parameter 'idrac_ip'. "
                    f"Received arguments: {list(arguments.keys())}"
                )

            username = arguments.pop('username', None)
            password = arguments.pop('password', None)
            auth_token = arguments.pop('auth_token', None)

            # Remaining arguments are workflow inputs
            workflow_inputs = arguments

            # Execute workflow
            result = self.workflow_executor.execute(
                workflow=workflow,
                idrac_ip=idrac_ip,
                username=username,
                password=password,
                auth_token=auth_token,
                **workflow_inputs
            )

            if not result.success:
                raise RuntimeError(f"Workflow execution failed: {result.error}")

            return result.output

        # Set function metadata (same pattern as regular tools)
        workflow_function.__name__ = workflow.name
        workflow_function.__doc__ = workflow.description
        workflow_function.__signature__ = sig

        # Set annotations for FastMCP introspection (critical for HTTP transport!)
        workflow_function.__annotations__ = {
            param.name: param.annotation for param in params
        }
        workflow_function.__annotations__['return'] = Dict[str, Any]

        return workflow_function

    def run(self, transport: str = "streamable-http", host: str = "0.0.0.0", port: int = 8000) -> None:
        """
        Run the MCP server.

        Args:
            transport: Transport type - "streamable-http" (default) or "stdio"
            host: Host to bind for streamable-http transport
            port: Port to bind for streamable-http transport
        """
        print(f"Starting {self.server_name}...")
        print(f"Loaded {len(self.config.get_enabled_tools())} tools")
        if self.workflow_parser:
            workflow_count = len(self.workflow_parser.get_enabled_workflows())
            print(f"Loaded {workflow_count} workflows")
        print(f"Transport: {transport}")

        try:
            if transport == "streamable-http":
                print(f"Streamable HTTP Server: http://{host}:{port}/mcp")
                print(f"Using Streamable HTTP for streaming responses (modern SSE replacement)")
                print(f"\n[INFO] Press Ctrl+C to stop the server\n")
                self.mcp.run(transport="http", host=host, port=port)
            elif transport == "stdio":
                print(f"Using STDIO transport (local process communication)")
                print(f"\n[INFO] Press Ctrl+C to stop the server\n")
                self.mcp.run()
            else:
                raise ValueError(
                    f"Unsupported transport: {transport}. "
                    f"Use 'streamable-http' or 'stdio'"
                )
        except KeyboardInterrupt:
            # Gracefully handle Ctrl+C
            self.shutdown()
            raise
        except Exception as e:
            print(f"\n[ERROR] Server error: {e}")
            self.shutdown()
            raise

    def shutdown(self) -> None:
        """
        Perform graceful shutdown of the server.

        This method can be extended to close connections, save state, etc.
        """
        print("\n[CLEANUP] Cleaning up resources...")
        # Close any open connections or resources here
        # For example, if we had persistent connections:
        # if self.redfish_client:
        #     self.redfish_client.close()
        print("[SUCCESS] Cleanup complete")

    def get_mcp_instance(self) -> FastMCP:
        """
        Get the FastMCP instance.

        Returns:
            The FastMCP server instance
        """
        return self.mcp


def create_server(
    openapi_file: Optional[str] = None,
    tools_config_file: Optional[str] = None,
    workflows_config_file: Optional[str] = None,
) -> RedfishMCPServer:
    """
    Factory function to create a Redfish MCP server.

    Args:
        openapi_file: Path to OpenAPI spec (defaults to config/openapi.yaml)
        tools_config_file: Path to tools config (defaults to config/tools.yaml)
        workflows_config_file: Path to workflows config (optional, defaults to config/workflows.yaml if exists)

    Returns:
        Configured RedfishMCPServer instance
    """
    # Default paths
    if not openapi_file:
        openapi_file = os.getenv("OPENAPI_FILE", "config/openapi.yaml")

    if not tools_config_file:
        tools_config_file = os.getenv("TOOLS_CONFIG_FILE", "config/tools.yaml")

    if not workflows_config_file:
        workflows_config_file = os.getenv("WORKFLOWS_CONFIG_FILE", "config/workflows.yaml")

    return RedfishMCPServer(
        openapi_file=openapi_file,
        tools_config_file=tools_config_file,
        workflows_config_file=workflows_config_file,
    )
