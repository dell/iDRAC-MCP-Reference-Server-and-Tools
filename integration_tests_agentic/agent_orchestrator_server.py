#!/usr/bin/env python3
# Licensed to You under the Apache License, Version 2.0

"""
Agent Orchestrator Service

LangChain ReAct agent with MCP tools and RAG capabilities.
Runs as a standalone HTTP service.
"""

import sys
import os
import logging
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid

# Configure logging with timestamps
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Add paths for imports
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Import from integration_tests_agentic utils
from utils.mcp_client import MCPClient
from utils.test_runner import AgentRunner, load_test_config
from utils.rag_tool import create_rag_tool, RAGConfig
from utils.credential_manager import CredentialDatabase


# =============================================================================
# Request/Response Models
# =============================================================================

class AgentRequest(BaseModel):
    """Request to agent orchestrator."""
    input: str
    conversation_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class AgentResponse(BaseModel):
    """Response from agent orchestrator."""
    output: str
    conversation_id: str
    timestamp: str
    success: bool = True
    metadata: Optional[Dict[str, Any]] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: str
    components: Dict[str, bool]


class ToolsResponse(BaseModel):
    """Available tools response."""
    tools: List[Dict[str, Any]]
    count: int


# =============================================================================
# Global State
# =============================================================================

# Conversation history (in-memory, replace with Redis/DB for production)
conversations: Dict[str, List[Dict[str, Any]]] = {}

# Agent components
mcp_client: Optional[MCPClient] = None
agent_runner: Optional[AgentRunner] = None
agent_executor = None
credential_db: Optional[CredentialDatabase] = None


# =============================================================================
# FastAPI Application
# =============================================================================

app = FastAPI(
    title="Agent Orchestrator Service",
    description="LangChain ReAct agent with MCP tools and RAG capabilities",
    version="1.0.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Startup/Shutdown
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize agent orchestrator on startup."""
    global mcp_client, agent_runner, agent_executor, credential_db

    startup_start = datetime.now()
    logger.info("=" * 80)
    logger.info("STARTUP: Initializing Agent Orchestrator Service...")
    logger.info(f"STARTUP: Start time: {startup_start.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 80)

    # Load configuration
    step_start = datetime.now()
    test_config = load_test_config()
    logger.info(f"STARTUP: [+{(datetime.now() - step_start).total_seconds():.2f}s] Configuration loaded")

    # Initialize credential database (shared with chat UI)
    # Database path can be configured via environment variable
    step_start = datetime.now()
    db_path = os.getenv("CREDENTIAL_DB_PATH", os.path.expanduser("~/.idrac_credentials.db"))
    master_password = os.getenv("CREDENTIAL_MASTER_PASSWORD")  # Optional encryption password

    logger.info(f"STARTUP: Initializing credential database at: {db_path}")
    credential_db = CredentialDatabase(db_path=db_path, master_password=master_password)
    logger.info(f"STARTUP: [+{(datetime.now() - step_start).total_seconds():.2f}s] Credential database initialized")

    # Log available systems
    systems = credential_db.list_credentials()
    if systems:
        logger.info(f"Found {len(systems)} configured systems in database:")
        for sys in systems:
            logger.info(f"  - {sys['system_id']}: {sys['idrac_ip']}")
    else:
        logger.warning("No systems configured in credential database!")
        logger.warning("Use the Chat UI to add iDRAC systems, or set environment variables for backwards compatibility")

        # Backwards compatibility: if no systems in DB, try environment variables
        idrac_ip = os.getenv("IDRAC_IP")
        idrac_username = os.getenv("IDRAC_USERNAME")
        idrac_password = os.getenv("IDRAC_PASSWORD")

        if idrac_ip and idrac_username and idrac_password:
            logger.info("Found credentials in environment variables, adding to database as 'default'")
            from utils.credential_manager import iDRACCredential
            default_cred = iDRACCredential(
                system_id="default",
                idrac_ip=idrac_ip,
                username=idrac_username,
                password=idrac_password,
                auth_token=os.getenv("IDRAC_AUTH_TOKEN"),
                description="Auto-imported from environment variables"
            )
            credential_db.add_credential(default_cred)
            logger.info("Added 'default' system to credential database")

    # Connect to MCP server (running as separate process on port 8000)
    step_start = datetime.now()
    mcp_server_url = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8000")
    logger.info(f"STARTUP: Connecting to MCP server at {mcp_server_url}...")

    mcp_client = MCPClient(base_url=mcp_server_url, timeout=60)

    # Connect to MCP server (async startup event)
    await mcp_client._connect_async()
    logger.info(f"STARTUP: [+{(datetime.now() - step_start).total_seconds():.2f}s] MCP server connection established")

    # Create LangChain tools from MCP client
    step_start = datetime.now()
    logger.info("STARTUP: Fetching tools from MCP server...")
    tools_list = await mcp_client.list_tools_async()
    logger.info(f"STARTUP: [+{(datetime.now() - step_start).total_seconds():.2f}s] Fetched {len(tools_list)} tools from MCP server")

    # Convert MCP tools to LangChain tools with credential database
    step_start = datetime.now()
    from utils.mcp_langchain_adapter import MCPToLangChainAdapter
    adapter = MCPToLangChainAdapter(mcp_client, credential_db=credential_db)
    tools = adapter._create_langchain_tools_from_list(tools_list)
    logger.info(f"STARTUP: [+{(datetime.now() - step_start).total_seconds():.2f}s] Created {len(tools)} LangChain tools with credential database support")

    # Create agent runner
    step_start = datetime.now()
    logger.info(f"STARTUP: Creating agent with provider: {test_config['llm']['provider']}")
    agent_runner = AgentRunner(test_config)
    logger.info(f"STARTUP: [+{(datetime.now() - step_start).total_seconds():.2f}s] Agent runner created")

    # Add RAG tool for documentation search
    try:
        step_start = datetime.now()
        logger.info("STARTUP: Initializing RAG tool (this may take a while for large PDF collections)...")
        rag_config = RAGConfig(
            pdf_folder="./data/pdfs",
            persist_directory="./data/chroma_db"
        )
        rag_tool = create_rag_tool(agent_runner.llm, rag_config)
        tools.append(rag_tool)
        logger.info(f"STARTUP: [+{(datetime.now() - step_start).total_seconds():.2f}s] RAG tool added ({len(tools)} total tools)")
    except Exception as e:
        logger.warning(f"STARTUP: RAG tool initialization failed: {e}")
        logger.info("STARTUP: Continuing without RAG tool...")

    # Create agent executor with all tools
    step_start = datetime.now()
    logger.info("STARTUP: Creating agent executor...")
    agent_executor = agent_runner.create_agent(tools)
    logger.info(f"STARTUP: [+{(datetime.now() - step_start).total_seconds():.2f}s] Agent executor created")

    total_startup_time = (datetime.now() - startup_start).total_seconds()
    logger.info("=" * 80)
    logger.info("STARTUP: Agent Orchestrator ready")
    logger.info(f"STARTUP: LLM Provider: {test_config['llm']['provider']}")
    logger.info(f"STARTUP: MCP Server: {mcp_server_url}")
    logger.info(f"STARTUP: Total Tools: {len(tools)}")
    logger.info(f"STARTUP: Total Startup Time: {total_startup_time:.2f}s")
    logger.info(f"STARTUP: Listening on: http://0.0.0.0:8001")
    logger.info("=" * 80)


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    global mcp_client

    logger.info("Shutting down Agent Orchestrator...")

    # Close MCP client connection
    if mcp_client:
        await mcp_client.close_async()
        logger.info("MCP client connection closed")


# =============================================================================
# API Endpoints
# =============================================================================

@app.get("/")
async def root():
    """Root endpoint - service info."""
    return {
        "service": "Agent Orchestrator Service",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "invoke": "/agent/invoke",
            "health": "/health",
            "tools": "/tools"
        }
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now().isoformat(),
        components={
            "mcp_client": mcp_client is not None,
            "agent_runner": agent_runner is not None,
            "agent_executor": agent_executor is not None,
        }
    )


@app.post("/agent/invoke", response_model=AgentResponse)
async def invoke_agent(request: AgentRequest):
    """
    Invoke the agent with user input.

    Args:
        request: Agent request with input and optional conversation_id

    Returns:
        Agent response with output and metadata
    """
    global conversations, agent_executor, agent_runner

    if not agent_executor or not agent_runner:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    # Get or create conversation ID
    conv_id = request.conversation_id or str(uuid.uuid4())

    # Initialize conversation if new
    if conv_id not in conversations:
        conversations[conv_id] = []

    # Add user message to history
    conversations[conv_id].append({
        "role": "user",
        "content": request.input,
        "timestamp": datetime.now().isoformat()
    })

    try:
        # Invoke agent
        logger.info(f"Processing request: {request.input[:100]}...")
        start_time = datetime.now()

        # Build chat history for context (last 2 messages only)
        chat_history = ""
        if conv_id in conversations and len(conversations[conv_id]) > 0:
            recent_history = conversations[conv_id][-2:]  # Last 2 messages
            for msg in recent_history:
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                if role == 'user':
                    chat_history += f"User: {content}\n"
                elif role == 'assistant':
                    chat_history += f"Assistant: {content}\n"

        logger.info("Invoking agent executor...")

        # Run agent executor in a thread pool to avoid async/sync mixing issues
        # This gives the agent a clean thread without a running event loop
        # The agent and tools can then run synchronously without deadlock
        loop = asyncio.get_event_loop()

        # Wrap in timeout to prevent indefinite hangs
        # Agent has its own timeout (90s), but we add a safety margin
        timeout_duration = 120  # 2 minutes safety timeout

        try:
            # LangGraph agent uses messages API
            from langchain_core.messages import HumanMessage, SystemMessage

            messages = []

            # Add system message if agent has one
            if hasattr(agent_executor, 'system_message'):
                messages.append(agent_executor.system_message)

            # Add chat history as context if available
            if chat_history:
                messages.append(SystemMessage(content=f"Previous conversation:\n{chat_history}"))

            # Add current user input
            messages.append(HumanMessage(content=request.input))

            result = await asyncio.wait_for(
                loop.run_in_executor(
                    None,  # Use default ThreadPoolExecutor
                    lambda: agent_executor.invoke({"messages": messages})
                ),
                timeout=timeout_duration
            )

            elapsed_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"Agent execution completed in {elapsed_time:.2f}s")

        except asyncio.TimeoutError:
            elapsed_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"Agent execution timed out after {elapsed_time:.2f}s")
            raise HTTPException(
                status_code=504,
                detail=f"Agent execution timed out after {timeout_duration}s"
            )

        # Extract response from LangGraph messages
        messages_result = result.get('messages', [])

        # Get final AI response
        response_text = 'No response generated'
        for msg in reversed(messages_result):
            if hasattr(msg, 'content') and msg.content:
                response_text = msg.content
                break

        # Extract tools called from messages
        tools_called = []
        for msg in messages_result:
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    if isinstance(tool_call, dict):
                        tools_called.append(tool_call.get('name', 'unknown'))
                    elif hasattr(tool_call, 'name'):
                        tools_called.append(tool_call.name)

        # Count iterations
        num_iterations = len([m for m in messages_result if hasattr(m, 'tool_calls')])
        intermediate_steps = messages_result

        # Add assistant message to history
        conversations[conv_id].append({
            "role": "assistant",
            "content": response_text,
            "timestamp": datetime.now().isoformat(),
            "tools_called": tools_called,
            "num_iterations": num_iterations
        })

        logger.info(f"Response generated (tools used: {tools_called}, iterations: {num_iterations})")

        # Log LLM usage stats
        if agent_runner and hasattr(agent_runner, 'llm_callback'):
            stats = agent_runner.llm_callback.get_stats()
            logger.info(f"LLM Usage: {stats['total_llm_calls']} calls, {stats['total_tokens']} total tokens")

        return AgentResponse(
            output=response_text,
            conversation_id=conv_id,
            timestamp=datetime.now().isoformat(),
            success=True,
            metadata={
                "tools_called": tools_called,
                "num_iterations": num_iterations
            }
        )

    except Exception as e:
        logger.error(f"Error processing request: {e}", exc_info=True)

        error_response = f"I encountered an error: {str(e)}"

        conversations[conv_id].append({
            "role": "assistant",
            "content": error_response,
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        })

        return AgentResponse(
            output=error_response,
            conversation_id=conv_id,
            timestamp=datetime.now().isoformat(),
            success=False,
            metadata={"error": str(e)}
        )


@app.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Get conversation history."""
    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {
        "conversation_id": conversation_id,
        "messages": conversations[conversation_id]
    }


@app.get("/tools", response_model=ToolsResponse)
async def list_tools():
    """List available tools."""
    if not mcp_client:
        raise HTTPException(status_code=503, detail="MCP client not initialized")

    # Get tools from MCP server
    try:
        mcp_tools = await mcp_client.list_tools_async()

        return ToolsResponse(
            tools=[
                {
                    "name": tool.get("name", "unknown"),
                    "description": tool.get("description", "No description"),
                    "category": "mcp",
                    "parameters": list(tool.get("inputSchema", {}).get("properties", {}).keys())
                }
                for tool in mcp_tools
            ],
            count=len(mcp_tools)
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to fetch tools from MCP server: {str(e)}")


# =============================================================================
# Main
# =============================================================================

def main():
    """Run the agent orchestrator service."""
    import argparse

    parser = argparse.ArgumentParser(description="Agent Orchestrator Service")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8001, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")

    args = parser.parse_args()

    print("""
╔══════════════════════════════════════════════════════════════╗
║                                                                ║
║            Agent Orchestrator Service                         ║
║                                                                ║
║     LangChain ReAct Agent with MCP Tools & RAG               ║
║                                                                ║
╚══════════════════════════════════════════════════════════════╝
    """)

    uvicorn.run(
        "agent_orchestrator_server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info"
    )


if __name__ == "__main__":
    main()
