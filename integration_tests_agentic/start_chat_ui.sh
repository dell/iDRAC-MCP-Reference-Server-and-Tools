#!/bin/bash
# Startup script for multi-process agentic integration test architecture
#
# Architecture:
#   1. Mock iDRAC Server (port 8002) OR Live iDRAC
#   2. MCP Server (port 8000) - Dell iDRAC Redfish MCP Server
#   3. Agent Orchestrator (port 8001) - LangChain ReAct Agent with MCP + RAG tools
#   4. Chat UI (port 8501) - Streamlit web interface

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                                                                ║${NC}"
echo -e "${BLUE}║     Agentic Integration Test - Multi-Process Startup          ║${NC}"
echo -e "${BLUE}║                                                                ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if running from correct directory
if [ ! -f "agent_orchestrator_server.py" ]; then
    echo -e "${RED}[ERROR] Must run from integration_tests_agentic directory${NC}"
    exit 1
fi

# Check dependencies
echo -e "${YELLOW}[INFO] Checking dependencies...${NC}"

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[ERROR] python3 is not installed${NC}"
    exit 1
fi

if ! python3 -c "import streamlit" 2>/dev/null; then
    echo -e "${RED}[ERROR] streamlit is not installed${NC}"
    echo -e "${YELLOW}[INFO] Install with: pip install streamlit${NC}"
    exit 1
fi

if ! python3 -c "import fastapi" 2>/dev/null; then
    echo -e "${RED}[ERROR] fastapi is not installed${NC}"
    echo -e "${YELLOW}[INFO] Install with: pip install -r requirements.txt${NC}"
    exit 1
fi

echo -e "${GREEN}[INFO] Dependencies OK${NC}"
echo ""


# Parse arguments
MODE="live"
VERBOSE=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --live)
            MODE="live"
            export INTEGRATION_TEST_MODE=live
            shift
            ;;
        --verbose|-v)
            VERBOSE="true"
            shift
            ;;
        --help|-h)
            echo "Multi-Process Agentic Test Startup Script"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --live       Use live iDRAC (requires env vars)"
            echo "  --verbose|-v Enable verbose logging"
            echo "  --help|-h    Show this help message"
            echo ""
            echo "Environment Variables:"
            echo "  LLM Configuration (dev_genai is default):"
            echo "    DEV_GENAI_API_URL    dev_genai API URL"
            echo "    DEV_GENAI_API_KEY    dev_genai API key"
            echo ""
            echo "  iDRAC Configuration:"
            echo "    INTEGRATION_TEST_MODE  'mock' or 'live' (default: mock)"
            echo "    IDRAC_IP              iDRAC IP address (for live mode)"
            echo "    IDRAC_USERNAME        iDRAC username (for live mode)"
            echo "    IDRAC_PASSWORD        iDRAC password (for live mode)"
            echo ""
            echo "Ports:"
            echo "  8002 - Mock iDRAC Server (mock mode only)"
            echo "  8000 - MCP Server"
            echo "  8001 - Agent Orchestrator"
            echo "  8501 - Chat UI (Streamlit)"
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

# Check for dev_genai credentials (warn if not set)
if [ -z "$DEV_GENAI_API_URL" ] || [ -z "$DEV_GENAI_API_KEY" ]; then
    echo -e "${YELLOW}[WARNING] dev_genai credentials not set${NC}"
    echo -e "${YELLOW}[WARNING] The default LLM provider is 'dev_genai'${NC}"
    echo -e "${YELLOW}[WARNING] Set DEV_GENAI_API_URL and DEV_GENAI_API_KEY or change provider in config/test_config.yaml${NC}"
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo -e "${GREEN}[INFO] dev_genai credentials configured${NC}"
fi

# Display mode
if [ "$MODE" = "live" ]; then
    echo -e "${YELLOW}[MODE] Live testing against real iDRAC${NC}"
    if [ -z "$IDRAC_IP" ]; then
        echo -e "${RED}[ERROR] IDRAC_IP not set for live mode${NC}"
        echo "Set with: export IDRAC_IP=http://192.168.1.100"
        exit 1
    fi
    echo -e "${GREEN}[INFO] iDRAC IP: $IDRAC_IP${NC}"
else
    echo -e "${GREEN}[MODE] Mock testing (no real iDRAC required)${NC}"
fi
echo ""

# Create log directory
mkdir -p logs

# Process ID tracking
MOCK_PID=""
MCP_PID=""
ORCHESTRATOR_PID=""
UI_PID=""

# Trap to cleanup on exit
cleanup() {
    echo -e "\n${YELLOW}[CLEANUP] Shutting down all services...${NC}"

    if [ ! -z "$UI_PID" ]; then
        echo -e "${YELLOW}[CLEANUP] Stopping Chat UI (PID: $UI_PID)${NC}"
        kill $UI_PID 2>/dev/null || true
    fi

    if [ ! -z "$ORCHESTRATOR_PID" ]; then
        echo -e "${YELLOW}[CLEANUP] Stopping Agent Orchestrator (PID: $ORCHESTRATOR_PID)${NC}"
        kill $ORCHESTRATOR_PID 2>/dev/null || true
    fi

    if [ ! -z "$MCP_PID" ]; then
        echo -e "${YELLOW}[CLEANUP] Stopping MCP Server (PID: $MCP_PID)${NC}"
        kill $MCP_PID 2>/dev/null || true
    fi

    if [ ! -z "$MOCK_PID" ]; then
        echo -e "${YELLOW}[CLEANUP] Stopping Mock iDRAC Server (PID: $MOCK_PID)${NC}"
        kill $MOCK_PID 2>/dev/null || true
    fi

    cd ../mcp_idrac_server
    docker-compose down
    cd ../integration_tests_agentic

    sleep 2
    echo -e "${GREEN}[CLEANUP] Done${NC}"
}
trap cleanup EXIT INT TERM

# ============================================================================
# 1. Start Mock iDRAC Server (if in mock mode)
# ============================================================================

if [ "$MODE" = "mock" ]; then
    echo -e "${YELLOW}[STARTUP] Starting Mock iDRAC Server (port 8002)...${NC}"

    python3 mock_idrac_server.py --host 127.0.0.1 --port 8002 > logs/mock_idrac.log 2>&1 &
    MOCK_PID=$!

    echo -e "${GREEN}[STARTUP] Mock iDRAC Server started (PID: $MOCK_PID)${NC}"

    # Wait for mock server to be ready
    echo -e "${YELLOW}[STARTUP] Waiting for Mock iDRAC to initialize...${NC}"
    for i in {1..30}; do
        if curl -s http://127.0.0.1:8002/redfish/v1/ > /dev/null 2>&1; then
            echo -e "${GREEN}[STARTUP] Mock iDRAC Server ready${NC}"
            break
        fi
        if [ $i -eq 30 ]; then
            echo -e "${RED}[ERROR] Mock iDRAC Server failed to start${NC}"
            echo -e "${YELLOW}[INFO] Check logs/mock_idrac.log for details${NC}"
            exit 1
        fi
        sleep 1
    done

    # Set environment for orchestrator to connect to mock
    export IDRAC_IP="http://127.0.0.1:8002"
    export IDRAC_USERNAME="root"
    export IDRAC_PASSWORD="calvin"
fi

echo ""

# ============================================================================
# 2. Start MCP Server
# ============================================================================

echo -e "${YELLOW}[STARTUP] Starting MCP Server (port 8000)...${NC}"

# Navigate to MCP server directory and start it
cd ../mcp_idrac_server
docker-compose up -d
#python3 -m src --transport streamable-http --host 127.0.0.1 --port 8000 > ../integration_tests_agentic/logs/mcp_server.log 2>&1 &
MCP_PID=$!
cd ../integration_tests_agentic

echo -e "${GREEN}[STARTUP] MCP Server started (PID: $MCP_PID)${NC}"

# Wait for MCP server to be ready
echo -e "${YELLOW}[STARTUP] Waiting for MCP Server to initialize...${NC}"
for i in {1..30}; do
    if curl -s http://127.0.0.1:8000/mcp > /dev/null 2>&1; then
        echo -e "${GREEN}[STARTUP] MCP Server ready${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}[ERROR] MCP Server failed to start${NC}"
        echo -e "${YELLOW}[INFO] Check logs/mcp_server.log for details${NC}"
        exit 1
    fi
    sleep 1
done

echo ""

# ============================================================================
# 3. Start Agent Orchestrator
# ============================================================================

echo -e "${YELLOW}[STARTUP] Starting Agent Orchestrator (port 8001)...${NC}"

python3 agent_orchestrator_server.py --host 0.0.0.0 --port 8001 > logs/orchestrator.log 2>&1 &
ORCHESTRATOR_PID=$!

echo -e "${GREEN}[STARTUP] Agent Orchestrator started (PID: $ORCHESTRATOR_PID)${NC}"

# Wait for orchestrator to be ready
echo -e "${YELLOW}[STARTUP] Waiting for Agent Orchestrator to initialize...${NC}"
echo -e "${YELLOW}[STARTUP] (This may take 2-5 minutes on first run for RAG initialization)${NC}"

for i in {1..120}; do
    if curl -s http://localhost:8001/health > /dev/null 2>&1; then
        echo -e "${GREEN}[STARTUP] Agent Orchestrator ready${NC}"
        break
    fi
    if [ $i -eq 120 ]; then
        echo -e "${RED}[ERROR] Agent Orchestrator failed to start${NC}"
        echo -e "${YELLOW}[INFO] Check logs/orchestrator.log for details${NC}"
        exit 1
    fi
    sleep 1
done

echo ""

# ============================================================================
# 4. Start Chat UI (Streamlit)
# ============================================================================

echo -e "${YELLOW}[STARTUP] Starting Chat UI (port 8501)...${NC}"
echo -e "${GREEN}[INFO] Chat UI will open in your browser${NC}"
echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Architecture:${NC}"

if [ "$MODE" = "mock" ]; then
    echo -e "${BLUE}  1. Mock iDRAC:         http://localhost:8002${NC}"
fi

echo -e "${BLUE}  2. MCP Server:         http://localhost:8000/mcp${NC}"
echo -e "${BLUE}  3. Agent Orchestrator: http://localhost:8001${NC}"
echo -e "${BLUE}  4. Chat UI:            http://localhost:8501${NC}"
echo -e "${BLUE}  Mode:                  ${MODE}${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${GREEN}[INFO] Press Ctrl+C to stop all services${NC}"
echo ""

cd chat-ui
streamlit run app.py --server.port 8501 --server.address 0.0.0.0 > ../logs/chat_ui.log 2>&1 &
UI_PID=$!

# Wait for UI or any service to exit
wait
