# Docker Deployment Guide

Agentic Admin for Dell PowerEdge - Containerized Deployment

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Compose Stack                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │   Chat UI    │───▶│ Orchestrator │───▶│  MCP Server │   │
│  │  (Streamlit) │    │  (FastAPI)   │    │  (FastAPI)   │   │
│  │   Port 8501  │    │   Port 8001  │    │   Port 8000  │   │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘   │
│         │                   │                    │          │
│         └───────────────────┴────────────────────┘          │
│                   Shared Credential DB                      │
│                   (Encrypted SQLite)                        │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
                   Live iDRAC Systems
                   (External)
```

## Services

### 1. MCP Server (`mcp-server`)
- **Port**: 8000
- **Description**: Dell iDRAC Redfish MCP Server providing tool interfaces
- **Health Check**: `GET http://localhost:8000/mcp`

### 2. Agent Orchestrator (`orchestrator`)
- **Port**: 8001
- **Description**: LangChain ReAct agent with MCP tools and RAG capabilities
- **Health Check**: `GET http://localhost:8001/health`
- **Dependencies**: Requires `mcp-server` to be healthy

### 3. Chat UI (`chat-ui`)
- **Port**: 8501
- **Description**: Streamlit web interface for managing credentials and chatting with the agent
- **URL**: `http://localhost:8501`
- **Dependencies**: Requires `orchestrator` to be healthy

## Quick Start

### Prerequisites

- Docker Engine 20.10+ or Docker Desktop
- Docker Compose V2
- At least 4GB RAM available for Docker
- Access to one or more live Dell iDRAC systems


### Configure Environment **REQUIRED**

**CRITICAL**: You must create a `.env` file before running docker compose!

```bash
# Copy environment template
cp .env.example .env

# Edit .env file with your credentials
nano .env
```

**Required Configuration**:

```bash
# LLM Provider - REQUIRED!
DEV_GENAI_API_URL=<>
DEV_GENAI_API_KEY=your-actual-api-key-here

# Credential Database Encryption (CHANGE THIS!)
CREDENTIAL_MASTER_PASSWORD=$(openssl rand -base64 32)
```

**Verify configuration**:
```bash
# Check that .env has required values
grep -E "DEV_GENAI_API_KEY|DEV_GENAI_API_URL|CREDENTIAL_MASTER_PASSWORD" .env
```

### Step 3: Build and Start

```bash
# Build all containers
docker compose build

# Start all services
docker compose up -d

# View logs
docker compose logs -f
```

### Step 4: Access the Application

1. Open browser: `http://localhost:8501`
2. Configure iDRAC systems in the sidebar
3. Start chatting with the agent!

## Managing iDRAC Systems

### Adding Systems via UI

1. Navigate to `http://localhost:8501`
2. In the sidebar, click **"➕ Add System"**
3. Fill in the form:
   - **System ID**: Unique identifier (e.g., `prod-server-01`)
   - **iDRAC IP/URL**: `192.168.1.100`
   - **Username**: `user name`
   - **Password**: password
   - **Description**: Optional description
4. Click **"💾 Save"**

### Importing Multiple Systems

1. In the sidebar, click **"📥 Import"**
2. Download the CSV or Excel template
3. Fill in your systems:
   ```csv
   system_id,idrac_ip,username,password,auth_token,description
   prod-01,<ip>,<user name>,<password>,,Production Server 1
   prod-02,<ip>,<user name>,<password>,,Production Server 2
   dev-01,<ip>,<user name>,<password>,,Development Server
   ```
4. Upload the file
5. Click **"📥 Import"**

### Querying Systems

**Single System**:
```
User: "Show me memory info for prod-01"
```

**All Systems** (parallel execution):
```
User: "Show me active alerts"
User: "What's the health status across all servers?"
User: "Compare BIOS versions. Are they running latest required versions?"
```

## Docker Commands

### Start Services

```bash
# Start all services (detached mode)
docker compose up -d

# Start specific service
docker compose up -d chat-ui

# Start with logs (foreground)
docker compose up
```

### Stop Services

```bash
# Stop all services
docker compose down

# Stop but keep volumes (credentials preserved)
docker compose down

# Stop and remove volumes (DESTROYS ALL DATA!)
docker compose down -v
```

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f orchestrator
docker compose logs -f chat-ui
docker compose logs -f mcp-server

# Last 100 lines
docker compose logs --tail=100
```

### Rebuild Services

```bash
# Rebuild all services
docker compose build

# Rebuild specific service
docker compose build orchestrator

# Rebuild without cache (clean build)
docker compose build --no-cache
```

### Service Management

```bash
# Restart a service
docker compose restart orchestrator

# Stop a service
docker compose stop chat-ui

# Start a service
docker compose start chat-ui

# View status
docker compose ps

# Execute command in container
docker compose exec orchestrator bash
```

## Volumes

### Shared Volumes

| Volume Name | Purpose | Shared Between |
|-------------|---------|----------------|
| `idrac-credentials` | Encrypted credential database | orchestrator, chat-ui |
| `idrac-chroma-db` | Vector store for RAG | orchestrator only |
| `idrac-streamlit-cache` | Streamlit cache | chat-ui only |


## License

Copyright 2025 Dell Inc. Licensed under Apache License 2.0.
