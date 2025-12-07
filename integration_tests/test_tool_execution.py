# Licensed to You under the Apache License, Version 2.0

"""
Integration tests for tool execution.

These tests verify that tools execute correctly end-to-end,
from client request through server to iDRAC API and back.
"""

import pytest
from src.server.mcp_server import RedfishMCPServer
from utils.test_helpers import assert_tool_result


class TestToolExecution:
    """Test end-to-end tool execution."""

    def test_get_service_root(self, mcp_server: RedfishMCPServer, basic_auth_credentials: dict):
        """Test getting service root."""
        tools = mcp_server.config.get_enabled_tools()
        tool_def = next((t for t in tools if t.name == "get_service_root"), None)
        assert tool_def is not None

        api_operation = mcp_server.openapi_parser.get_operation(tool_def.operation_id)
        tool_func = mcp_server.tool_generator.generate_tool(tool_def, api_operation)

        result = tool_func(**basic_auth_credentials)

        # Verify result structure
        assert_tool_result(result, expected_keys=["Name", "RedfishVersion"])

    def test_list_systems(self, mcp_server: RedfishMCPServer, basic_auth_credentials: dict):
        """Test listing systems."""
        tools = mcp_server.config.get_enabled_tools()
        tool_def = next((t for t in tools if t.name == "list_systems"), None)
        assert tool_def is not None

        api_operation = mcp_server.openapi_parser.get_operation(tool_def.operation_id)
        tool_func = mcp_server.tool_generator.generate_tool(tool_def, api_operation)

        result = tool_func(**basic_auth_credentials)

        # Verify result structure
        assert_tool_result(result, expected_keys=["Members"])

    def test_get_system_info(self, mcp_server: RedfishMCPServer, basic_auth_credentials: dict):
        """Test getting system information."""
        tools = mcp_server.config.get_enabled_tools()
        tool_def = next((t for t in tools if t.name == "get_system_info"), None)
        assert tool_def is not None

        api_operation = mcp_server.openapi_parser.get_operation(tool_def.operation_id)
        tool_func = mcp_server.tool_generator.generate_tool(tool_def, api_operation)

        result = tool_func(
            **basic_auth_credentials,
            system_id="System.Embedded.1"
        )

        # Verify result structure
        assert_tool_result(result, expected_keys=["Id", "Name", "PowerState", "Model"])

    @pytest.mark.mock_only
    def test_reset_system(self, mcp_server: RedfishMCPServer, basic_auth_credentials: dict):
        """Test system reset operation (mock only - destructive in live mode)."""
        tools = mcp_server.config.get_enabled_tools()
        tool_def = next((t for t in tools if t.name == "reset_system"), None)
        assert tool_def is not None

        api_operation = mcp_server.openapi_parser.get_operation(tool_def.operation_id)
        tool_func = mcp_server.tool_generator.generate_tool(tool_def, api_operation)

        result = tool_func(
            **basic_auth_credentials,
            system_id="System.Embedded.1",
            reset_type="On"
        )

        # Verify result
        assert result is not None
        assert isinstance(result, dict)

    def test_tool_with_token_auth(self, mcp_server: RedfishMCPServer, token_auth_credentials: dict):
        """Test tool execution with token auth."""
        tools = mcp_server.config.get_enabled_tools()
        tool_def = next((t for t in tools if t.name == "get_system_info"), None)
        assert tool_def is not None

        api_operation = mcp_server.openapi_parser.get_operation(tool_def.operation_id)
        tool_func = mcp_server.tool_generator.generate_tool(tool_def, api_operation)

        result = tool_func(
            **token_auth_credentials,
            system_id="System.Embedded.1"
        )

        assert_tool_result(result, expected_keys=["Id", "Name"])


class TestParameterMapping:
    """Test parameter mapping and validation."""

    def test_required_parameter_provided(self, mcp_server: RedfishMCPServer, basic_auth_credentials: dict):
        """Test that required parameters work correctly."""
        tools = mcp_server.config.get_enabled_tools()
        tool_def = next((t for t in tools if t.name == "get_system_info"), None)
        api_operation = mcp_server.openapi_parser.get_operation(tool_def.operation_id)
        tool_func = mcp_server.tool_generator.generate_tool(tool_def, api_operation)

        # Should succeed with required parameter
        result = tool_func(
            **basic_auth_credentials,
            system_id="System.Embedded.1"
        )

        assert result is not None

    def test_default_parameter_value(self, mcp_server: RedfishMCPServer, basic_auth_credentials: dict):
        """Test that default parameter values are used."""
        tools = mcp_server.config.get_enabled_tools()
        tool_def = next((t for t in tools if t.name == "get_system_info"), None)
        api_operation = mcp_server.openapi_parser.get_operation(tool_def.operation_id)
        tool_func = mcp_server.tool_generator.generate_tool(tool_def, api_operation)

        # system_id has default value "System.Embedded.1"
        result = tool_func(**basic_auth_credentials)

        assert result is not None

    def test_invalid_reset_type(self, mcp_server: RedfishMCPServer, basic_auth_credentials: dict):
        """Test that invalid parameter values are rejected."""
        tools = mcp_server.config.get_enabled_tools()
        tool_def = next((t for t in tools if t.name == "reset_system"), None)
        api_operation = mcp_server.openapi_parser.get_operation(tool_def.operation_id)
        tool_func = mcp_server.tool_generator.generate_tool(tool_def, api_operation)

        from src.clients.redfish_client import RedfishAPIError

        # Invalid ResetType should be rejected by iDRAC
        with pytest.raises(RedfishAPIError):
            tool_func(
                **basic_auth_credentials,
                system_id="System.Embedded.1",
                reset_type="InvalidResetType"
            )


class TestRawJsonResponse:
    """Test raw JSON response structure."""

    def test_raw_json_response_structure(self, mcp_server: RedfishMCPServer, basic_auth_credentials: dict):
        """Test that responses return raw JSON dict."""
        tools = mcp_server.config.get_enabled_tools()
        tool_def = next((t for t in tools if t.name == "get_system_info"), None)
        api_operation = mcp_server.openapi_parser.get_operation(tool_def.operation_id)
        tool_func = mcp_server.tool_generator.generate_tool(tool_def, api_operation)

        result = tool_func(
            **basic_auth_credentials,
            system_id="System.Embedded.1"
        )

        # Result should be a dictionary (raw JSON from API)
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_raw_json_response_content(self, mcp_server: RedfishMCPServer, basic_auth_credentials: dict):
        """Test that raw JSON response contains expected fields."""
        tools = mcp_server.config.get_enabled_tools()
        tool_def = next((t for t in tools if t.name == "get_system_info"), None)
        api_operation = mcp_server.openapi_parser.get_operation(tool_def.operation_id)
        tool_func = mcp_server.tool_generator.generate_tool(tool_def, api_operation)

        result = tool_func(
            **basic_auth_credentials,
            system_id="System.Embedded.1"
        )

        # Should contain expected Redfish fields
        assert "Id" in result or "@odata.id" in result
        assert "Name" in result or "@odata.type" in result


class TestErrorHandling:
    """Test error handling in tool execution."""

    @pytest.mark.mock_only
    def test_not_found_error(self, mcp_server: RedfishMCPServer, basic_auth_credentials: dict):
        """Test handling of 404 not found errors."""
        tools = mcp_server.config.get_enabled_tools()
        tool_def = next((t for t in tools if t.name == "get_system_info"), None)
        api_operation = mcp_server.openapi_parser.get_operation(tool_def.operation_id)
        tool_func = mcp_server.tool_generator.generate_tool(tool_def, api_operation)

        from src.clients.redfish_client import RedfishAPIError

        # Non-existent system ID
        with pytest.raises(RedfishAPIError):
            tool_func(
                **basic_auth_credentials,
                system_id="NonExistent.System.999"
            )

    def test_missing_idrac_ip(self, mcp_server: RedfishMCPServer):
        """Test that missing idrac_ip raises error."""
        tools = mcp_server.config.get_enabled_tools()
        tool_def = next((t for t in tools if t.name == "get_system_info"), None)
        api_operation = mcp_server.openapi_parser.get_operation(tool_def.operation_id)
        tool_func = mcp_server.tool_generator.generate_tool(tool_def, api_operation)

        # Missing required parameter raises TypeError
        with pytest.raises(TypeError, match="idrac_ip"):
            tool_func(username="admin", password="password")
