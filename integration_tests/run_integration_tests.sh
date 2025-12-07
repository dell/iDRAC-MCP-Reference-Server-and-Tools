#!/bin/bash
# Licensed to You under the Apache License, Version 2.0

# Integration Test Runner for Dell iDRAC Redfish MCP Server
#
# Usage:
#   ./run_integration_tests.sh              # Run all tests in mock mode
#   ./run_integration_tests.sh --live       # Run tests against live iDRAC
#   ./run_integration_tests.sh --coverage   # Run with coverage report
#   ./run_integration_tests.sh --verbose    # Run with verbose output

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Default values
TEST_MODE="mock"
COVERAGE=false
VERBOSE=""
PYTEST_ARGS=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --live)
            TEST_MODE="live"
            shift
            ;;
        --coverage)
            COVERAGE=true
            shift
            ;;
        --verbose|-v)
            VERBOSE="-v"
            shift
            ;;
        --help|-h)
            echo "Integration Test Runner"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --live        Run tests against live iDRAC (requires env vars)"
            echo "  --coverage    Generate coverage report"
            echo "  --verbose|-v  Verbose output"
            echo "  --help|-h     Show this help message"
            echo ""
            echo "Environment variables for live mode:"
            echo "  IDRAC_IP              iDRAC IP address"
            echo "  IDRAC_USERNAME        iDRAC username"
            echo "  IDRAC_PASSWORD        iDRAC password"
            echo "  or"
            echo "  IDRAC_AUTH_TOKEN      iDRAC auth token"
            echo ""
            exit 0
            ;;
        *)
            PYTEST_ARGS="$PYTEST_ARGS $1"
            shift
            ;;
    esac
done

# Print banner
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Integration Test Suite${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Set test mode
export INTEGRATION_TEST_MODE=$TEST_MODE

if [ "$TEST_MODE" = "live" ]; then
    echo -e "${YELLOW}[MODE] Live testing against real iDRAC${NC}"
    echo ""

    # Validate environment variables
    if [ -z "$IDRAC_IP" ]; then
        echo -e "${RED}[ERROR] IDRAC_IP environment variable is required for live mode${NC}"
        exit 1
    fi

    if [ -z "$IDRAC_AUTH_TOKEN" ] && ([ -z "$IDRAC_USERNAME" ] || [ -z "$IDRAC_PASSWORD" ]); then
        echo -e "${RED}[ERROR] Either IDRAC_AUTH_TOKEN or (IDRAC_USERNAME and IDRAC_PASSWORD) required${NC}"
        exit 1
    fi

    echo -e "${GREEN}[INFO] iDRAC IP: $IDRAC_IP${NC}"
    echo ""
else
    echo -e "${GREEN}[MODE] Mock testing (no real iDRAC required)${NC}"
    echo ""
fi

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}[ERROR] pytest is not installed${NC}"
    echo -e "${YELLOW}[INFO] Install with: pip install -r requirements-integration-test.txt${NC}"
    exit 1
fi

# Build pytest command (run from integration_tests directory)
PYTEST_CMD="pytest . $VERBOSE $PYTEST_ARGS"

if [ "$COVERAGE" = true ]; then
    echo -e "${GREEN}[INFO] Running with coverage report${NC}"
    PYTEST_CMD="$PYTEST_CMD --cov=../mcp_idrac_server/src --cov=../mcp_client_examples/client --cov-report=html --cov-report=term"
fi

echo -e "${GREEN}[INFO] Running tests...${NC}"
echo ""

# Run tests
$PYTEST_CMD

# Check exit code
EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  All Tests Passed!${NC}"
    echo -e "${GREEN}========================================${NC}"

    if [ "$COVERAGE" = true ]; then
        echo ""
        echo -e "${BLUE}[INFO] Coverage report generated at: htmlcov/index.html${NC}"
    fi
else
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}  Tests Failed${NC}"
    echo -e "${RED}========================================${NC}"
fi

exit $EXIT_CODE
