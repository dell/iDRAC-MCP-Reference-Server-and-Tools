# Integration Test Suite

Integration tests for the Dell iDRAC Redfish MCP Server project.

## Overview

This test suite verifies the complete system works correctly from client through server to iDRAC API and back. It supports both **mock testing** and **live testing** (against real iDRAC hardware).


## Test Structure

```
integration_tests/
├── __init__.py
├── conftest.py                    # Pytest fixtures and configuration
├── config/
│   ├── test_config.yaml          # Test server configuration
│   └── mock_responses.json       # Mock iDRAC API responses
├── utils/
│   ├── mock_idrac.py             # Mock iDRAC HTTP server
│   └── test_helpers.py           # Helper functions
├── test_server_startup.py        # Server initialization tests
├── test_authentication.py        # Authentication tests
└── test_tool_execution.py        # Tool execution tests
```

## Quick Start

### 1. Navigate to Integration Tests Directory

```bash
cd integration_tests
```

### 2. Install Dependencies

```bash
pip install -r requirements-integration-test.txt
```

### 3. Run Tests (Mock Mode)

```bash
# Run all tests with mock iDRAC
./run_integration_tests.sh

# Show tool help
./run_integration_tests.sh --help

# Run with verbose output
./run_integration_tests.sh --verbose

# Run with coverage report
./run_integration_tests.sh --coverage
```

### 4. Run Tests (Live Mode)

```bash
# Set environment variables
export INTEGRATION_TEST_MODE=live
export IDRAC_IP=192.168.1.100
export IDRAC_USERNAME=admin
export IDRAC_PASSWORD=password123

# Or use token auth
export IDRAC_AUTH_TOKEN=your-x-auth-token

# Run tests
./run_integration_tests.sh --live
```

## License

Licensed under the Apache License, Version 2.0
