# Licensed to You under the Apache License, Version 2.0

"""
Pytest configuration and fixtures for integration tests.

This module provides fixtures for:
- Mock iDRAC server (for CI/CD and automated testing)
- MCP server instance
- Test credentials and configuration
"""

import pytest
import time
import sys
from pathlib import Path
from typing import Generator, Dict

# Add project paths to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / 'mcp_idrac_server'))
sys.path.insert(0, str(Path(__file__).parent))  # Add integration_tests to path

from utils.test_helpers import (
    is_live_mode,
    get_live_idrac_config,
    get_test_config_path,
    get_openapi_spec_path,
)
from utils.mock_idrac import MockiDRACServer

# Import server components
from src.server.mcp_server import RedfishMCPServer


@pytest.fixture(scope="session")
def test_mode() -> str:
    """
    Get the test mode (mock or live).

    Returns:
        'mock' or 'live'
    """
    return "live" if is_live_mode() else "mock"


@pytest.fixture(scope="session")
def mock_idrac_server(test_mode: str) -> Generator[MockiDRACServer, None, None]:
    """
    Provide mock iDRAC server for testing.

    Only starts in mock mode. In live mode, returns None.

    Yields:
        MockiDRACServer instance or None
    """
    if test_mode == "live":
        print("[INFO] Running in LIVE mode - skipping mock iDRAC server")
        yield None
        return

    print("[INFO] Starting mock iDRAC server...")
    server = MockiDRACServer(host="127.0.0.1", port=8888)
    server.start()

    # Wait for server to be ready
    time.sleep(1)

    yield server

    print("[INFO] Stopping mock iDRAC server...")
    server.stop()


@pytest.fixture(scope="session")
def idrac_connection_info(test_mode: str, mock_idrac_server: MockiDRACServer) -> Dict[str, str]:
    """
    Get iDRAC connection information for tests.

    Returns:
        Dictionary with idrac_ip and credentials
    """
    if test_mode == "live":
        print("[INFO] Using live iDRAC configuration")
        config = get_live_idrac_config()
        if not config:
            pytest.skip("Live iDRAC configuration not available")
        return config
    else:
        print("[INFO] Using mock iDRAC server")
        # Return http://host:port for mock server
        # Include http:// prefix since mock server doesn't support https
        return {
            "idrac_ip": f"http://{mock_idrac_server.host}:{mock_idrac_server.port}",
            **mock_idrac_server.get_credentials("basic")
        }


@pytest.fixture(scope="session")
def mcp_server(test_mode: str, mock_idrac_server: MockiDRACServer) -> Generator[RedfishMCPServer, None, None]:
    """
    Provide MCP server instance for testing.

    Yields:
        RedfishMCPServer instance
    """
    print("[INFO] Initializing MCP server...")

    openapi_file = str(get_openapi_spec_path())
    config_file = str(get_test_config_path())

    server = RedfishMCPServer(
        openapi_file=openapi_file,
        tools_config_file=config_file,
        server_name="test-idrac-server"
    )

    print(f"[INFO] MCP server initialized with {len(server.config.get_enabled_tools())} tools")

    yield server

    print("[INFO] MCP server shutdown")


# Note: mcp_client fixture removed as tests directly call tool functions
# For true end-to-end testing with client, see mcp_client_examples/


@pytest.fixture
def basic_auth_credentials(idrac_connection_info: Dict[str, str]) -> Dict[str, str]:
    """
    Get basic authentication credentials.

    Returns:
        Dictionary with idrac_ip, username, and password
    """
    return {
        "idrac_ip": idrac_connection_info["idrac_ip"],
        "username": idrac_connection_info.get("username", "admin"),
        "password": idrac_connection_info.get("password", "password123")
    }


@pytest.fixture
def token_auth_credentials(test_mode: str, mock_idrac_server: MockiDRACServer) -> Dict[str, str]:
    """
    Get token authentication credentials.

    Returns:
        Dictionary with idrac_ip and auth_token
    """
    if test_mode == "live":
        config = get_live_idrac_config()
        if "auth_token" not in config:
            pytest.skip("Token authentication not configured for live mode")
        return {
            "idrac_ip": config["idrac_ip"],
            "auth_token": config["auth_token"]
        }
    else:
        # Return http://host:port for mock server
        # Include http:// prefix since mock server doesn't support https
        return {
            "idrac_ip": f"http://{mock_idrac_server.host}:{mock_idrac_server.port}",
            **mock_idrac_server.get_credentials("token")
        }


# Test markers
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "live_only: mark test to run only in live mode"
    )
    config.addinivalue_line(
        "markers", "mock_only: mark test to run only in mock mode"
    )


def pytest_collection_modifyitems(config, items):
    """Skip tests based on test mode."""
    test_mode = "live" if is_live_mode() else "mock"

    for item in items:
        if "live_only" in item.keywords and test_mode != "live":
            item.add_marker(pytest.mark.skip(reason="Test requires live iDRAC"))
        elif "mock_only" in item.keywords and test_mode != "mock":
            item.add_marker(pytest.mark.skip(reason="Test requires mock mode"))
