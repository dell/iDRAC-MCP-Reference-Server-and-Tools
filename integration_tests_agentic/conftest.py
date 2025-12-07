# Licensed to You under the Apache License, Version 2.0

"""
Pytest Configuration and Fixtures for Agentic Integration Tests

Provides fixtures for:
- MCP server setup
- LangChain agent creation
- Mock iDRAC server
- Test configuration
"""

import pytest
import sys
from pathlib import Path
from typing import Generator, Dict, List

# Add paths for imports
# Import from the original integration_tests folder to reuse CI/CD code
sys.path.insert(0, str(Path(__file__).parent))  # integration_tests_agentic
sys.path.insert(0, str(Path(__file__).parent.parent / 'integration_tests'))  # integration_tests (for reuse)

# Import mock_idrac and test_helpers from integration_tests (reusing CI/CD code)
from utils.mock_idrac import MockiDRACServer
from utils.test_helpers import (
    is_live_mode,
    get_live_idrac_config
)

# Now remove integration_tests from path to avoid shadowing
sys.path.pop(0)

# Import local utils from integration_tests_agentic
from utils.mcp_client import MCPClient
from utils.mcp_langchain_adapter import create_mcp_agent_tools
from utils.test_runner import AgentRunner, load_test_config
from langchain_core.tools import BaseTool
from typing import Any
import os
import time


# ============================================================================
# Test Mode and Configuration
# ============================================================================

@pytest.fixture(scope="session")
def test_mode() -> str:
    """
    Get the test mode (mock or live).

    Returns:
        'mock' or 'live'
    """
    return "live" if is_live_mode() else "mock"


@pytest.fixture(scope="session")
def agentic_test_config() -> Dict:
    """
    Load agentic test configuration.

    Returns:
        Configuration dictionary
    """
    return load_test_config()


# ============================================================================
# Mock iDRAC Server
# ============================================================================

@pytest.fixture(scope="session")
def mock_idrac_server(test_mode: str) -> Generator[MockiDRACServer, None, None]:
    """
    Provide mock iDRAC server for testing.

    Only starts in mock mode. In live mode, returns None.

    Yields:
        MockiDRACServer instance or None
    """
    if test_mode == "mock":
        print("\n[INFO] Starting mock iDRAC server for agentic tests...")
        server = MockiDRACServer()
        server.start()
        yield server
        print("\n[INFO] Stopping mock iDRAC server...")
        server.stop()
    else:
        # Live mode - no mock server needed
        yield None


# ============================================================================
# MCP Client
# ============================================================================

@pytest.fixture(scope="session")
def mcp_client() -> Generator[MCPClient, None, None]:
    """
    Provide MCP client connected to running MCP server.

    The MCP server must be running on port 8000 before tests start.
    Use start_chat_ui.sh or start the MCP server manually.

    Yields:
        MCPClient instance
    """
    print("\n[INFO] Connecting to MCP server for agentic tests...")

    # Get MCP server URL from environment
    mcp_server_url = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8000")

    # Create client
    client = MCPClient(base_url=mcp_server_url, timeout=60)

    # Connect to server
    max_retries = 5
    for i in range(max_retries):
        try:
            client.connect()  # This establishes the connection
            tools = client.list_tools()
            print(f"[INFO] Connected to MCP server with {len(tools)} tools")
            break
        except Exception as e:
            if i == max_retries - 1:
                raise Exception(
                    f"Failed to connect to MCP server at {mcp_server_url}. "
                    "Please ensure the MCP server is running (start_chat_ui.sh or manually start it)."
                ) from e
            print(f"[INFO] Waiting for MCP server to be ready... ({i+1}/{max_retries})")
            time.sleep(2)

    yield client

    print("\n[INFO] Closing MCP client connection")
    client.close()


# ============================================================================
# Credentials
# ============================================================================

@pytest.fixture(scope="session")
def test_credentials(test_mode: str, mock_idrac_server: MockiDRACServer) -> Dict[str, str]:
    """
    Get test credentials based on test mode.

    Args:
        test_mode: Test mode (mock or live)
        mock_idrac_server: Mock server instance (None in live mode)

    Returns:
        Dictionary with credentials
    """
    if test_mode == "live":
        config = get_live_idrac_config()
        return {
            "idrac_ip": config["idrac_ip"],
            "username": config.get("username"),
            "password": config.get("password"),
            "auth_token": config.get("auth_token"),
        }
    else:
        # Mock mode
        return {
            "idrac_ip": f"http://{mock_idrac_server.host}:{mock_idrac_server.port}",
            **mock_idrac_server.get_credentials("basic")
        }


# ============================================================================
# LangChain Tools
# ============================================================================

@pytest.fixture(scope="session")
def langchain_tools(mcp_client: MCPClient, test_credentials: Dict[str, str]) -> List[BaseTool]:
    """
    Create LangChain tools from MCP client.

    Args:
        mcp_client: MCP client instance
        test_credentials: Test credentials

    Returns:
        List of LangChain tools
    """
    print("\n[INFO] Fetching tools from MCP server and converting to LangChain format...")
    tools = create_mcp_agent_tools(mcp_client, test_credentials)
    print(f"[INFO] Created {len(tools)} LangChain tools")
    return tools


# ============================================================================
# Agent Runner
# ============================================================================

@pytest.fixture(scope="session")
def agent_runner(agentic_test_config: Dict) -> AgentRunner:
    """
    Create agent runner instance.

    Args:
        agentic_test_config: Test configuration

    Returns:
        AgentRunner instance
    """
    print(f"\n[INFO] Creating agent runner with provider: {agentic_test_config['llm']['provider']}")
    return AgentRunner(agentic_test_config)


# ============================================================================
# Agent Executor
# ============================================================================

@pytest.fixture
def agent_executor(agent_runner: AgentRunner, langchain_tools: List[BaseTool]) -> Any:
    """
    Create agent executor for tests.

    This is function-scoped so each test gets a fresh agent.

    Args:
        agent_runner: Agent runner instance
        langchain_tools: LangChain tools

    Returns:
        LangGraph agent (compiled graph)
    """
    return agent_runner.create_agent(langchain_tools)


# ============================================================================
# Pytest Configuration
# ============================================================================

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "agentic: mark test as an agentic integration test"
    )
    config.addinivalue_line(
        "markers", "tier1: fast smoke tests"
    )
    config.addinivalue_line(
        "markers", "tier2: thorough integration tests"
    )
    config.addinivalue_line(
        "markers", "tier3: acceptance tests"
    )
    config.addinivalue_line(
        "markers", "smoke: smoke test (critical)"
    )
    config.addinivalue_line(
        "markers", "workflow: multi-step workflow test"
    )
    config.addinivalue_line(
        "markers", "mock_only: only run in mock mode"
    )
    config.addinivalue_line(
        "markers", "live_only: only run in live mode"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to handle test mode filtering."""
    test_mode = "live" if is_live_mode() else "mock"

    for item in items:
        # Skip mock_only tests in live mode
        if "mock_only" in item.keywords and test_mode == "live":
            item.add_marker(pytest.mark.skip(reason="mock_only test skipped in live mode"))

        # Skip live_only tests in mock mode
        if "live_only" in item.keywords and test_mode == "mock":
            item.add_marker(pytest.mark.skip(reason="live_only test skipped in mock mode"))
