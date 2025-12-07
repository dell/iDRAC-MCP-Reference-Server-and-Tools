# iDRAC Reference MCP Server - Architecture Documentation

## Table of Contents

1. [Overview](#overview)
2. [High-Level Architecture](#high-level-architecture)
3. [Components](#components)
4. [Data Flow](#data-flow)
    - [Tool Generation Flow](#tool-generation-flow)
    - [Tool Call Flow](#tool-call-flow)
    - [Workflow (as a Tool) Call Flow](workflow-(as-a-tool)-call-flow)
6. [Authentication Flow](#authentication-flow)
    - [Basic Authentication](#basic-authentication)
    - [Session or X-Auth Token Authentication](#session-or-x-Auth-token-authentication)
7. [Request/Response Flow](#request/response-flow)
    - [Successful Request](#successful-request)
    - [Error Handling](#error-handling)
8. [Tool (Simple or Workflow based) Addition or Extension Points](#tool-simple-or-workflow-based-extension-points)
    - [Adding New Tools](#adding-new-tools)
    - [Adding New Workflows](#adding-new-workflows)
10. [Directory Structure](#directory-structure)
11. [Performance Considerations](#performance-considerations)
12. [Security Considerations](#security-considerations)
13. [References](#references)

---

## Overview

The iDRAC Reference MCP Server is a **Model Context Protocol (MCP)** server that exposes Dell iDRAC Redfish API operations as callable tools for AI agents and automation systems.

### Key Features

- **Automatic Tool Generation**: Converts OpenAPI specifications to MCP tools
- **Custom Workflows**: Compose multiple API calls into higher-level operations
- **Flexible Authentication**: Supports both Basic Auth and Token-based authentication
- **Per-Request Credentials**: No hardcoded credentials, fully dynamic
- **Transport Flexibility**: Supports HTTP and STDIO transports

### Technology Stack

- **Framework**: FastMCP (Model Context Protocol)
- **HTTP Client**: httpx (for Redfish API calls)
- **Configuration**: YAML (OpenAPI spec, tools config, workflows config)
- **Data Validation**: Pydantic
- **JSONPath**: jsonpath-ng (for workflow data extraction)

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     MCP Client (Agent/User)                     │
│                    (LangChain, Claude, Custom)                  │
└────────────────────────────┬────────────────────────────────────┘
                             │ MCP Protocol (HTTP/STDIO)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    iDRAC Redfish MCP Server                     │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                     FastMCP Server                        │  │
│  │                (Tool Registry & Dispatch)                 │  │
│  └───────────────┬─────────────────────────┬─────────────────┘  │
│                  │                         │                    │
│         ┌────────▼────────┐       ┌────────▼─────┐              │
│         │  Standard Tools │       │  Workflows   │              │
│         │ (1:1 API calls) │       │ (Multi-step) │              │
│         └────────┬────────┘       └────────┬─────┘              │
│                  │                         │                    │
│  ┌───────────────▼─────────────────────────▼─────────────────┐  │
│  │              Tool/Workflow Execution Layer                │  │
│  │  ┌─────────────────┐         ┌────────────────────────┐   │  │
│  │  │  Tool Generator │         │  Workflow Executor     │   │  │
│  │  │  - Param mapping│         │  - Multi-step orchestr.│   │  │
│  │  │  - Validation   │         │  - Variable subst.     │   │  │
│  │  └────────┬────────┘         │  - Error handling      │   │  │
│  │           │                  │  - Data extraction     │   │  │
│  │           │                  └────────┬───────────────┘   │  │
│  │           └───────────────────────────┘                   │  │
│  │                           │                               │  │
│  │  ┌────────────────────────▼──────────────────────────┐    │  │
│  │  │            Redfish Client Layer                   │    │  │
│  │  │  - HTTP Request Construction                      │    │  │
│  │  │  - Authentication (Basic/Token)                   │    │  │
│  │  │  - Retry Logic                                    │    │  │
│  │  │  - SSL Verification                               │    │  │
│  │  └────────────────────────┬──────────────────────────┘    │  │
│  └───────────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS/HTTP (Redfish API)
                             ▼
                   ┌─────────────────────┐
                   │   Dell iDRAC        │
                   │   (Redfish API)     │
                   │                     │
                   └─────────────────────┘
```

---

## Components

### 1. Configuration Layer

#### **OpenAPI Parser** (`src/parsers/openapi_parser.py`)

**Purpose**: Parse Dell iDRAC Redfish OpenAPI specification

**Responsibilities**:
- Load and parse OpenAPI YAML
- Extract API operation definitions
- Build operation registry (operationId → operation details)
- Provide parameter schemas

**Key Methods**:
```python
get_operation(operation_id: str) -> ApiOperation
list_operation_ids() -> List[str]
```

#### **Tool Config Parser** (`src/parsers/tool_config_parser.py`)

**Purpose**: Parse tool configuration from `tools.yaml`

**Responsibilities**:
- Load tool definitions
- Map tool parameters to API parameters
- Validate tool configurations against OpenAPI spec
- Filter enabled/disabled tools

**Configuration Format**:
```yaml
tools:
  - name: get_system_info
    operation_id: GET_/redfish/v1/Systems/{ComputerSystemId}
    enabled: true
    parameter_mappings:
      - tool_param_name: system_id
        api_param_name: ComputerSystemId
        location: path
```

#### **Workflow Parser** (`src/parsers/workflow_parser.py`)

**Purpose**: Parse workflow definitions from `workflows.yaml`

**Responsibilities**:
- Load workflow definitions
- Parse inputs, steps, and outputs
- Validate that workflows reference existing tools
- Filter enabled/disabled workflows

**Configuration Format**:
```yaml
workflows:
  - name: diagnose_system_health
    inputs:
      - name: system_id
    steps:
      - name: get_system
        tool: get_system_info
        parameters:
          system_id: ${{inputs.system_id}}
        outputs:
          health: "$.Status.Health"
```

---

### 2. Execution Layer

#### **Tool Generator** (`src/generators/tool_generator.py`)

**Purpose**: Generate callable Python functions from tool definitions

**Responsibilities**:
- Create function signatures with proper type annotations
- Map tool parameters to API parameters (path, query, body)
- Handle credential extraction (idrac_ip, username, password, auth_token)
- Execute Redfish API calls via RedfishClient
- Return formatted responses

**Function Signature Generation**:
```python
# Generated signature for get_system_info:
def get_system_info(
    idrac_ip: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
    auth_token: Optional[str] = None,
    system_id: str = "System.Embedded.1"
) -> Dict[str, Any]:
    # Execute Redfish API call
    ...
```

**Parameter Mapping Flow**:
```
Tool Parameters → Parameter Mappings → API Parameters
system_id       →  path mapping     → /Systems/{ComputerSystemId}
filter_type     →  query mapping    → ?$filter=...
config_data     →  body mapping     → Request Body
```

#### **Workflow Executor** (`src/generators/workflow_executor.py`)

**Purpose**: Execute multi-step workflows with orchestration logic

**Responsibilities**:
- Execute steps sequentially
- Perform variable substitution (`${{inputs.x}}`, `${{steps.y.output}}`)
- Extract data using JSONPath
- Evaluate conditions for conditional steps
- Handle errors according to step strategy (fail/continue/skip)
- Build final output from template

**Execution Context**:
```python
WorkflowExecutionContext:
  - workflow_name: str
  - inputs: Dict[str, Any]           # User inputs
  - step_outputs: Dict[str, Dict]    # Accumulated step results
  - variables: Dict[str, Any]        # Runtime variables
  - errors: List[Dict]               # Errors encountered
```

**Variable Substitution**:
```
${{inputs.system_id}}              → "System.Embedded.1"
${{steps.get_system.health}}       → "OK"
${{workflow.timestamp}}            → "2025-01-16T10:30:00"
```

**JSONPath Extraction**:
```
"$.Status.Health"                  → "OK"
"$.Members"                        → [array of members]
"$.Members@odata.count"            → 12
```

---

### 3. Client Layer

#### **Redfish Client** (`src/clients/redfish_client.py`)

**Purpose**: HTTP client for Dell iDRAC Redfish API

**Responsibilities**:
- Construct HTTP requests (GET, POST, PATCH, DELETE)
- Add authentication headers (Basic or Token)
- Handle SSL verification
- Implement retry logic with exponential backoff
- Parse JSON responses
- Raise typed exceptions (RedfishAPIError)

**Request Construction**:
```python
def execute_operation(
    operation: ApiOperation,
    credentials: Credentials,
    base_url: str,
    path_params: Dict,
    query_params: Dict,
    body: Optional[Dict],
    headers: Dict
) -> Dict[str, Any]:
    # 1. Build URL with path parameters
    # 2. Add query parameters
    # 3. Add authentication headers
    # 4. Execute request with retries
    # 5. Parse and return response
```

#### **Authentication Handlers** (`src/auth/authentication.py`)

**Purpose**: Handle different authentication methods

**Basic Auth Handler**:
```python
def add_auth_headers(credentials: Credentials) -> Dict[str, str]:
    auth_str = base64.b64encode(f"{username}:{password}".encode())
    return {"Authorization": f"Basic {auth_str}"}
```

**Token Auth Handler**:
```python
def add_auth_headers(credentials: Credentials) -> Dict[str, str]:
    return {"X-Auth-Token": credentials.token}
```

---

### 4. Server Layer

#### **RedfishMCPServer** (`src/server/mcp_server.py`)

**Purpose**: Main server class that orchestrates all components

**Initialization Flow**:
```
1. Parse OpenAPI specification
2. Parse tools configuration
3. Validate tools against OpenAPI
4. Create Redfish client
5. Generate tool functions
6. Register tools with FastMCP
7. [Optional] Parse workflows configuration
8. [Optional] Validate workflows against tools
9. [Optional] Create workflow executor
10. [Optional] Generate and register workflow functions
```

**Tool Registration**:
```python
# For each enabled tool:
tool_func = tool_generator.generate_tool(tool_def, api_operation)
mcp.tool(name=tool_def.name, description=...)(tool_func)
```

**Workflow Registration**:
```python
# For each enabled workflow:
workflow_func = _create_workflow_function(workflow_def)
mcp.tool(name=workflow_def.name, description=...)(workflow_func)
```

#### **FastMCP Server** (External Library)

**Purpose**: MCP protocol implementation

**Responsibilities**:
- Handle MCP protocol messages
- Dispatch tool calls to registered functions
- Manage transports (HTTP, STDIO)
- Return results in MCP format

---

## Data Flow

## Tool Generation Flow

```
OpenAPI Spec          Tools Config
(openapi.yaml)        (tools.yaml)
      │                    │
      │                    │
      ▼                    ▼
┌─────────────┐    ┌──────────────┐
│   OpenAPI   │    │ Tool Config  │
│   Parser    │    │   Parser     │
└──────┬──────┘    └──────┬───────┘
       │                  │
       │ operation_id     │ tool definition
       │ "GET_/redfish/v1/Systems/{id}"
       │                  │
       └────────┬─────────┘
                │
                ▼
       ┌────────────────────┐
       │  Tool Generator    │
       │                    │
       │  1. Match tool     │
       │     operation_id   │
       │                    │
       │  2. Build function │
       │     signature:     │
       │     - idrac_ip     │
       │     - credentials  │
       │     - tool params  │
       │                    │
       │  3. Map parameters:│
       │     tool_param →   │
       │     api_param      │
       │     (path/query/   │
       │      body)         │
       │                    │
       │  4. Create wrapper:│
       │     - Extract creds│
       │     - Map params   │
       │     - Call Redfish │
       │       Client       │
       │     - Return result│
       └────────┬───────────┘
                │
                ▼
         ┌──────────────┐
         │ Tool Function│ → Register with FastMCP
         │  (Callable)  │
         └──────────────┘
```

### Tool Call Flow

```
┌──────────────┐
│  MCP Client  │
│   (Agent)    │
└──────┬───────┘
       │ 1. Call tool "get_system_info"
       │    Parameters: {idrac_ip, username, password, system_id}
       ▼
┌──────────────────────────────────────────┐
│         FastMCP Server                   │
│  2. Lookup tool in registry              │
│  3. Dispatch to tool function            │
└──────┬───────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│       Tool Generator                     │
│  4. Extract credentials                  │
│  5. Map tool params → API params         │
│     system_id → ComputerSystemId (path)  │
└──────┬───────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│       Redfish Client                     │
│  6. Build HTTP request:                  │
│     GET /redfish/v1/Systems/System.Embedded.1  │
│  7. Add auth headers (Basic or Token)    │
│  8. Execute request with retries         │
└──────┬───────────────────────────────────┘
       │ HTTPS
       ▼
┌──────────────────────────────────────────┐
│          Dell iDRAC                      │
│  9. Authenticate request                 │
│  10. Execute operation                   │
│  11. Return JSON response                │
└──────┬───────────────────────────────────┘
       │ JSON Response
       ▼
┌──────────────────────────────────────────┐
│       Redfish Client                     │
│  12. Parse JSON response                 │
│  13. Handle errors                       │
└──────┬───────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│       Tool Function                      │
│  14. Return response data                │
└──────┬───────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│       FastMCP Server                     │
│  15. Format as MCP response              │
└──────┬───────────────────────────────────┘
       │
       ▼
┌──────────────┐
│  MCP Client  │
│  16. Receive │
│      result  │
└──────────────┘
```

## Workflow (as a Tool) Call Flow

```
Workflow Definition (workflows.yaml)
         │
         ▼
┌─────────────────┐
│ Workflow Parser │
│ - Parse YAML    │
│ - Validate refs │
└────────┬────────┘
         │
         ▼
   ┌─────────────────────────────────────┐
   │    Workflow Executor                │
   │                                     │
   │  INITIALIZATION:                    │
   │  1. Create execution context        │
   │  2. Store user inputs               │
   │  3. Store credentials               │
   │                                     │
   │  FOR EACH STEP:                     │
   │  ┌──────────────────────────────┐  │
   │  │ EVALUATE CONDITION           │  │
   │  │ - Substitute variables       │  │
   │  │ - Check if step should run   │  │
   │  └──────────┬───────────────────┘  │
   │             │ true                 │
   │  ┌──────────▼───────────────────┐  │
   │  │ PARAMETER RESOLUTION         │  │
   │  │ Pattern: ${{source.path}}    │  │
   │  │                              │  │
   │  │ Sources:                     │  │
   │  │ - inputs.param_name          │  │
   │  │ - steps.step_name.output     │  │
   │  │ - workflow.property          │  │
   │  └──────────┬───────────────────┘  │
   │             │                      │
   │  ┌──────────▼───────────────────┐  │
   │  │ TOOL EXECUTION               │  │
   │  │ 1. Lookup tool in registry   │  │
   │  │ 2. Add credentials           │  │
   │  │ 3. Call tool function        │──┼───> Redfish API
   │  │ 4. Get result                │  │
   │  └──────────┬───────────────────┘  │
   │             │                      │
   │  ┌──────────▼───────────────────┐  │
   │  │ OUTPUT EXTRACTION            │  │
   │  │ Use JSONPath:                │  │
   │  │ - "$.Status.Health" → "OK"   │  │
   │  │ - "$.Members" → [array]      │  │
   │  │ - "$" → entire response      │  │
   │  └──────────┬───────────────────┘  │
   │             │                      │
   │  ┌──────────▼───────────────────┐  │
   │  │ STORE OUTPUTS                │  │
   │  │ context.step_outputs[name]   │  │
   │  │   = extracted_data           │  │
   │  └──────────┬───────────────────┘  │
   │             │                      │
   │  ┌──────────▼───────────────────┐  │
   │  │ ERROR HANDLING               │  │
   │  │ - fail: stop workflow        │  │
   │  │ - continue: log & proceed    │  │
   │  │ - skip_remaining: stop loop  │  │
   │  └──────────────────────────────┘  │
   │                                     │
   │  FINALIZATION:                      │
   │  1. Build output from template      │
   │  2. Substitute step outputs         │
   │  3. Return WorkflowExecutionResult  │
   └─────────────────────────────────────┘
```

---

## Authentication Flow

### Basic Authentication

```
Client Request
     │
     ▼
┌─────────────────────────┐
│ Tool Function           │
│ username = "root"       │
│ password = "calvin"     │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ Create Credentials      │
│ Credentials(            │
│   username="root",      │
│   password="calvin"     │
│ )                       │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ Basic Auth Handler      │
│ 1. Encode credentials   │
│    base64(root:calvin)  │
│ 2. Build header:        │
│    Authorization:       │
│      Basic cm9vdDp...   │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ Redfish Client          │
│ Add header to request   │
└────────┬────────────────┘
         │ HTTPS with Basic Auth
         ▼
┌─────────────────────────┐
│ Dell iDRAC              │
│ Validate credentials    │
└─────────────────────────┘
```

### Session or X-Auth Token Authentication

```
Client Request
     │
     ▼
┌─────────────────────────┐
│ Tool Function           │
│ auth_token = "xyz123"   │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ Create Credentials      │
│ Credentials(            │
│   token="xyz123"        │
│ )                       │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ Token Auth Handler      │
│ Build header:           │
│   X-Auth-Token: xyz123  │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ Redfish Client          │
│ Add header to request   │
└────────┬────────────────┘
         │ HTTPS with Token
         ▼
┌─────────────────────────┐
│ Dell iDRAC              │
│ Validate token          │
└─────────────────────────┘
```

---

## Request/Response Flow

### Successful Request

```
MCP Client
    │
    │ call_tool("get_system_info", {...})
    ▼
FastMCP Server
    │
    │ Dispatch to tool
    ▼
Tool Function
    │
    │ Extract: idrac_ip, credentials, system_id
    ▼
Parameter Mapping
    │
    │ system_id → ComputerSystemId (path)
    ▼
Redfish Client
    │
    │ Build URL: https://192.168.1.100/redfish/v1/Systems/System.Embedded.1
    │ Add Auth Header
    │ Execute HTTP GET
    ▼
Dell iDRAC
    │
    │ Authenticate
    │ Fetch system info
    │ Return JSON
    ▼
Redfish Client
    │
    │ Parse JSON: {"Model": "PowerEdge R750", ...}
    ▼
Tool Function
    │
    │ Return data
    ▼
FastMCP Server
    │
    │ Format MCP response
    ▼
MCP Client
    │
    │ Receive: {"Model": "PowerEdge R750", ...}
```

### Error Handling

```
Request
    │
    ▼
Redfish Client
    │
    │ HTTP Request
    ▼
Dell iDRAC
    │
    │ HTTP 401 Unauthorized
    ▼
Redfish Client
    │
    │ Catch HTTP error
    │ Raise RedfishAPIError("Authentication failed")
    ▼
Tool Function
    │
    │ Propagate exception
    ▼
FastMCP Server
    │
    │ Convert to MCP error
    ▼
MCP Client
    │
    │ Receive error response
```

---

## Extension Points

### 1. Adding New Tools

**File**: `config/tools.yaml`

```yaml
tools:
  - name: my_custom_tool
    description: Description of what it does
    operation_id: GET_/redfish/v1/CustomEndpoint
    enabled: true
    category: custom
    parameter_mappings:
      - tool_param_name: param1
        api_param_name: ApiParam1
        location: path  # or query, body
        required: true
```

### 2. Adding New Workflows

**File**: `config/workflows.yaml`

```yaml
workflows:
  - name: my_custom_workflow
    description: Multi-step operation
    enabled: true
    inputs:
      - name: input1
        type: string
        required: true
    steps:
      - name: step1
        tool: existing_tool_name
        parameters:
          param1: ${{inputs.input1}}
        outputs:
          result: "$"
    output:
      final_result: ${{steps.step1.result}}
```

---

## Directory Structure

```
mcp_idrac_server/
├── config/
│   ├── openapi.yaml           # Redfish API specification
│   ├── tools_reference.yaml   # Reference YAML which is a direct conversion from OpenAPI redfish YAML definition
│   ├── tools.yaml             # Tool definitions (user configurable file)
│   └── workflows.yaml         # Workflow definitions (user configruable file)
├── src/
│   ├── __init__.py
│   ├── __main__.py            # Entry point
│   ├── auth/
│   │   ├── __init__.py
│   │   └── authentication.py  # Auth handlers
│   ├── clients/
│   │   ├── __init__.py
│   │   └── redfish_client.py  # HTTP client
│   ├── generators/
│   │   ├── __init__.py
│   │   ├── tool_generator.py  # Tool function generator
│   │   └── workflow_executor.py  # Workflow orchestrator
│   ├── models/
│   │   ├── __init__.py
│   │   ├── api_operation.py   # API operation model
│   │   ├── tool_definition.py # Tool definition model
│   │   └── workflow_definition.py  # Workflow models
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── openapi_parser.py  # OpenAPI parser
│   │   ├── tool_config_parser.py  # Tool config parser
│   │   └── workflow_parser.py # Workflow parser
│   └── server/
│       ├── __init__.py
│       └── mcp_server.py      # Main server
├── README.md                  # General documentation
└── requirements.txt           # Dependencies
```

---

## Performance Considerations

### Tool Execution

- **Connection Pooling**: httpx reuses connections
- **Timeouts**: Configurable per-request (default: 30s)
- **Retries**: Exponential backoff with max 3 retries
- **Concurrent Requests**: Multiple tools can be called in parallel by clients

### Workflow Execution

- **Sequential Steps**: With in a workflow steps execute in order
- **Early Exit**: Error strategies allow skipping remaining steps
- **Memory Efficiency**: Step outputs stored in context, cleaned after workflow

### Scalability

- **Stateless Server**: No session state, scales horizontally
- **Per-Request Credentials**: No global credential storage
- **Configuration Caching**: OpenAPI and config parsed once at startup

---

## Security Considerations

### Credential Handling

- **No Hardcoded Credentials**: All credentials provided per-request
- **Memory Only**: Credentials never written to disk
- **Secure Transport**: HTTPS enforced for iDRAC communication
- **No Logging**: Credentials not logged

### SSL/TLS

- **SSL Verification**: Configurable (default: disabled for self-signed certs)
- **Production**: Enable SSL verification and use valid certificates

### Input Validation

- **Parameter Validation**: Pydantic validates all inputs
- **Type Safety**: Type annotations enforce correctness
- **Required Parameters**: Validated before API calls

### Error Messages

- **Sanitized Errors**: No credential leakage in error messages
- **Detailed Logging**: Debug info for troubleshooting (without credentials)

---


## References

- **MCP Protocol**: https://modelcontextprotocol.io/
- **FastMCP**: https://github.com/jlowin/fastmcp
- **Dell iDRAC Redfish API**: https://www.dell.com/support/manuals/idrac
- **JSONPath**: https://goessner.net/articles/JsonPath/
