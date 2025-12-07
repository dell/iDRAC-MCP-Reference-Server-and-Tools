#  Copyright 2025 Dell Inc. or its subsidiaries. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.


"""Generator for creating MCP tools from tool definitions."""

from typing import Dict, Any, List, Callable, Optional, Tuple, Annotated
from functools import wraps
import inspect

from ..models.tool_definition import ToolDefinition, ParameterMapping
from ..models.api_operation import ApiOperation, ParameterLocation
from ..clients.redfish_client import RedfishClient
from ..auth.authentication import Credentials


class ToolGenerator:
    """
    Generates MCP tool functions from tool definitions and API operations.

    This class creates callable functions that can be registered with the MCP server,
    handling parameter mapping and API execution.
    """

    def __init__(self, redfish_client: RedfishClient):
        """
        Initialize the tool generator.

        Args:
            redfish_client: Client for making Redfish API calls
        """
        self.client = redfish_client

    def generate_tool(
        self, tool_def: ToolDefinition, api_operation: ApiOperation
    ) -> Callable:
        """
        Generate an MCP tool function from a tool definition and API operation.

        Args:
            tool_def: Tool definition from configuration
            api_operation: API operation from OpenAPI spec

        Returns:
            Callable function that can be registered as an MCP tool
        """
        # Build parameter list for the function signature
        # Separate required and optional parameters to maintain proper order
        required_params = [
            inspect.Parameter(
                'idrac_ip',
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=Annotated[str, "iDRAC IP address or hostname. Protocol prefix (https://) is optional."]
            ),
        ]

        optional_params = [
            inspect.Parameter(
                'username',
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=Annotated[Optional[str], "iDRAC username for authentication (required for Basic Auth)"],
                default=None
            ),
            inspect.Parameter(
                'password',
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=Annotated[Optional[str], "iDRAC password for authentication (required for Basic Auth)"],
                default=None
            ),
            inspect.Parameter(
                'auth_token',
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=Annotated[Optional[str], "iDRAC auth token for authentication (required for Token Auth)"],
                default=None
            ),
        ]

        # Add tool-specific parameters - separate required and optional
        for mapping in tool_def.parameter_mappings:
            param_type = str  # Default type
            param_desc = mapping.description or f"Parameter: {mapping.tool_param_name}"

            if mapping.required:
                # Add to required params (no default)
                required_params.append(
                    inspect.Parameter(
                        mapping.tool_param_name,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        annotation=Annotated[param_type, param_desc],
                        default=inspect.Parameter.empty
                    )
                )
            else:
                # Add to optional params (with default)
                default = mapping.default if mapping.default is not None else None
                optional_params.append(
                    inspect.Parameter(
                        mapping.tool_param_name,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        annotation=Annotated[Optional[param_type], param_desc],
                        default=default
                    )
                )

        # Combine: all required params first, then all optional params
        params = required_params + optional_params

        # Create the function signature
        sig = inspect.Signature(params, return_annotation=Dict[str, Any])

        # Create the actual function
        def tool_function(*args, **kwargs):
            """
            Generated tool function that executes the Redfish API operation.

            Returns:
                API response data

            Raises:
                ValueError: If required parameters are missing
                RedfishAPIError: If API call fails
            """
            # Bind arguments to parameters
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            arguments = bound.arguments

            # Extract iDRAC IP (mandatory)
            idrac_ip = arguments.get('idrac_ip')
            if not idrac_ip:
                raise ValueError("Missing required parameter 'idrac_ip'")

            # Ensure protocol prefix
            if not idrac_ip.startswith(('http://', 'https://')):
                idrac_ip = f"https://{idrac_ip}"

            # Extract credentials
            username = arguments.get('username')
            password = arguments.get('password')
            auth_token = arguments.get('auth_token')

            # Validate authentication parameters based on auth method
            if auth_token:
                # Token Auth: only auth_token is required
                credentials = Credentials(token=auth_token)
            elif username and password:
                # Basic Auth: username and password are required
                credentials = Credentials(username=username, password=password)
            else:
                # Invalid combination
                raise ValueError(
                    "Authentication required. Provide either:\n"
                    "  - 'auth_token' for Token Authentication, OR\n"
                    "  - 'username' AND 'password' for Basic Authentication"
                )

            # Map tool parameters to API parameters
            path_params, query_params, headers, body = self._map_parameters(
                tool_def, api_operation, arguments
            )

            # Execute the API operation
            result = self.client.execute_operation(
                operation=api_operation,
                credentials=credentials,
                base_url=idrac_ip,
                path_params=path_params,
                query_params=query_params,
                body=body,
                headers=headers,
            )

            # Return raw JSON response
            return result

        # Set function metadata
        tool_function.__name__ = tool_def.name
        tool_function.__doc__ = tool_def.description
        tool_function.__signature__ = sig
        tool_function.__annotations__ = {
            param.name: param.annotation for param in params
        }
        tool_function.__annotations__['return'] = Dict[str, Any]

        return tool_function

    def _map_parameters(
        self,
        tool_def: ToolDefinition,
        api_operation: ApiOperation,
        kwargs: Dict[str, Any],
    ) -> Tuple[
        Dict[str, Any], Dict[str, Any], Dict[str, str], Optional[Dict[str, Any]]
    ]:
        """
        Map tool parameters to API parameters.

        Args:
            tool_def: Tool definition
            api_operation: API operation
            kwargs: Tool parameters

        Returns:
            Tuple of (path_params, query_params, headers, body)

        Raises:
            ValueError: If required parameters are missing
        """
        path_params: Dict[str, Any] = {}
        query_params: Dict[str, Any] = {}
        headers: Dict[str, str] = {}
        body_params: Dict[str, Any] = {}

        # Process parameter mappings
        for mapping in tool_def.parameter_mappings:
            tool_param_value = kwargs.get(mapping.tool_param_name)

            # Check if required parameter is missing
            if mapping.required and tool_param_value is None:
                # Use default if available
                if mapping.default is not None:
                    tool_param_value = mapping.default
                else:
                    raise ValueError(
                        f"Required parameter '{mapping.tool_param_name}' is missing"
                    )

            # Skip if optional and not provided
            if tool_param_value is None:
                continue

            # Apply transformation if specified
            if mapping.transform:
                tool_param_value = self._apply_transform(
                    tool_param_value, mapping.transform
                )

            # Route parameter to correct location
            location = mapping.location.lower()
            if location == "path":
                path_params[mapping.api_param_name] = tool_param_value
            elif location == "query":
                query_params[mapping.api_param_name] = tool_param_value
            elif location == "header":
                headers[mapping.api_param_name] = str(tool_param_value)
            elif location == "body":
                body_params[mapping.api_param_name] = tool_param_value

        # Include additional parameters if specified
        for key, value in tool_def.additional_parameters.items():
            if key not in kwargs:
                body_params[key] = value

        # Return body as None if empty
        body = body_params if body_params else None

        return path_params, query_params, headers, body

    def _apply_transform(self, value: Any, transform: str) -> Any:
        """
        Apply a transformation to a parameter value.

        Args:
            value: Original value
            transform: Transformation name

        Returns:
            Transformed value
        """
        # Basic transformations
        transforms: Dict[str, Callable[[Any], Any]] = {
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "upper": lambda x: str(x).upper(),
            "lower": lambda x: str(x).lower(),
            "strip": lambda x: str(x).strip(),
        }

        transform_func = transforms.get(transform.lower())
        if transform_func:
            return transform_func(value)

        # If no matching transform, return original value
        return value

    def generate_tool_schema(
        self, tool_def: ToolDefinition, api_operation: ApiOperation
    ) -> Dict[str, Any]:
        """
        Generate MCP tool schema from tool definition.

        Args:
            tool_def: Tool definition
            api_operation: API operation

        Returns:
            Tool schema dictionary for MCP server registration
        """
        # Build parameters schema
        parameters = {
            "type": "object",
            "properties": {},
            "required": [],
        }

        # Add mandatory idrac_ip parameter
        parameters["properties"]["idrac_ip"] = {
            "type": "string",
            "description": "iDRAC IP address or hostname. Protocol prefix (https://) is optional.",
        }
        parameters["required"].append("idrac_ip")

        # Add authentication parameters
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

        # Add mapped parameters
        for mapping in tool_def.parameter_mappings:
            param_schema = self._create_parameter_schema(mapping, api_operation)
            parameters["properties"][mapping.tool_param_name] = param_schema

            if mapping.required:
                parameters["required"].append(mapping.tool_param_name)

        return {
            "name": tool_def.name,
            "description": tool_def.description,
            "inputSchema": parameters,
        }

    def _create_parameter_schema(
        self, mapping: ParameterMapping, api_operation: ApiOperation
    ) -> Dict[str, Any]:
        """
        Create JSON schema for a parameter.

        Args:
            mapping: Parameter mapping
            api_operation: API operation

        Returns:
            JSON schema for the parameter
        """
        schema: Dict[str, Any] = {
            "type": "string",  # Default type
        }

        if mapping.description:
            schema["description"] = mapping.description

        if mapping.default is not None:
            schema["default"] = mapping.default

        # Try to get more specific type information from API operation
        for api_param in api_operation.parameters:
            if api_param.name == mapping.api_param_name:
                if api_param.schema_def:
                    param_type = api_param.schema_def.get("type", "string")
                    schema["type"] = param_type

                    # Add enum if available
                    if "enum" in api_param.schema_def:
                        schema["enum"] = api_param.schema_def["enum"]

                if not mapping.description and api_param.description:
                    schema["description"] = api_param.description

                break

        return schema
