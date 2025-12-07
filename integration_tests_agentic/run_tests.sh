#!/bin/bash
# Quick test runner for agentic integration tests

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Agentic Integration Test Runner${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Parse arguments
TIER="tier1"
VERBOSE=""
MODE="mock"

while [[ $# -gt 0 ]]; do
    case $1 in
        --tier1)
            TIER="tier1"
            shift
            ;;
        --tier2)
            TIER="tier2"
            shift
            ;;
        --tier3)
            TIER="tier3"
            shift
            ;;
        --smoke)
            TIER="smoke"
            shift
            ;;
        --all)
            TIER="all"
            shift
            ;;
        --live)
            MODE="live"
            export INTEGRATION_TEST_MODE=live
            shift
            ;;
        --verbose|-v)
            VERBOSE="-v -s"
            shift
            ;;
        --help|-h)
            echo "Agentic Test Runner"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --smoke      Run smoke tests only (critical)"
            echo "  --tier1      Run tier 1 tests (fast, local models)"
            echo "  --tier2      Run tier 2 tests (thorough, cloud models)"
            echo "  --tier3      Run tier 3 tests (acceptance, best models)"
            echo "  --all        Run all tests"
            echo "  --live       Run against live iDRAC (requires env vars)"
            echo "  --verbose|-v Verbose output with agent traces"
            echo "  --help|-h    Show this help message"
            echo ""
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Display configuration
if [ "$MODE" = "live" ]; then
    echo -e "${YELLOW}[MODE] Live testing against real iDRAC${NC}"
    echo ""

    if [ -z "$IDRAC_IP" ]; then
        echo -e "${RED}[ERROR] IDRAC_IP not set. Required for live mode.${NC}"
        echo "Set with: export IDRAC_IP=192.168.1.100"
        exit 1
    fi

    echo -e "${GREEN}[INFO] iDRAC IP: $IDRAC_IP${NC}"
else
    echo -e "${GREEN}[MODE] Mock testing (no real iDRAC required)${NC}"
fi

echo -e "${GREEN}[TIER] Running: $TIER${NC}"
echo ""

# Check dependencies
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}[ERROR] pytest is not installed${NC}"
    echo -e "${YELLOW}[INFO] Install with: pip install -r requirements.txt${NC}"
    exit 1
fi

# Check if MCP server is running (required for integration tests)
echo -e "${YELLOW}[INFO] Checking for MCP server...${NC}"
MCP_SERVER_URL="${MCP_SERVER_URL:-http://127.0.0.1:8000}"

if ! curl -s "${MCP_SERVER_URL}/mcp" > /dev/null 2>&1; then
    echo -e "${RED}[ERROR] MCP server is not running at ${MCP_SERVER_URL}${NC}"
    echo ""
    echo -e "${YELLOW}[INFO] The agentic integration tests require a running MCP server.${NC}"
    echo -e "${YELLOW}[INFO] Please start the full test environment with:${NC}"
    echo -e "${YELLOW}       ./start_chat_ui.sh${NC}"
    echo ""
    echo -e "${YELLOW}[INFO] Or start just the MCP server manually:${NC}"
    echo -e "${YELLOW}       cd ../mcp_idrac_server${NC}"
    echo -e "${YELLOW}       python3 -m src --transport streamable-http --port 8000${NC}"
    echo ""
    exit 1
fi

echo -e "${GREEN}[INFO] MCP server is running at ${MCP_SERVER_URL}${NC}"
echo ""

# Run tests based on tier
case $TIER in
    smoke)
        echo -e "${GREEN}[INFO] Running smoke tests (critical)...${NC}"
        pytest $VERBOSE -m smoke scenarios/test_smoke.py
        ;;
    tier1)
        echo -e "${GREEN}[INFO] Running Tier 1 tests...${NC}"
        pytest $VERBOSE -m tier1
        ;;
    tier2)
        echo -e "${GREEN}[INFO] Running Tier 2 tests...${NC}"
        pytest $VERBOSE -m tier2
        ;;
    tier3)
        echo -e "${GREEN}[INFO] Running Tier 3 tests...${NC}"
        pytest $VERBOSE -m tier3
        ;;
    all)
        echo -e "${GREEN}[INFO] Running all agentic tests...${NC}"
        pytest $VERBOSE
        ;;
esac

# Check exit code
EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  All Tests Passed!${NC}"
    echo -e "${GREEN}========================================${NC}"
else
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}  Tests Failed${NC}"
    echo -e "${RED}========================================${NC}"
fi

exit $EXIT_CODE
