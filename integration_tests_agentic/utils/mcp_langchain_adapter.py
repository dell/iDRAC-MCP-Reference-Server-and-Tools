# Licensed to You under the Apache License, Version 2.0

"""
MCP to LangChain Adapter

This module converts MCP server tools into LangChain-compatible tools,
enabling them to be used with LangChain agents (ReAct, OpenAI Functions, etc.)

Uses MCP client to communicate with a running MCP server (not embedded).
"""

import logging
import threading
from typing import List, Dict, Any, Type, Optional
from pydantic import BaseModel, Field, create_model
from langchain_core.tools import StructuredTool, ToolException

from .mcp_client import MCPClient
from .credential_manager import CredentialDatabase

logger = logging.getLogger(__name__)

class MCPToolWrapper:
    """Wraps an MCP tool for use with LangChain."""

    def __init__(
        self,
        mcp_client: MCPClient,
        tool_def: Dict[str, Any],
        credential_db: Optional[CredentialDatabase] = None,
        default_credentials: Optional[Dict[str, str]] = None
    ):
        """
        Initialize MCP tool wrapper.

        Args:
            mcp_client: MCP client instance (used to get base_url and timeout)
            tool_def: Tool definition from MCP server
            credential_db: Credential database for dynamic lookup (optional)
            default_credentials: Default credentials if no credential_db or system_id (optional)
        """
        # Store connection info for thread-local client creation
        self.mcp_base_url = mcp_client.base_url
        self.mcp_timeout = mcp_client.timeout
        self.tool_def = tool_def
        self.credential_db = credential_db
        self.default_credentials = default_credentials or {}
        self.tool_name = tool_def.get("name", "unknown")

    def execute(self, *args, **kwargs) -> str:
        """
        Execute the MCP tool (synchronous wrapper for async execution).

        Handles both positional (Pydantic model) and keyword arguments.

        Returns:
            String representation of the result (LangChain expects string)
        """
        import asyncio

        # Debug: log what we received
        logger.debug(f"Tool '{self.tool_name}' called with args={args}, kwargs={kwargs}")

        try:
            # Handle Pydantic model passed as positional argument
            if args:
                if len(args) == 1:
                    arg = args[0]

                    # Convert Pydantic model to dict
                    if hasattr(arg, 'model_dump'):  # Pydantic V2
                        kwargs = arg.model_dump(exclude_none=True)
                    elif hasattr(arg, 'dict'):  # Pydantic V1
                        kwargs = arg.dict(exclude_none=True)
                    elif isinstance(arg, dict):
                        kwargs = arg
                    elif isinstance(arg, str):
                        # Handle string input - try to parse as Python literal
                        # Agent might output: "system_id = 'System.Embedded.1'"
                        import ast
                        import re

                        logger.debug(f"Parsing string input: {arg}")

                        # Try to parse as JSON first
                        try:
                            import json
                            kwargs = json.loads(arg)
                        except (json.JSONDecodeError, ValueError):
                            # Try to parse Python assignment syntax: key = 'value'
                            try:
                                # Extract key=value pairs
                                # Match patterns like: system_id = 'System.Embedded.1'
                                matches = re.findall(r'(\w+)\s*=\s*(["\']?)([^"\']+)\2', arg)
                                if matches:
                                    kwargs = {key: value for key, _, value in matches}
                                    logger.debug(f"Parsed assignment syntax: {kwargs}")
                                else:
                                    # Try to evaluate as Python literal
                                    parsed = ast.literal_eval(arg)
                                    if isinstance(parsed, dict):
                                        kwargs = parsed
                                    else:
                                        logger.warning(f"Could not parse string input: {arg}")
                                        kwargs = {}
                            except (ValueError, SyntaxError) as e:
                                logger.warning(f"Failed to parse string input '{arg}': {e}")
                                kwargs = {}

            # Log what was extracted from arguments
            logger.debug(f"Extracted kwargs: {kwargs}")

            # Look up credentials from database if target_system_id is provided
            target_system_id = kwargs.get("target_system_id")

            # Check if we should execute for all systems
            if not target_system_id and self.credential_db:
                # No specific system provided - execute for ALL systems in parallel
                # Query database dynamically to get the latest list
                all_systems = self.credential_db.list_credentials()
                logger.info(f"[CREDENTIAL LOOKUP] Queried database, found {len(all_systems)} system(s): {[s['system_id'] for s in all_systems]}")

                if len(all_systems) > 1:
                    logger.info(f"No target_system_id specified, executing for all {len(all_systems)} systems in parallel")
                    return self._execute_for_all_systems(all_systems, kwargs)
                elif len(all_systems) == 1:
                    # Only one system - use it directly
                    target_system_id = all_systems[0]['system_id']
                    logger.info(f"Only one system configured, using: {target_system_id}")
                else:
                    # No systems configured - use defaults
                    logger.warning("No systems configured in database, using default credentials")
                    logger.warning(f"Database path: {self.credential_db.db_path if self.credential_db else 'N/A'}")

            # Single system execution
            credentials = {}

            if target_system_id and self.credential_db:
                # Look up credentials from database
                logger.info(f"[CREDENTIAL LOOKUP] Looking up credentials for system_id: {target_system_id}")
                logger.info(f"[CREDENTIAL LOOKUP] Database path: {self.credential_db.db_path}")
                cred = self.credential_db.get_credential(target_system_id)

                if cred:
                    credentials = cred.get_connection_dict()
                    logger.info(f"[CREDENTIAL LOOKUP] ✓ Found credentials for {target_system_id} (iDRAC IP: {cred.idrac_ip})")
                else:
                    logger.error(f"[CREDENTIAL LOOKUP] ✗ No credentials found for system_id: {target_system_id}")
                    logger.error(f"[CREDENTIAL LOOKUP] Database path: {self.credential_db.db_path}")
                    # List all available systems for debugging
                    all_systems = self.credential_db.list_credentials()
                    logger.error(f"[CREDENTIAL LOOKUP] Available systems in database: {[s['system_id'] for s in all_systems]}")
                    logger.warning(f"Using default credentials (if configured)")
                    credentials = self.default_credentials
            else:
                # Use default credentials
                if not target_system_id:
                    logger.debug(f"[CREDENTIAL LOOKUP] No target_system_id provided, using default credentials")
                if not self.credential_db:
                    logger.warning(f"[CREDENTIAL LOOKUP] No credential database configured, using default credentials")
                credentials = self.default_credentials

            # Filter out None values from credentials
            clean_credentials = {k: v for k, v in credentials.items() if v is not None}

            # Filter out dummy parameter and target_system_id (metadata, not for MCP tool)
            tool_params = {k: v for k, v in kwargs.items() if k not in ("dummy", "target_system_id")}
            logger.debug(f"Tool params (after filtering): {tool_params}")

            # Merge credentials with tool parameters
            params = {**clean_credentials, **tool_params}

            # Validate required parameters before calling MCP server
            input_schema = self.tool_def.get("inputSchema", {})
            required_params = input_schema.get("required", [])

            # Check for missing required parameters (excluding credentials)
            credential_fields = {"idrac_ip", "username", "password", "auth_token"}
            missing_params = []
            for req_param in required_params:
                if req_param not in credential_fields and req_param not in params:
                    missing_params.append(req_param)

            if missing_params:
                error_msg = (
                    f"Missing required parameter(s) for tool '{self.tool_name}': {', '.join(missing_params)}. "
                    f"Required: {[p for p in required_params if p not in credential_fields]}"
                )
                logger.error(f"[TOOL VALIDATION ERROR] {error_msg}")
                raise ToolException(error_msg)

            # Log the parameters being sent (excluding sensitive data)
            param_keys = list(params.keys())
            logger.info(f"[TOOL START] Calling MCP tool '{self.tool_name}' with parameters: {param_keys}")

            # Execute the tool via MCP client
            # Create fresh connection for each call to avoid event loop lifecycle issues
            thread_id = threading.current_thread().name
            logger.debug(f"[{thread_id}] Creating MCP client for '{self.tool_name}'")

            # Create event loop and run everything within it
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # Timeout for entire operation (connect + call + close)
            # MCP calls should complete quickly (5-10 seconds)
            start_time = None

            try:
                # Create client and connect within this loop
                mcp_client = MCPClient(base_url=self.mcp_base_url, timeout=self.mcp_timeout)
                logger.debug(f"[{thread_id}] Connecting to MCP server")

                # Connection with timeout
                start_time = loop.time()
                try:
                    loop.run_until_complete(
                        asyncio.wait_for(mcp_client._connect_async(), timeout=5.0)
                    )
                except asyncio.TimeoutError:
                    raise ToolException(
                        f"Connection to MCP server timed out after 5s for tool '{self.tool_name}'"
                    )

                # Execute tool call with timeout
                logger.debug(f"[{thread_id}] Calling MCP server for '{self.tool_name}'")
                try:
                    result = loop.run_until_complete(
                        asyncio.wait_for(
                            mcp_client.call_tool_async(self.tool_name, params),
                            timeout=10.0  # Max 10 seconds for tool execution
                        )
                    )
                    elapsed = loop.time() - start_time
                    logger.debug(f"[{thread_id}] MCP call completed in {elapsed:.2f}s for '{self.tool_name}'")
                except asyncio.TimeoutError:
                    elapsed = loop.time() - start_time
                    raise ToolException(
                        f"Tool '{self.tool_name}' execution timed out after 10s (total elapsed: {elapsed:.2f}s)"
                    )

                # Clean shutdown (quick, 2s max)
                logger.debug(f"[{thread_id}] Closing MCP client connection")
                try:
                    loop.run_until_complete(
                        asyncio.wait_for(mcp_client.close_async(), timeout=2.0)
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"[{thread_id}] Client close timed out, continuing anyway")

            finally:
                # Clean shutdown of any remaining pending tasks
                try:
                    pending = asyncio.all_tasks(loop)
                    if pending:
                        for task in pending:
                            task.cancel()
                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                except Exception as e:
                    logger.debug(f"[{thread_id}] Task cleanup: {e}")
                finally:
                    loop.close()
                    asyncio.set_event_loop(None)
                    logger.debug(f"[{thread_id}] Event loop closed for '{self.tool_name}'")

            # Convert result to string for LangChain
            logger.info(f"[TOOL SUCCESS] MCP tool '{self.tool_name}' completed successfully")
            if isinstance(result, dict):
                return self._format_result(result)
            else:
                return str(result)

        except ToolException:
            # Re-raise ToolException as-is (validation errors, timeout errors, etc.)
            raise

        except asyncio.TimeoutError:
            # Generic timeout (shouldn't reach here as we catch specific timeouts above)
            error_msg = f"Tool '{self.tool_name}' timed out unexpectedly"
            logger.error(f"[TOOL TIMEOUT] {error_msg}")
            raise ToolException(error_msg)

        except ConnectionError as e:
            error_msg = f"Failed to connect to MCP server for tool '{self.tool_name}': {str(e)}"
            logger.error(f"[TOOL CONNECTION ERROR] {error_msg}")
            raise ToolException(error_msg)

        except ValueError as e:
            # Often indicates parameter validation issues
            error_msg = f"Invalid parameter value for tool '{self.tool_name}': {str(e)}"
            logger.error(f"[TOOL VALUE ERROR] {error_msg}")
            raise ToolException(error_msg)

        except Exception as e:
            # Generic error - log full trace for debugging
            logger.error(f"[TOOL FAILURE] MCP tool '{self.tool_name}' failed: {e}", exc_info=True)

            # Try to extract useful error message from MCP response
            error_msg = str(e)
            if "error" in error_msg.lower():
                # MCP server returned an error, pass it through
                raise ToolException(f"MCP server error for '{self.tool_name}': {error_msg}")
            else:
                raise ToolException(f"Tool '{self.tool_name}' failed: {error_msg}")

    def _execute_for_all_systems(self, all_systems: List[Dict[str, Any]], kwargs: Dict[str, Any]) -> str:
        """
        Execute tool for all configured systems in parallel.

        Args:
            all_systems: List of system summaries from credential database
            kwargs: Tool parameters (excluding target_system_id)

        Returns:
            Consolidated formatted string with results from all systems
        """
        import asyncio
        import time
        from concurrent.futures import ThreadPoolExecutor, as_completed

        logger.info(f"[MULTI-SYSTEM] Executing '{self.tool_name}' for {len(all_systems)} systems in parallel")
        start_time = time.time()

        # Filter out dummy and target_system_id from kwargs
        tool_params = {k: v for k, v in kwargs.items() if k not in ("dummy", "target_system_id")}

        # Prepare execution tasks for each system
        results = {}
        errors = {}

        def execute_for_system(system_info: Dict[str, Any]) -> tuple:
            """Execute tool for a single system (runs in thread pool)."""
            system_id = system_info['system_id']
            try:
                # Get credentials for this system
                cred = self.credential_db.get_credential(system_id)
                if not cred:
                    return (system_id, None, f"Credentials not found for {system_id}")

                credentials = cred.get_connection_dict()
                clean_credentials = {k: v for k, v in credentials.items() if v is not None}

                # Merge credentials with tool parameters
                params = {**clean_credentials, **tool_params}

                # Validate required parameters
                input_schema = self.tool_def.get("inputSchema", {})
                required_params = input_schema.get("required", [])
                credential_fields = {"idrac_ip", "username", "password", "auth_token"}

                missing_params = []
                for req_param in required_params:
                    if req_param not in credential_fields and req_param not in params:
                        missing_params.append(req_param)

                if missing_params:
                    return (system_id, None, f"Missing required parameters: {', '.join(missing_params)}")

                # Execute MCP tool call
                logger.debug(f"[{system_id}] Calling '{self.tool_name}'")

                # Create fresh event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                try:
                    # Create MCP client
                    mcp_client = MCPClient(base_url=self.mcp_base_url, timeout=self.mcp_timeout)

                    # Connect
                    loop.run_until_complete(
                        asyncio.wait_for(mcp_client._connect_async(), timeout=5.0)
                    )

                    # Execute tool
                    result = loop.run_until_complete(
                        asyncio.wait_for(
                            mcp_client.call_tool_async(self.tool_name, params),
                            timeout=10.0
                        )
                    )

                    # Close connection
                    try:
                        loop.run_until_complete(
                            asyncio.wait_for(mcp_client.close_async(), timeout=2.0)
                        )
                    except asyncio.TimeoutError:
                        pass

                    logger.info(f"[{system_id}] Tool '{self.tool_name}' completed successfully")
                    return (system_id, result, None)

                finally:
                    # Cleanup loop
                    try:
                        pending = asyncio.all_tasks(loop)
                        if pending:
                            for task in pending:
                                task.cancel()
                            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                    except:
                        pass
                    finally:
                        loop.close()
                        asyncio.set_event_loop(None)

            except asyncio.TimeoutError:
                logger.error(f"[{system_id}] Tool '{self.tool_name}' timed out")
                return (system_id, None, "Execution timed out")
            except Exception as e:
                logger.error(f"[{system_id}] Tool '{self.tool_name}' failed: {e}")
                return (system_id, None, str(e))

        # Execute in parallel using ThreadPoolExecutor
        max_workers = min(len(all_systems), 10)  # Max 10 concurrent executions
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_system = {
                executor.submit(execute_for_system, system_info): system_info
                for system_info in all_systems
            }

            # Collect results as they complete
            for future in as_completed(future_to_system):
                system_id, result, error = future.result()

                if error:
                    errors[system_id] = error
                else:
                    results[system_id] = result

        elapsed_time = time.time() - start_time
        logger.info(f"[MULTI-SYSTEM] Completed {len(results)} successful, {len(errors)} failed in {elapsed_time:.2f}s")

        # Format consolidated results
        return self._format_multi_system_results(results, errors, elapsed_time)

    def _format_multi_system_results(
        self,
        results: Dict[str, Any],
        errors: Dict[str, str],
        elapsed_time: float
    ) -> str:
        """
        Format multi-system results into readable string.

        Args:
            results: Dictionary of system_id -> result
            errors: Dictionary of system_id -> error message
            elapsed_time: Total execution time

        Returns:
            Formatted string with all results
        """
        output_lines = []

        # Header
        total_systems = len(results) + len(errors)
        output_lines.append(f"=== Results from {total_systems} Systems (completed in {elapsed_time:.2f}s) ===\n")

        # Successful results
        if results:
            for system_id, result in sorted(results.items()):
                output_lines.append(f"\n{'='*60}")
                output_lines.append(f"System: {system_id}")
                output_lines.append(f"{'='*60}")

                if isinstance(result, dict):
                    output_lines.append(self._format_result(result))
                else:
                    output_lines.append(str(result))

        # Errors
        if errors:
            output_lines.append(f"\n\n{'='*60}")
            output_lines.append(f"ERRORS ({len(errors)} systems failed)")
            output_lines.append(f"{'='*60}")

            for system_id, error in sorted(errors.items()):
                output_lines.append(f"\n[{system_id}] ERROR: {error}")

        # Summary
        output_lines.append(f"\n\n{'='*60}")
        output_lines.append(f"SUMMARY: {len(results)} successful, {len(errors)} failed out of {total_systems} systems")
        output_lines.append(f"{'='*60}")

        return "\n".join(output_lines)

    def _format_result(self, result: Dict[str, Any]) -> str:
        """
        Format dictionary result as readable string for LLM.

        Args:
            result: Result dictionary from MCP tool

        Returns:
            Formatted string
        """
        # Remove OData fields for cleaner output
        clean_result = {
            k: v for k, v in result.items()
            if not k.startswith('@odata')
        }

        # Format as key-value pairs
        lines = []
        for key, value in clean_result.items():
            if isinstance(value, dict):
                lines.append(f"{key}:")
                for sub_key, sub_value in value.items():
                    lines.append(f"  {sub_key}: {sub_value}")
            elif isinstance(value, list):
                lines.append(f"{key}: {len(value)} items")
            else:
                lines.append(f"{key}: {value}")

        return "\n".join(lines)


class MCPToLangChainAdapter:
    """Converts MCP client tools to LangChain tools."""

    def __init__(
        self,
        mcp_client: MCPClient,
        credential_db: Optional[CredentialDatabase] = None,
        default_credentials: Optional[Dict[str, str]] = None
    ):
        """
        Initialize the adapter.

        Args:
            mcp_client: MCP client instance
            credential_db: Credential database for dynamic credential lookup (optional)
            default_credentials: Default credentials if no credential_db or system_id (optional)
        """
        self.mcp_client = mcp_client
        self.credential_db = credential_db
        self.default_credentials = default_credentials or {}

    def _get_available_systems(self) -> List[str]:
        """
        Get list of available systems dynamically (no caching).

        This ensures we always have the latest list, even if systems
        are added/removed after the adapter was initialized.

        Returns:
            List of system IDs
        """
        if self.credential_db:
            return [s['system_id'] for s in self.credential_db.list_credentials()]
        return []

    def create_langchain_tools(self) -> List[StructuredTool]:
        """
        Convert all MCP tools to LangChain tools.

        Returns:
            List of LangChain StructuredTool instances
        """
        # Get tools from MCP server
        mcp_tools = self.mcp_client.list_tools()
        return self._create_langchain_tools_from_list(mcp_tools)

    def _create_langchain_tools_from_list(self, mcp_tools: List[Dict[str, Any]]) -> List[StructuredTool]:
        """
        Convert a list of MCP tools to LangChain tools.

        Args:
            mcp_tools: List of MCP tool definitions

        Returns:
            List of LangChain StructuredTool instances
        """
        langchain_tools = []
        for tool_def in mcp_tools:
            try:
                lc_tool = self._create_langchain_tool(tool_def)
                langchain_tools.append(lc_tool)
            except Exception as e:
                tool_name = tool_def.get("name", "unknown")
                logger.warning(f"Failed to convert tool '{tool_name}': {e}")

        logger.info(f"Converted {len(langchain_tools)} MCP tools to LangChain format")
        return langchain_tools

    def _create_langchain_tool(self, tool_def: Dict[str, Any]) -> StructuredTool:
        """
        Create a LangChain StructuredTool from an MCP tool.

        Args:
            tool_def: Tool definition from MCP server

        Returns:
            LangChain StructuredTool
        """
        # Create wrapper
        wrapper = MCPToolWrapper(
            self.mcp_client,
            tool_def,
            credential_db=self.credential_db,
            default_credentials=self.default_credentials
        )

        # Build parameter schema for LangChain
        args_schema = self._build_args_schema(tool_def)

        # Enhance description with parameter information
        enhanced_description = self._enhance_tool_description(tool_def)

        # Create LangChain tool
        return StructuredTool(
            name=tool_def.get("name", "unknown"),
            description=enhanced_description,
            func=wrapper.execute,
            args_schema=args_schema,
            return_direct=False,
        )

    def _build_args_schema(self, tool_def: Dict[str, Any]) -> Type[BaseModel]:
        """
        Build Pydantic schema for tool arguments.

        Args:
            tool_def: Tool definition from MCP server

        Returns:
            Pydantic model class
        """
        # Get input schema from MCP tool definition
        input_schema = tool_def.get("inputSchema", {})
        properties = input_schema.get("properties", {})
        required = input_schema.get("required", [])

        # Build field definitions
        fields = {}

        # Filter out credential fields (they're auto-injected)
        credential_fields = {"idrac_ip", "username", "password", "auth_token"}

        for param_name, param_spec in properties.items():
            # Skip credential fields
            if param_name in credential_fields:
                continue

            # Map JSON schema types to Python types
            json_type = param_spec.get("type", "string")
            if json_type == "integer":
                field_type = int
            elif json_type == "number":
                field_type = float
            elif json_type == "boolean":
                field_type = bool
            elif json_type == "array":
                field_type = list
            elif json_type == "object":
                field_type = dict
            else:
                field_type = str

            # Determine if required (not in credentials and in required list)
            is_required = param_name in required
            field_default = ... if is_required else param_spec.get("default", None)

            # Build comprehensive description
            description = param_spec.get("description", f"Parameter: {param_name}")

            # Add type hint to description
            description += f" (type: {json_type})"

            # Add enum values if present
            if "enum" in param_spec:
                enum_values = param_spec["enum"]
                description += f". Allowed values: {', '.join(map(str, enum_values))}"

            # Add default value to description if present and not required
            if not is_required and "default" in param_spec:
                description += f". Default: {param_spec['default']}"

            fields[param_name] = (
                field_type,
                Field(default=field_default, description=description)
            )

        # Add target_system_id parameter for credential lookup
        # This is optional - if provided, credentials will be looked up from database
        system_desc = "Optional: System identifier for credential lookup (e.g., 'server-01')."
        available_systems = self._get_available_systems()
        if available_systems:
            num_systems = len(available_systems)
            system_desc += f" Available systems: {', '.join(available_systems)}."
            if num_systems > 1:
                system_desc += f" If not provided, this tool will execute for ALL {num_systems} systems in parallel and return consolidated results."
        else:
            system_desc += " If not provided, default credentials will be used."

        fields["target_system_id"] = (
            str,
            Field(default=None, description=system_desc)
        )

        # Create dynamic Pydantic model
        tool_name = tool_def.get("name", "unknown")
        model_name = f"{tool_name}_args"

        # Handle case where there are no parameters (except target_system_id)
        if len(fields) == 1:  # Only target_system_id
            fields["dummy"] = (str, Field(default=None, description="No parameters required"))

        return create_model(model_name, **fields)

    def _enhance_tool_description(self, tool_def: Dict[str, Any]) -> str:
        """
        Enhance tool description with clear parameter requirements.

        Args:
            tool_def: Tool definition from MCP server

        Returns:
            Enhanced description string
        """
        base_description = tool_def.get("description", "No description")

        # Get parameter info
        input_schema = tool_def.get("inputSchema", {})
        properties = input_schema.get("properties", {})
        required = input_schema.get("required", [])

        # Filter out credential fields
        credential_fields = {"idrac_ip", "username", "password", "auth_token"}

        # Collect non-credential required parameters
        required_params = []
        optional_params = []

        for param_name, param_spec in properties.items():
            if param_name in credential_fields:
                continue

            param_info = {
                "name": param_name,
                "type": param_spec.get("type", "string"),
                "description": param_spec.get("description", ""),
                "default": param_spec.get("default"),
                "enum": param_spec.get("enum")
            }

            if param_name in required:
                required_params.append(param_info)
            else:
                optional_params.append(param_info)

        # Build enhanced description
        enhanced = base_description

        # Add required parameters section
        if required_params:
            enhanced += "\n\nREQUIRED Parameters:"
            for param in required_params:
                enhanced += f"\n  - {param['name']} ({param['type']}): {param['description']}"
                if param['enum']:
                    enhanced += f". Options: {', '.join(map(str, param['enum']))}"

        # Add optional parameters section
        if optional_params:
            enhanced += "\n\nOptional Parameters:"
            for param in optional_params:
                enhanced += f"\n  - {param['name']} ({param['type']}): {param['description']}"
                if param['default'] is not None:
                    enhanced += f". Default: {param['default']}"
                if param['enum']:
                    enhanced += f". Options: {', '.join(map(str, param['enum']))}"

        # Add note about credentials and multi-system capability
        enhanced += "\n\nNote: Authentication credentials (idrac_ip, username, password) are automatically provided."

        # Add multi-system capability info
        available_systems = self._get_available_systems()
        if available_systems and len(available_systems) > 1:
            enhanced += f"\n\nMULTI-SYSTEM CAPABILITY: If you don't specify target_system_id, this tool will automatically execute for ALL {len(available_systems)} configured systems ({', '.join(available_systems)}) in parallel and return consolidated results. This is useful for comparing data across all systems or checking status of all servers."

        return enhanced


def create_mcp_agent_tools(
    mcp_client: MCPClient,
    credentials: Optional[Dict[str, str]] = None,
    credential_db: Optional[CredentialDatabase] = None
) -> List[StructuredTool]:
    """
    Convenience function to create LangChain tools from MCP client.

    Args:
        mcp_client: MCP client instance
        credentials: Default authentication credentials (deprecated, use credential_db)
        credential_db: Credential database for dynamic credential lookup

    Returns:
        List of LangChain tools

    Example (with credential database):
        >>> from utils.credential_manager import CredentialDatabase
        >>> mcp_client = MCPClient("http://localhost:8000")
        >>> credential_db = CredentialDatabase()
        >>> tools = create_mcp_agent_tools(mcp_client, credential_db=credential_db)
        >>> agent = create_react_agent(llm, tools, prompt)

    Example (legacy with static credentials):
        >>> mcp_client = MCPClient("http://localhost:8000")
        >>> tools = create_mcp_agent_tools(mcp_client, credentials={
        ...     "idrac_ip": "192.168.1.100",
        ...     "username": "admin",
        ...     "password": "password"
        ... })
        >>> agent = create_react_agent(llm, tools, prompt)
    """
    adapter = MCPToLangChainAdapter(
        mcp_client,
        credential_db=credential_db,
        default_credentials=credentials
    )
    return adapter.create_langchain_tools()
