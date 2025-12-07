# Licensed to You under the Apache License, Version 2.0

"""Helper functions for integration tests."""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent.parent


def add_to_path(subdir: str) -> None:
    """
    Add a subdirectory to Python path.

    Args:
        subdir: Subdirectory name (e.g., 'mcp_idrac_server', 'mcp_client_examples')
    """
    project_root = get_project_root()
    target_path = project_root / subdir

    if target_path.exists() and str(target_path) not in sys.path:
        sys.path.insert(0, str(target_path))


def get_test_config_path() -> Path:
    """Get path to test configuration file."""
    return get_project_root() / 'integration_tests' / 'config' / 'test_config.yaml'


def get_openapi_spec_path() -> Path:
    """Get path to OpenAPI specification."""
    return get_project_root() / 'mcp_idrac_server' / 'config' / 'openapi.yaml'


def is_live_mode() -> bool:
    """
    Check if tests should run in live mode (against real iDRAC).

    Set environment variable INTEGRATION_TEST_MODE=live to enable.

    Returns:
        True if live mode, False for mock mode
    """
    return os.getenv('INTEGRATION_TEST_MODE', 'mock').lower() == 'live'


def get_live_idrac_config() -> Optional[Dict[str, str]]:
    """
    Get live iDRAC configuration from environment variables.

    Required environment variables for live mode:
    - IDRAC_IP: iDRAC IP address
    - IDRAC_USERNAME: iDRAC username
    - IDRAC_PASSWORD or IDRAC_AUTH_TOKEN: Credentials

    Returns:
        Dictionary with iDRAC connection info, or None if not configured
    """
    if not is_live_mode():
        return None

    idrac_ip = os.getenv('IDRAC_IP')
    username = os.getenv('IDRAC_USERNAME')
    password = os.getenv('IDRAC_PASSWORD')
    auth_token = os.getenv('IDRAC_AUTH_TOKEN')

    if not idrac_ip:
        raise ValueError("IDRAC_IP environment variable is required for live mode")

    if not (username and password) and not auth_token:
        raise ValueError(
            "Either (IDRAC_USERNAME and IDRAC_PASSWORD) or IDRAC_AUTH_TOKEN "
            "is required for live mode"
        )

    config = {"idrac_ip": idrac_ip}

    if auth_token:
        config["auth_token"] = auth_token
    else:
        config["username"] = username
        config["password"] = password

    return config


def wait_for_server(url: str, timeout: int = 10, interval: float = 0.5) -> bool:
    """
    Wait for a server to become available.

    Args:
        url: URL to check
        timeout: Maximum time to wait in seconds
        interval: Time between checks in seconds

    Returns:
        True if server is available, False if timeout
    """
    import time
    import requests

    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            response = requests.get(url, timeout=2)
            if response.status_code < 500:  # Any response except server error
                return True
        except requests.exceptions.RequestException:
            pass

        time.sleep(interval)

    return False


def assert_tool_result(result: Dict[str, Any], expected_keys: list = None) -> None:
    """
    Assert that a tool result is valid.

    Args:
        result: Tool execution result
        expected_keys: Optional list of expected keys in result
    """
    assert isinstance(result, dict), f"Result should be dict, got {type(result)}"

    # If formatting is enabled, check for formatted response
    if 'formatted' in result:
        assert isinstance(result['formatted'], str), "Formatted output should be string"
        assert len(result['formatted']) > 0, "Formatted output should not be empty"

    # Check expected keys if provided
    if expected_keys:
        # If result has 'raw' key with data (when include_raw_json=true), check that
        # Otherwise, if result has 'formatted' key, we can't check individual keys
        # Otherwise, check the result itself (when formatting is disabled)
        if 'raw' in result and result['raw'] is not None:
            data_to_check = result['raw']
        elif 'formatted' in result:
            # When formatting is enabled but include_raw_json=false,
            # we can only verify that formatted text contains the expected keys as strings
            formatted_text = result['formatted']
            for key in expected_keys:
                assert key in formatted_text, f"Expected key '{key}' not found in formatted output"
            return  # Don't check dict keys since we don't have the raw data
        else:
            data_to_check = result

        # Check keys in the data
        if 'formatted' not in result:  # Only check dict keys if not formatted
            for key in expected_keys:
                assert key in data_to_check, f"Expected key '{key}' not found in result"


def print_test_info(test_name: str, mode: str = None) -> None:
    """
    Print test information banner.

    Args:
        test_name: Name of the test
        mode: Test mode (mock/live)
    """
    if mode is None:
        mode = "LIVE" if is_live_mode() else "MOCK"

    print("\n" + "=" * 80)
    print(f"TEST: {test_name}")
    print(f"MODE: {mode}")
    print("=" * 80)
