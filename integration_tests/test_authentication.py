# Licensed to You under the Apache License, Version 2.0

"""
Integration tests for authentication.

These tests verify that both Basic Auth and Token Auth work correctly
through the complete server stack.
"""

import pytest
from src.server.mcp_server import RedfishMCPServer
from src.auth.authentication import Credentials


class TestBasicAuthentication:
    """Test Basic Authentication (username + password)."""

    def test_basic_auth_valid_credentials(self, mcp_server: RedfishMCPServer, basic_auth_credentials: dict):
        """Test that valid basic auth credentials work."""
        # Get a tool function
        tools = mcp_server.config.get_enabled_tools()
        service_root_tool = next((t for t in tools if t.name == "get_service_root"), None)
        assert service_root_tool is not None

        # Get the API operation
        api_operation = mcp_server.openapi_parser.get_operation(service_root_tool.operation_id)

        # Generate the tool function
        tool_func = mcp_server.tool_generator.generate_tool(service_root_tool, api_operation)

        # Execute with basic auth
        result = tool_func(
            idrac_ip=basic_auth_credentials["idrac_ip"],
            username=basic_auth_credentials["username"],
            password=basic_auth_credentials["password"]
        )

        # Should return data (either formatted or raw)
        assert result is not None
        assert isinstance(result, dict)

    def test_basic_auth_missing_username(self, mcp_server: RedfishMCPServer, basic_auth_credentials: dict):
        """Test that missing username raises error."""
        tools = mcp_server.config.get_enabled_tools()
        service_root_tool = next((t for t in tools if t.name == "get_service_root"), None)
        api_operation = mcp_server.openapi_parser.get_operation(service_root_tool.operation_id)
        tool_func = mcp_server.tool_generator.generate_tool(service_root_tool, api_operation)

        with pytest.raises(ValueError, match="Authentication required"):
            tool_func(
                idrac_ip=basic_auth_credentials["idrac_ip"],
                password=basic_auth_credentials["password"]
                # Missing username
            )

    def test_basic_auth_missing_password(self, mcp_server: RedfishMCPServer, basic_auth_credentials: dict):
        """Test that missing password raises error."""
        tools = mcp_server.config.get_enabled_tools()
        service_root_tool = next((t for t in tools if t.name == "get_service_root"), None)
        api_operation = mcp_server.openapi_parser.get_operation(service_root_tool.operation_id)
        tool_func = mcp_server.tool_generator.generate_tool(service_root_tool, api_operation)

        with pytest.raises(ValueError, match="Authentication required"):
            tool_func(
                idrac_ip=basic_auth_credentials["idrac_ip"],
                username=basic_auth_credentials["username"]
                # Missing password
            )

    @pytest.mark.mock_only
    def test_basic_auth_invalid_credentials(self, mcp_server: RedfishMCPServer, basic_auth_credentials: dict):
        """Test that invalid credentials raise error (mock mode only)."""
        tools = mcp_server.config.get_enabled_tools()
        service_root_tool = next((t for t in tools if t.name == "get_service_root"), None)
        api_operation = mcp_server.openapi_parser.get_operation(service_root_tool.operation_id)
        tool_func = mcp_server.tool_generator.generate_tool(service_root_tool, api_operation)

        from src.clients.redfish_client import RedfishAPIError

        with pytest.raises(RedfishAPIError):
            tool_func(
                idrac_ip=basic_auth_credentials["idrac_ip"],
                username="invalid_user",
                password="invalid_pass"
            )


class TestTokenAuthentication:
    """Test Token Authentication (auth_token only)."""

    def test_token_auth_valid(self, mcp_server: RedfishMCPServer, token_auth_credentials: dict):
        """Test that valid token auth works."""
        tools = mcp_server.config.get_enabled_tools()
        service_root_tool = next((t for t in tools if t.name == "get_service_root"), None)
        api_operation = mcp_server.openapi_parser.get_operation(service_root_tool.operation_id)
        tool_func = mcp_server.tool_generator.generate_tool(service_root_tool, api_operation)

        # Execute with token auth (no username/password)
        result = tool_func(
            idrac_ip=token_auth_credentials["idrac_ip"],
            auth_token=token_auth_credentials["auth_token"]
        )

        assert result is not None
        assert isinstance(result, dict)

    def test_token_auth_no_username_required(self, mcp_server: RedfishMCPServer, token_auth_credentials: dict):
        """Test that token auth doesn't require username."""
        tools = mcp_server.config.get_enabled_tools()
        service_root_tool = next((t for t in tools if t.name == "get_service_root"), None)
        api_operation = mcp_server.openapi_parser.get_operation(service_root_tool.operation_id)
        tool_func = mcp_server.tool_generator.generate_tool(service_root_tool, api_operation)

        # Should work with just auth_token
        result = tool_func(
            idrac_ip=token_auth_credentials["idrac_ip"],
            auth_token=token_auth_credentials["auth_token"]
            # No username or password
        )

        assert result is not None

    def test_token_auth_missing_token(self, mcp_server: RedfishMCPServer, token_auth_credentials: dict):
        """Test that missing token raises error."""
        tools = mcp_server.config.get_enabled_tools()
        service_root_tool = next((t for t in tools if t.name == "get_service_root"), None)
        api_operation = mcp_server.openapi_parser.get_operation(service_root_tool.operation_id)
        tool_func = mcp_server.tool_generator.generate_tool(service_root_tool, api_operation)

        with pytest.raises(ValueError, match="Authentication required"):
            tool_func(
                idrac_ip=token_auth_credentials["idrac_ip"]
                # Missing auth_token
            )

    @pytest.mark.mock_only
    def test_token_auth_invalid_token(self, mcp_server: RedfishMCPServer, token_auth_credentials: dict):
        """Test that invalid token raises error (mock mode only)."""
        tools = mcp_server.config.get_enabled_tools()
        service_root_tool = next((t for t in tools if t.name == "get_service_root"), None)
        api_operation = mcp_server.openapi_parser.get_operation(service_root_tool.operation_id)
        tool_func = mcp_server.tool_generator.generate_tool(service_root_tool, api_operation)

        from src.clients.redfish_client import RedfishAPIError

        with pytest.raises(RedfishAPIError):
            tool_func(
                idrac_ip=token_auth_credentials["idrac_ip"],
                auth_token="invalid-token-12345"
            )


class TestAuthenticationHandlers:
    """Test authentication handler selection."""

    def test_basic_auth_handler_validates(self, mcp_server: RedfishMCPServer):
        """Test basic auth handler validation."""
        handler = mcp_server.basic_auth_handler

        # Valid credentials
        valid_creds = Credentials(username="admin", password="password")
        assert handler.validate_credentials(valid_creds) is True

        # Invalid credentials
        invalid_creds = Credentials(username="admin", password=None)
        assert handler.validate_credentials(invalid_creds) is False

    def test_token_auth_handler_validates(self, mcp_server: RedfishMCPServer):
        """Test token auth handler validation."""
        handler = mcp_server.token_auth_handler

        # Valid credentials
        valid_creds = Credentials(token="test-token")
        assert handler.validate_credentials(valid_creds) is True

        # Invalid credentials
        invalid_creds = Credentials(token=None)
        assert handler.validate_credentials(invalid_creds) is False
