# Licensed to You under the Apache License, Version 2.0

"""
Integration tests for MCP server startup and initialization.

These tests verify that the MCP server starts correctly and loads
the proper configuration.
"""

import pytest
from src.server.mcp_server import RedfishMCPServer


class TestServerStartup:
    """Test MCP server initialization."""

    def test_server_initializes(self, mcp_server: RedfishMCPServer):
        """Test that server initializes successfully."""
        assert mcp_server is not None
        assert mcp_server.server_name == "test-idrac-server"

    def test_server_loads_tools(self, mcp_server: RedfishMCPServer):
        """Test that server loads configured tools."""
        tools = mcp_server.config.get_enabled_tools()

        assert len(tools) > 0, "Server should load at least one tool"

        # Check specific tools from test config
        tool_names = [tool.name for tool in tools]
        assert "get_system_info" in tool_names
        assert "list_systems" in tool_names
        assert "reset_system" in tool_names
        assert "get_service_root" in tool_names

    def test_server_configuration(self, mcp_server: RedfishMCPServer):
        """Test that server configuration is loaded correctly."""
        config = mcp_server.config

        # Check server config
        assert config.server.verify_ssl is False  # Test config disables SSL
        assert config.server.timeout == 10
        assert config.server.max_retries == 1

        # Check auth config
        assert config.authentication.token_header == "X-Auth-Token"

    def test_authentication_handlers(self, mcp_server: RedfishMCPServer):
        """Test that authentication handlers are initialized."""
        assert mcp_server.basic_auth_handler is not None
        assert mcp_server.token_auth_handler is not None

    def test_redfish_client(self, mcp_server: RedfishMCPServer):
        """Test that Redfish client is initialized."""
        assert mcp_server.redfish_client is not None
        assert mcp_server.redfish_client.verify_ssl is False
        assert mcp_server.redfish_client.timeout == 10

    def test_tool_generator(self, mcp_server: RedfishMCPServer):
        """Test that tool generator is initialized."""
        assert mcp_server.tool_generator is not None
        assert mcp_server.tool_generator.client is not None
