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


"""Parser for tool configuration YAML files."""

import yaml
from typing import Dict, List, Optional, Any
from pathlib import Path
from pydantic import ValidationError

from ..models.tool_definition import (
    ToolsConfiguration,
    ToolDefinition,
    ParameterMapping,
    AuthenticationConfig,
    ServerConfig,
)


class ToolConfigParser:
    """
    Parser for tool configuration YAML files.

    This class reads and validates tool definition files that specify
    which Redfish API operations to expose as MCP tools.
    """

    def __init__(self, config_file_path: str):
        """
        Initialize the tool configuration parser.

        Args:
            config_file_path: Path to the tool configuration YAML file
        """
        self.file_path = Path(config_file_path)
        self.config: Optional[ToolsConfiguration] = None
        self._load_config()

    def _load_config(self) -> None:
        """Load and parse the tool configuration file."""
        if not self.file_path.exists():
            raise FileNotFoundError(f"Tool configuration file not found: {self.file_path}")

        with open(self.file_path, "r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f)

        if not raw_config:
            raise ValueError(f"Empty or invalid configuration file: {self.file_path}")

        self._parse_config(raw_config)

    def _parse_config(self, raw_config: Dict[str, Any]) -> None:
        """
        Parse and validate the raw configuration dictionary.

        Args:
            raw_config: Raw configuration dictionary from YAML

        Raises:
            ValidationError: If configuration is invalid
        """
        try:
            # Parse server configuration
            server_config = ServerConfig(**raw_config.get("server", {}))

            # Parse authentication configuration
            auth_config = AuthenticationConfig(**raw_config.get("authentication", {}))

            # Parse tool definitions
            tools = []
            for tool_spec in raw_config.get("tools", []):
                tool = self._parse_tool_definition(tool_spec)
                if tool:
                    tools.append(tool)

            self.config = ToolsConfiguration(
                version=raw_config.get("version", "1.0"),
                server=server_config,
                authentication=auth_config,
                tools=tools,
            )

        except ValidationError as e:
            raise ValueError(f"Invalid tool configuration: {e}")

    def _parse_tool_definition(self, tool_spec: Dict[str, Any]) -> Optional[ToolDefinition]:
        """
        Parse a single tool definition.

        Args:
            tool_spec: Tool specification dictionary

        Returns:
            ToolDefinition object or None if parsing fails
        """
        try:
            # Parse parameter mappings
            mappings = []
            for mapping_spec in tool_spec.get("parameter_mappings", []):
                mapping = ParameterMapping(**mapping_spec)
                mappings.append(mapping)

            return ToolDefinition(
                name=tool_spec["name"],
                description=tool_spec["description"],
                operation_id=tool_spec["operation_id"],
                enabled=tool_spec.get("enabled", True),
                category=tool_spec.get("category"),
                parameter_mappings=mappings,
                additional_parameters=tool_spec.get("additional_parameters", {}),
                response_transform=tool_spec.get("response_transform"),
                examples=tool_spec.get("examples"),
            )
        except (KeyError, ValidationError) as e:
            print(f"Warning: Failed to parse tool definition: {e}")
            return None

    def get_config(self) -> ToolsConfiguration:
        """
        Get the parsed configuration.

        Returns:
            ToolsConfiguration object

        Raises:
            ValueError: If configuration hasn't been loaded
        """
        if not self.config:
            raise ValueError("Configuration not loaded")
        return self.config

    def get_tool_definition(self, tool_name: str) -> Optional[ToolDefinition]:
        """
        Get a specific tool definition by name.

        Args:
            tool_name: Name of the tool to retrieve

        Returns:
            ToolDefinition object or None if not found
        """
        if not self.config:
            return None
        return self.config.get_tool_by_name(tool_name)

    def get_enabled_tools(self) -> List[ToolDefinition]:
        """
        Get all enabled tool definitions.

        Returns:
            List of enabled ToolDefinition objects
        """
        if not self.config:
            return []
        return self.config.get_enabled_tools()

    def validate_against_openapi(
        self, operation_ids: List[str]
    ) -> tuple[List[str], List[str]]:
        """
        Validate that all tool operation IDs exist in the OpenAPI specification.

        Args:
            operation_ids: List of valid operation IDs from OpenAPI spec

        Returns:
            Tuple of (valid_tools, invalid_tools) where each is a list of tool names
        """
        if not self.config:
            return [], []

        valid_tools = []
        invalid_tools = []

        for tool in self.config.tools:
            if tool.operation_id in operation_ids:
                valid_tools.append(tool.name)
            else:
                invalid_tools.append(tool.name)

        return valid_tools, invalid_tools

    def reload(self) -> None:
        """Reload the configuration from file."""
        self._load_config()

    def get_server_config(self) -> Optional[ServerConfig]:
        """
        Get server configuration.

        Returns:
            ServerConfig object or None if not loaded
        """
        if not self.config:
            return None
        return self.config.server

    def get_auth_config(self) -> Optional[AuthenticationConfig]:
        """
        Get authentication configuration.

        Returns:
            AuthenticationConfig object or None if not loaded
        """
        if not self.config:
            return None
        return self.config.authentication
