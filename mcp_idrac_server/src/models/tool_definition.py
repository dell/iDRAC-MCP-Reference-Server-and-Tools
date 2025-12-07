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


"""Data models for tool definitions from configuration YAML."""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, field_validator


class ParameterMapping(BaseModel):
    """Mapping between tool parameter and API parameter."""

    tool_param_name: str
    api_param_name: str
    location: str  # path, query, header, body
    description: Optional[str] = None
    required: bool = True
    default: Optional[Any] = None
    transform: Optional[str] = None  # Optional transformation function


class ToolDefinition(BaseModel):
    """
    Definition of a tool to be exposed through the MCP server.

    This maps a user-friendly tool interface to underlying Redfish API operations.
    """

    name: str
    description: str
    operation_id: str  # References the operationId in OpenAPI spec
    enabled: bool = True
    category: Optional[str] = None
    parameter_mappings: List[ParameterMapping] = []
    additional_parameters: Dict[str, Any] = {}
    response_transform: Optional[str] = None  # Optional response transformation
    examples: Optional[List[Dict[str, Any]]] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate tool name follows naming conventions."""
        if not v:
            raise ValueError("Tool name cannot be empty")
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Tool name must be alphanumeric (underscores and hyphens allowed)")
        return v

    def get_required_mappings(self) -> List[ParameterMapping]:
        """Get list of required parameter mappings."""
        return [mapping for mapping in self.parameter_mappings if mapping.required]

    def get_optional_mappings(self) -> List[ParameterMapping]:
        """Get list of optional parameter mappings."""
        return [mapping for mapping in self.parameter_mappings if not mapping.required]


class AuthenticationConfig(BaseModel):
    """Authentication configuration for the MCP server."""

    # Credentials are provided by the client per-request
    # Only the token header name is configurable
    token_header: str = "X-Auth-Token"


class ServerConfig(BaseModel):
    """Configuration for Redfish server connection."""

    base_url: Optional[str] = None  # Can be provided at runtime
    verify_ssl: bool = True
    timeout: int = 30
    max_retries: int = 3




class ToolsConfiguration(BaseModel):
    """
    Root configuration object for tool definitions.

    This represents the entire tools.yaml configuration file.
    """

    version: str = "1.0"
    server: ServerConfig = ServerConfig()
    authentication: AuthenticationConfig = AuthenticationConfig()
    tools: List[ToolDefinition] = []

    def get_enabled_tools(self) -> List[ToolDefinition]:
        """Get list of enabled tools."""
        return [tool for tool in self.tools if tool.enabled]

    def get_tool_by_name(self, name: str) -> Optional[ToolDefinition]:
        """Get tool definition by name."""
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None

    def get_tools_by_category(self, category: str) -> List[ToolDefinition]:
        """Get all tools in a specific category."""
        return [tool for tool in self.tools if tool.category == category]
