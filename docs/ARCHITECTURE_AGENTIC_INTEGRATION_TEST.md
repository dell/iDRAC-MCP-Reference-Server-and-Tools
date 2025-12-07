# Agentic Integration test - Admin for Dell PowerEdge - Architecture Documentation

## Table of Contents

1. [Overview](#overview)
2. [High-Level Architecture](#high-level-architecture)
3. [Components](#components)
4. [Data Flow](#data-flow)
5. [Agent Reasoning Flow](#agent-reasoning-flow)
6. [RAG Integration](#rag-integration)
7. [Docker Deployment](#docker-deployment)
8. [Security Best Practices](#scurity-best-practices)
9. [References](#references)

---

## Overview

The Agentic Admin system is an **AI-powered administration interface** for managing Dell PowerEdge servers via iDRAC. It uses a **ReAct (Reasoning + Acting) agent** powered by LLMs to understand natural language requests and execute appropriate Redfish API operations.

### Key Features

- **Natural Language Interface**: Interact with servers using conversational language
- **Multi-System Management**: Manage multiple servers simultaneously with optimized execution
- **Intelligent Decision Making**: Agent reasons about tasks and chooses appropriate tools
- **RAG-Enhanced Responses**: Combines live data with Dell documentation for enriched answers
- **Chat History**: Contextual conversations with memory
- **Spreadsheet Import**: Bulk credential import from CSV/Excel

### Technology Stack

- **LLM**: Dell GenAI (oss-gpt), or OpenAI, or Anthropic Claude
- **Agent Framework**: LangChain 0.3.x + LangGraph
- **MCP Protocol**: Model Context Protocol for tool invocation
- **Backend**: FastAPI (orchestrator), FastMCP (MCP server)
- **Frontend**: Streamlit (chat UI)
- **Database**: SQLite with AES encryption (credentials)
- **Vector Store**: ChromaDB (RAG document embeddings)
- **Deployment**: Docker Compose

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User (Browser)                               │
│                  http://localhost:8501                               │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ HTTP
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Chat UI (Streamlit)                              │
│                        Port 8501                                    │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  UI Components:                                               │  │
│  │  - Chat interface                                             │  │
│  │  - Credential management sidebar                              │  │
│  │  - System selector                                            │  │
│  │  - CSV/Excel import                                           │  │
│  └──────────────────────┬───────────────────────────────────────┘   │
│                         │                                           │
│  ┌──────────────────────▼───────────────────────────────────────┐   │
│  │  Credential Database (SQLite + Fernet)                        │  │
│  │  ~/.idrac_credentials.db (shared with orchestrator)           │  │
│  └───────────────────────────────────────────────────────────────┘  │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ HTTP
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│               Agent Orchestrator (FastAPI)                          │
│                        Port 8001                                    │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    LangGraph Agent                           │   │
│  │                   (ReAct Pattern)                            │   │
│  │  ┌────────────────────────────────────────────────────────┐  │   │
│  │  │  Agent Loop:                                           │  │   │
│  │  │  1. Receive user query                                 │  │   │
│  │  │  2. Reason about task                                  │  │   │
│  │  │  3. Select appropriate tool(s)                         │  │   │
│  │  │  4. Execute tool(s)                                    │  │   │
│  │  │  5. Observe results                                    │  │   │
│  │  │  6. Repeat or finalize                                 │  │   │
│  │  └────────────────────────────────────────────────────────┘  │   │
│  └───────┬──────────────────────────────┬───────────────────────┘   │
│          │                              │                           │
│  ┌───────▼──────┐              ┌────────▼────────┐                  │
│  │  MCP Tools   │              │   RAG Tool      │                  │
│  │  (via MCP    │              │   (ChromaDB)    │                  │
│  │   Adapter)   │              │                 │                  │
│  └───────┬──────┘              └────────┬────────┘                  │
│          │                              │                           │
│  ┌───────▼──────────────────────────────▼────────┐                  │
│  │  Credential Database (SQLite + Fernet)         │                 │
│  │  Dynamic lookup, multi-system support          │                 │
│  └────────────────────────────────────────────────┘                 │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ HTTP (MCP Protocol)
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  MCP Server (FastMCP)                               │
│                        Port 8000                                    │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  MCP Tools (25+ tools):                                       │  │
│  │  - get_system_info                                            │  │
│  │  - get_memory_info                                            │  │
│  │  - get_processor_info                                         │  │
│  │  - reset_system                                               │  │
│  │  - ... (auto-generated from OpenAPI)                          │  │
│  │                                                               │  │
│  │  Workflows (6+ workflows):                                    │  │
│  │  - diagnose_system_health                                     │  │
│  │  - collect_full_inventory                                     │  │
│  │  - backup_bios_config                                         │  │
│  │  - ...                                                        │  │
│  └──────────────────────┬───────────────────────────────────────┘   │
└─────────────────────────┴───────────────────────────────────────────┘
                          │ HTTPS (Redfish API)
        ┌─────────────────┼─────────────────┬─────────────────┐
        │                 │                 │                 │
        ▼                 ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ iDRAC        │  │ iDRAC        │  │ iDRAC        │  │ iDRAC        │
│ prod-01      │  │ prod-02      │  │ dev-01       │  │ ...          │
│ 192.168.1.100│  │ 192.168.1.101│  │ 192.168.1.200│  │              │
└──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘
```

---

## Components

### 1. Chat UI (Streamlit)

**Location**: `chat-ui/app.py`
**Port**: 8501
**Purpose**: User interface for interacting with the agent

#### Responsibilities

- **Chat Interface**: Display conversation history and user inputs
- **Message Handling**: Send user queries to orchestrator, display responses
- **Credential Management**:
  - Add/import/manage iDRAC credentials
  - CSV/Excel bulk import
- **Session Management**: Maintain conversation context

---

### 2. Agent Orchestrator (FastAPI)

**Location**: `agent_orchestrator_server.py`
**Port**: 8001
**Purpose**: LangChain/LangGraph agent execution and tool orchestration

#### Responsibilities

- **Agent Execution**: Run ReAct agent to process user queries
- **Tool Coordination**: Provide MCP tools and RAG tool to agent
- **Conversation Management**: Track chat history per session
- **Credential Management**: Lookup and provide credentials dynamically
- **Multi-System Coordination**: Handle parallel execution for multiple systems

---

### 3. MCP Adapter (LangChain Integration)

**Location**: `utils/mcp_langchain_adapter.py`
**Purpose**: Bridge between LangChain and MCP protocol

#### Responsibilities

- **Tool Wrapping**: Convert MCP tools to LangChain StructuredTools
- **Dynamic Credentials**: Lookup credentials from database at execution time
- **Multi-System Execution**: Detect and execute for all systems in parallel
- **Result Formatting**: Format multi-system results for agent consumption

---

### 4. Credential Manager

**Location**: `utils/credential_manager.py`, `chat-ui/credential_manager.py`
**Purpose**: Secure storage and retrieval of iDRAC credentials

#### Architecture

```
┌──────────────────────────────────────┐
│     Credential Database              │
│     ~/.idrac_credentials.db          │
│                                      │
│  Table: credentials                  │
│  ┌────────────────────────────────┐ │
│  │ system_id (PK)                 │ │
│  │ idrac_ip (encrypted)           │ │
│  │ username (encrypted)           │ │
│  │ password (encrypted)           │ │
│  │ auth_token (encrypted)         │ │
│  └────────────────────────────────┘ │
└──────────────────────────────────────┘
```

#### Encryption

**Algorithm**: Fernet (AES-128 in CBC mode)
**Key Derivation**: PBKDF2HMAC with SHA-256
**Iterations**: 100,000
**Salt**: Fixed application salt (for simplicity)
**Master Password**: From environment variable `CREDENTIAL_MASTER_PASSWORD`

---

### 5. RAG Tool (Documentation Search)

**Location**: `utils/rag_tool.py`
**Purpose**: Search Dell PowerEdge/iDRAC documentation for context

#### Architecture

```
┌──────────────────────────────────────┐
│      Dell iDRAC Documentation        │
│      data/pdfs/                      │
└────────────┬─────────────────────────┘
             │ Ingestion (once)
             ▼
┌──────────────────────────────────────┐
│      Text Chunking                   │
│  - Chunk size: 1500 chars           │
│  - Overlap: 300 chars                │
└────────────┬─────────────────────────┘
             │
             ▼
┌──────────────────────────────────────┐
│      Embedding Generation            │
│  Model: all-mpnet-base-v2            │
│  (HuggingFace Sentence Transformers) │
└────────────┬─────────────────────────┘
             │
             ▼
┌──────────────────────────────────────┐
│      Vector Store (ChromaDB)         │
│      data/chroma_db/                 │
│  Collection: idrac_documents         │
│  - Document chunks                   │
│  - Embeddings (vectors)              │
│  - Metadata (source, page)           │
└────────────┬─────────────────────────┘
             │
             │ Query time
             ▼
┌──────────────────────────────────────┐
│      Retrieval (MMR)                 │
│  - Fetch k=16 candidates             │
│  - Apply MMR for diversity           │
│  - Return top k=8 chunks             │
└────────────┬─────────────────────────┘
             │
             ▼
┌──────────────────────────────────────┐
│      Return Context to Agent         │
│  Relevant documentation excerpts     │
└──────────────────────────────────────┘
```

---

### 6. MCP Client

**Location**: `utils/mcp_client.py`
**Purpose**: Communicate with MCP server using Model Context Protocol

#### Responsibilities

- **HTTP Transport**: Send requests to MCP server
- **Tool Discovery**: List available tools
- **Tool Invocation**: Call tools with parameters
- **Error Handling**: Handle MCP protocol errors

---

## Data Flow

### Complete Request Flow

```
1. USER INPUT
   User: "Show me memory info for prod-01"
        │
        ▼
2. CHAT UI (Streamlit)
   - Capture user input
   - Get selected system from UI (if any)
   - Send to orchestrator: POST /chat
        │
        ▼
3. AGENT ORCHESTRATOR
   - Receive message
   - Create LangGraph agent config
   - Execute agent with message
        │
        ▼
4. AGENT REASONING (ReAct Loop)
   ┌─────────────────────────────────────┐
   │ Thought: I need to get memory info  │
   │         for prod-01 system          │
   │                                     │
   │ Action: get_memory_info             │
   │ Action Input: {                     │
   │   target_system_id: "prod-01"       │
   │ }                                   │
   └──────────────┬──────────────────────┘
                  │
                  ▼
5. MCP ADAPTER (Tool Execution)
   - Extract target_system_id: "prod-01"
   - Lookup credentials from database
        │
        ▼
6. CREDENTIAL DATABASE
   - Query: SELECT * FROM credentials WHERE system_id='prod-01'
   - Decrypt: idrac_ip, username, password
   - Return: iDRACCredential object
        │
        ▼
7. MCP ADAPTER (continued)
   - Build MCP request with credentials
   - Call MCP server: call_tool_async("get_memory_info", {...})
        │
        ▼
8. MCP SERVER
   - Execute tool: get_memory_info
   - Map parameters to Redfish API
   - Add authentication headers
   - Call iDRAC: GET /redfish/v1/Systems/System.Embedded.1/Memory
        │
        ▼
9. iDRAC (prod-01)
   - Authenticate request
   - Fetch memory information
   - Return JSON response
        │
        ▼
10. MCP SERVER (return path)
    - Parse JSON response
    - Return to MCP adapter
        │
        ▼
11. MCP ADAPTER (return path)
    - Format result
    - Return to agent as tool observation
        │
        ▼
12. AGENT REASONING (continued)
    ┌─────────────────────────────────────┐
    │ Observation: {                      │
    │   "Members@odata.count": 12,        │
    │   "Members": [                      │
    │     {"Name": "DIMM A1", ...},       │
    │     ...                             │
    │   ]                                 │
    │ }                                   │
    │                                     │
    │ Thought: I have the memory info     │
    │                                     │
    │ Final Answer: System prod-01 has    │
    │   12 memory modules installed...    │
    └──────────────┬──────────────────────┘
                   │
                   ▼
13. AGENT ORCHESTRATOR (return path)
    - Get agent's final answer
    - Return to Chat UI: {response: "..."}
        │
        ▼
14. CHAT UI (display)
    - Display agent response in chat
    - Add to conversation history
        │
        ▼
15. USER
    Views response in browser
```

---

## Agent Reasoning Flow

### ReAct Pattern

The agent follows the **Reasoning and Acting (ReAct)** pattern:

```
┌──────────────────────────────────────────────┐
│          Agent Reasoning Loop                 │
│                                               │
│  1. QUESTION                                  │
│     Input: User's natural language query     │
│            + Chat history                     │
│            + Available tools                  │
│                                               │
│  2. THOUGHT                                   │
│     Agent reasons about:                      │
│     - What is the user asking?                │
│     - What information do I need?             │
│     - Which tool(s) should I use?             │
│     - Do I need documentation context?        │
│                                               │
│  3. ACTION (if needed)                        │
│     Agent selects a tool:                     │
│     - get_system_info                         │
│     - get_memory_info                         │
│     - rag_search                              │
│     - reset_system                            │
│     - etc.                                    │
│                                               │
│  4. ACTION INPUT                              │
│     Agent specifies parameters:               │
│     {                                         │
│       "target_system_id": "prod-01",          │
│       "system_id": "System.Embedded.1"        │
│     }                                         │
│                                               │
│  5. OBSERVATION                               │
│     Tool returns result:                      │
│     - API response data                       │
│     - Documentation excerpts                  │
│     - Error message (if failed)               │
│                                               │
│  6. REPEAT (if needed)                        │
│     Agent evaluates if more actions needed:   │
│     - Need more data? → Execute another tool  │
│     - Need documentation? → Call rag_search   │
│     - Have enough info? → Go to Final Answer  │
│                                               │
│  7. FINAL ANSWER                              │
│     Agent formulates complete response:       │
│     - Combine all observations                │
│     - Format clearly for user                 │
│     - Include relevant context                │
└───────────────────────────────────────────────┘
```
---

## RAG Integration

### Document Processing Pipeline

```
┌──────────────────────────────────────┐
│   PDF Documents (data/pdfs/)         │
│   - idrac10-1-20-xx-ug.pdf (4.4MB)   │
│   - idrac_redfish_api_guide.pdf      │
│   - idrac10-1-20-xx-ar-guide.pdf     │
└────────────┬─────────────────────────┘
             │ (First run only)
             ▼
┌──────────────────────────────────────┐
│   PDF Loader (LangChain)             │
│   - PyPDFLoader                      │
│   - Extract text from PDFs           │
│   - Preserve metadata                │
└────────────┬─────────────────────────┘
             │
             ▼
┌──────────────────────────────────────┐
│   Text Splitter                      │
│   - RecursiveCharacterTextSplitter   │
│   - chunk_size: 1500                 │
│   - chunk_overlap: 300               │
│   - separators: ["\n\n", "\n", " "]  │
└────────────┬─────────────────────────┘
             │
             ▼
┌──────────────────────────────────────┐
│   Embedding Model                    │
│   - HuggingFaceEmbeddings            │
│   - Model: all-mpnet-base-v2         │
│   - Dimension: 768                   │
│   - Generate embeddings for chunks   │
└────────────┬─────────────────────────┘
             │
             ▼
┌──────────────────────────────────────┐
│   Vector Store (ChromaDB)            │
│   Location: data/chroma_db/          │
│   Collection: idrac_documents        │
│   ┌──────────────────────────────┐   │
│   │ Document Chunks (~2000)      │   │
│   │ + Embeddings (768-dim)       │   │
│   │ + Metadata (source, page)    │   │
│   └──────────────────────────────┘   │
└──────────────────────────────────────┘
```

### Query-Time Retrieval

```
User Query
     │
     ▼
┌──────────────────────────────────────┐
│   Embedding Model                    │
│   Generate query embedding (768-dim) │
└────────────┬─────────────────────────┘
             │
             ▼
┌──────────────────────────────────────┐
│   Vector Store Search                │
│   1. Similarity search               │
│      - Cosine similarity             │
│      - Fetch k=16 candidates         │
│                                      │
│   2. MMR (Maximal Marginal Relevance)│
│      - Balance relevance & diversity │
│      - Return top k=8 chunks         │
└────────────┬─────────────────────────┘
             │
             ▼
┌──────────────────────────────────────┐
│   Format Context                     │
│   Combine chunks with sources:       │
│                                      │
│   Source: idrac_redfish_api_guide.pdf│
│   Page: 42                           │
│   [Chunk text about memory config]   │
│                                      │
│   Source: idrac10-1-20-xx-ug.pdf     │
│   Page: 156                          │
│   [Chunk text about health status]   │
└────────────┬─────────────────────────┘
             │
             ▼
     Return to Agent
```

### Agent + RAG Workflow

```
User: "How do I configure RAID arrays?"
     │
     ▼
Agent Thought: I should search documentation
     │
     ▼
Action: rag_search
Action Input: {"query": "configure RAID arrays iDRAC"}
     │
     ▼
RAG Tool: Searches vector store
     │
     ▼
Observation: [Documentation excerpts about RAID configuration]
     │
     ▼
Agent Thought: I have the instructions
     │
     ▼
Final Answer: To configure RAID arrays in iDRAC:
              1. Navigate to Storage → Controllers
              2. Select the RAID controller
              3. Click "Create Virtual Disk"
              4. [Full instructions from documentation]
```

---

## Docker Deployment

### Multi-Container Architecture

```
┌─────────────────────────────────────────────────────────┐
│               Docker Compose Stack                       │
│               (idrac-agentic-network)                    │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │  chat-ui (Streamlit)                               │ │
│  │  Port: 8501                                        │ │
│  │  Image: python:3.11-slim                           │ │
│  │  Volumes:                                          │ │
│  │    - idrac-credentials:/data                       │ │
│  │    - idrac-streamlit-cache:/root/.streamlit        │ │
│  │  Depends: orchestrator (healthy)                   │ │
│  └────────────────────────┬───────────────────────────┘ │
│                           │ HTTP                         │
│  ┌────────────────────────▼───────────────────────────┐ │
│  │  orchestrator (FastAPI)                            │ │
│  │  Port: 8001                                        │ │
│  │  Image: python:3.11-slim                           │ │
│  │  Volumes:                                          │ │
│  │    - idrac-credentials:/data (shared)              │ │
│  │    - idrac-chroma-db:/data/chroma_db               │ │
│  │    - ./data/pdfs:/app/data/pdfs:ro                 │ │
│  │    - ./config:/app/config:ro                       │ │
│  │  Depends: mcp-server (healthy)                     │ │
│  └────────────────────────┬───────────────────────────┘ │
│                           │ HTTP (MCP)                   │
│  ┌────────────────────────▼───────────────────────────┐ │
│  │  mcp-server (FastMCP)                              │ │
│  │  Port: 8000                                        │ │
│  │  Image: python:3.11-slim                           │ │
│  │  Volumes:                                          │ │
│  │    - ../mcp_idrac_server/config:/app/config:ro     │ │
│  └────────────────────────┬───────────────────────────┘ │
│                           │ HTTPS                        │
└───────────────────────────┼─────────────────────────────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
              ▼             ▼             ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │ iDRAC    │  │ iDRAC    │  │ iDRAC    │
        │ prod-01  │  │ prod-02  │  │ dev-01   │
        └──────────┘  └──────────┘  └──────────┘
```

### Volume Management

```
┌─────────────────────────────────────────┐
│      Docker Volumes                      │
│                                          │
│  1. idrac-credentials                    │
│     Purpose: Encrypted credential DB     │
│     Shared: orchestrator ↔ chat-ui       │
│     Path: /data/credentials.db           │
│     Backup: docker volume backup cmd     │
│                                          │
│  2. idrac-chroma-db                      │
│     Purpose: RAG vector store            │
│     Used by: orchestrator only           │
│     Path: /data/chroma_db                │
│     Rebuild: Delete volume to re-index   │
│                                          │
│  3. idrac-streamlit-cache                │
│     Purpose: Streamlit cache             │
│     Used by: chat-ui only                │
│     Path: /root/.streamlit               │
│     Optional: Can be deleted             │
└─────────────────────────────────────────┘
```

### Health Checks

```
┌─────────────────────────────────────────┐
│      Service Health Checks               │
│                                          │
│  mcp-server:                             │
│    Test: python -c "import sys; ..."    │
│    Interval: 10s                         │
│    Start Period: 10s                     │
│    Retries: 5                            │
│                                          │
│  orchestrator:                           │
│    Test: curl http://localhost:8001/health│
│    Interval: 30s                         │
│    Start Period: 60s (for RAG init)      │
│    Retries: 5                            │
│    Depends: mcp-server (healthy)         │
│                                          │
│  chat-ui:                                │
│    Test: curl http://localhost:8501/... │
│    Interval: 30s                         │
│    Start Period: 10s                     │
│    Retries: 3                            │
│    Depends: orchestrator (healthy)       │
└─────────────────────────────────────────┘
```

### Environment Configuration

```bash
# .env file (required!)
DEV_GENAI_API_URL=https://genai-api-dev.dell.com/v1
DEV_GENAI_API_KEY=your-api-key-here
CREDENTIAL_MASTER_PASSWORD=your-secure-password

# Docker Compose reads .env automatically
docker compose up -d
```

---

## Security Best Practices

### Production Deployment Checklist

- [ ] Change `CREDENTIAL_MASTER_PASSWORD` to strong value
- [ ] Use HTTPS reverse proxy (nginx/traefik) in front
- [ ] Enable network isolation (firewall rules)
- [ ] Use Docker secrets for sensitive env vars
- [ ] Regularly backup credential database
- [ ] Monitor logs for suspicious activity
- [ ] Keep Docker images updated
- [ ] Enable SSL verification for iDRAC (with valid certs)
- [ ] Implement rate limiting
- [ ] Add authentication to Chat UI (if exposed)

---

## References

- **LangChain**: https://python.langchain.com/
- **LangGraph**: https://langchain-ai.github.io/langgraph/
- **Model Context Protocol**: https://modelcontextprotocol.io/
- **Dell iDRAC**: https://www.dell.com/support/manuals/idrac
- **ChromaDB**: https://www.trychroma.com/
- **Docker Compose**: https://docs.docker.com/compose/
