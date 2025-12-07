
# Design Tenants for the MCP Tool and Workflow Architecture 

This document explains the key design tenants of the iDRAC MCP Servber reference implementation. 

Subsequently it also explores how MCP tools are generated from OpenAPI specifications and how workflows orchestrate multiple tools sequentially.

---

## Design Tenants

AI agents require fundamentally different interfaces compared to human developers. Achieving 100% task success versus 50% often depends on treating tool design as a first-class engineering discipline. This involves applying well-defined patterns for descriptions, schemas, error handling, and token efficiency.
There are numerous state-of-the-art resources available online that provide deeper insights into best practices for tool design. It is highly recommended that readers review these articles—particularly those published by industry leaders such as Anthropic and OpenAI—to gain a comprehensive understanding of effective approaches.

Agents process information token-by-token, have limited context windows, and operate non-deterministically. Considering this we have structured the design philosophy based on the following design tenants.

**Tenant 1: Choose tools with a clear purpose for agentic use cases.** Keep in mind that only about 10–20% of workflows may actually be exercised through agentic methods. Therefore, exposing every supported Systems Management Redfish API as a tool definition is likely unnecessary.
Instead, focus on the end agentic scenarios customers want to achieve. Based on those use cases, define tools that represent simple workflows or more complex ones involving multiple Redfish API calls. This approach ensures the toolset is aligned with real-world needs rather than exhaustive API coverage.

**Tenant 2: Design for token efficiency, not scale.** Token economics and efficiency will ultimately drive the viability of end-use applications. Therefore, every design decision should be made with token optimization in mind, ensuring that interfaces and workflows minimize unnecessary token usage while maintaining functionality.

**Tenant 3: Error messages should be instructive for the agent, providing clarity and actionable guidance for recovery within the agentic process.** Instead of simply signaling failure, they should include meaningful context and suggest corrective steps. Actionable feedback is a key characteristic of agent-friendly systems.

**Tenant 4: Tool definitions should be clear and descriptive.** A well-written description establishes the contract between your tool and the agent, ensuring proper usage and predictable outcomes. Adopting a description-first approach forces you to think through critical aspects—what the tool should do, when agents should use it, and what potential failure scenarios exist—before investing in implementation.


---

Following sections explore how MCP tools are generated from OpenAPI specifications and how workflow (as simple tool calls) definitions orchestrate multiple tools sequentially. 

The reference tool definition YAML file is derived from a one-to-one mapping between each tool and the corresponding Redfish OpenAPI YAML definition. Users can select the tools they need and, if required, define workflow-based tool definitions that execute multiple Redfish API calls within a single tool invocation. This approach enables both simple and complex workflows to be represented efficiently.


---

## Part 1: Tool Generation from Redfish OpenAPI YAML definitions 

This section outlines how the config/openapi.yaml (Redfish OpenAPI definition for iDRAC system management capabilities. This can be downloaded from an iDRAC at /redfish/v1/openapi.yaml) is mapped to config/tools_reference.yaml.

### Overview

Tools are generated through a 3-step mapping process:

```
OpenAPI YAML → Tool Configuration → Generated MCP Tool Function
```

### Step 1: OpenAPI Specification (Source)

**File**: `config/openapi.yaml`

The OpenAPI spec defines the raw Redfish API operations:

```yaml
paths:
  /redfish/v1/Systems/{ComputerSystemId}:
    get:
      operationId: GET_/redfish/v1/Systems/{ComputerSystemId}
      summary: Get information about a computer system
      parameters:
        - name: ComputerSystemId
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: System information
          content:
            application/json:
              schema:
                type: object
```

**Key Elements Extracted**:
- **Operation ID**: Unique identifier for the API operation
- **HTTP Method**: GET, POST, PUT, PATCH, DELETE
- **Path**: URL path with parameters
- **Parameters**: Location (path/query/header/body), type, required/optional
- **Request Body**: Schema for POST/PUT/PATCH operations
- **Response**: Expected response structure


### Step 2: Tool Configuration (Mapping)

**File**: `config/tools_reference.yaml`

Maps the OpenAPI operation to a user-friendly MCP tool:

```yaml
tools:
  - name: get_system_info                          # Tool name (user-facing)
    description: Get detailed information about a specific system
    operation_id: GET_/redfish/v1/Systems/{ComputerSystemId}  # Links to OpenAPI
    enabled: true
    category: system_info

    parameter_mappings:                            # Maps tool params → API params
      - tool_param_name: system_id                 # User-friendly name
        api_param_name: ComputerSystemId           # OpenAPI parameter name
        location: path                             # Where in the API request (path/query/header/body)
        description: The ID of the computer system
        required: true
        default: "System.Embedded.1"
```

**Mapping Process**:

| OpenAPI Element | Tool Config Element | Purpose |
|----------------|---------------------|---------|
| `operationId` | `operation_id` | Links tool definition to API operation |
| Parameter name | `api_param_name` | Original API parameter name |
| (none) | `tool_param_name` | User-friendly parameter name |
| `in: path/query/header` | `location` | Where parameter goes in HTTP request |
| `required: true/false` | `required` | Validation requirement |
| `schema.type` | (inferred) | Parameter type validation |


User shall pick and choose what they need as tools from config/tools_reference.yaml and define at config/tools.yaml for MCP reference server to consume. User shall also edit the name and description fields to match their requirements for the tool names.


### Step 3: Generated MCP Tool Function

**File**: `src/generators/tool_generator.py`

The `ToolGenerator` creates a callable Python function from the definitions in config/tools.yaml.

```python
# Generated function signature:
def get_system_info(
    idrac_ip: str,                    # Auto-added: iDRAC connection
    username: Optional[str] = None,   # Auto-added: Authentication
    password: Optional[str] = None,   # Auto-added: Authentication
    auth_token: Optional[str] = None, # Auto-added: Authentication
    system_id: str = "System.Embedded.1"  # From tool config mapping
) -> Dict[str, Any]:
    """Get detailed information about a specific system"""
    # Function implementation:
    # 1. Build credentials from idrac_ip/username/password/token
    # 2. Map system_id → ComputerSystemId
    # 3. Substitute {ComputerSystemId} in path → /redfish/v1/Systems/System.Embedded.1
    # 4. Make HTTP GET request to iDRAC
    # 5. Return JSON response
```

**Auto-Generated Elements**:

1. **Credential Parameters** (always added):
   - `idrac_ip`: Target iDRAC IP/hostname
   - `username`, `password`: Basic Authentication
   - `auth_token`: Token Authentication

2. **Function Signature**:
   - Built using Python `inspect.Parameter` and `inspect.Signature`
   - Preserves parameter order (required first, optional after)
   - Type annotations from `Annotated[type, description]`

3. **Function Metadata** (for MCP protocol):
   ```python
   tool_function.__name__ = "get_system_info"
   tool_function.__doc__ = "Get detailed information about a specific system"
   tool_function.__signature__ = sig  # Full parameter signature
   tool_function.__annotations__ = {
       'idrac_ip': str,
       'username': Optional[str],
       'system_id': str,
       'return': Dict[str, Any]
   }
   ```

4. **Execution Logic**:
   - Parameter mapping: `system_id` → `ComputerSystemId`
   - Path substitution: `{ComputerSystemId}` → actual value
   - Credential handling: Select Basic Auth or Token Auth
   - HTTP request construction and execution
   - Response parsing and error handling


### Mapping Example

**Input (OpenAPI)**:
```yaml
/redfish/v1/Systems/{ComputerSystemId}/Actions/ComputerSystem.Reset:
  post:
    operationId: POST_/redfish/v1/Systems/{ComputerSystemId}/Actions/ComputerSystem.Reset
    parameters:
      - name: ComputerSystemId
        in: path
        required: true
    requestBody:
      content:
        application/json:
          schema:
            type: object
            properties:
              ResetType:
                type: string
                enum: [On, ForceOff, GracefulShutdown, GracefulRestart, ForceRestart]
```


**Configuration (tools.yaml)**:
```yaml
- name: reset_system
  operation_id: POST_/redfish/v1/Systems/{ComputerSystemId}/Actions/ComputerSystem.Reset
  parameter_mappings:
    - tool_param_name: system_id
      api_param_name: ComputerSystemId
      location: path
      required: true
    - tool_param_name: reset_type
      api_param_name: ResetType
      location: body
      required: true
```


**Output (Generated Function)**:
```python
def reset_system(
    idrac_ip: str,
    system_id: str,
    reset_type: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
    auth_token: Optional[str] = None
) -> Dict[str, Any]:
    # Maps to: POST https://{idrac_ip}/redfish/v1/Systems/{system_id}/Actions/ComputerSystem.Reset
    # With body: {"ResetType": reset_type}
```

---

## Part 2: Workflow Execution for Token efficiency

### Overview

Workflows combine multiple tools into sequential operations that include data flow, conditional execution, and error handling. The underlying API calls are abstracted within these workflow tool calls, allowing them to be executed as a single request to the MCP server thus enabling token efficiency.

### Workflow Definition Structure

**File**: `config/workflows.yaml`

```yaml
workflows:
  - name: diagnose_system_health
    description: Comprehensive system health check
    category: diagnostics
    enabled: true

    # User inputs to the workflow
    inputs:
      - name: system_id
        type: string
        description: System ID to diagnose
        required: true
        default: "System.Embedded.1"

      - name: include_logs
        type: boolean
        required: false
        default: true

    # Sequential execution steps
    steps:
      - name: get_system_info
        tool: get_system_info                    # References a tool from tools.yaml
        parameters:
          system_id: ${{inputs.system_id}}       # Variable substitution
        outputs:
          health_status: "$.Status.Health"       # JSONPath extraction
          power_state: "$.PowerState"
        on_error: fail                           # Error handling strategy

      - name: get_memory
        tool: get_memory_info
        parameters:
          system_id: ${{inputs.system_id}}
        outputs:
          memory_count: "$.Members@odata.count"
        on_error: continue

      - name: get_event_logs
        tool: get_system_event_log
        condition: ${{inputs.include_logs}} == true  # Conditional execution
        parameters:
          manager_id: "iDRAC.Embedded.1"
        on_error: continue

    # Format the final output
    output:
      workflow_name: "System Health Diagnosis"
      system_id: ${{inputs.system_id}}
      summary:
        health: ${{steps.get_system_info.health_status}}
        power: ${{steps.get_system_info.power_state}}
        memory_modules: ${{steps.get_memory.memory_count}}
```

### Workflow Execution Flow

**File**: `src/generators/workflow_executor.py`

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. INITIALIZATION                                               │
│    - Validate workflow inputs (system_id, include_logs)         │
│    - Create execution context                                   │
│    - Store credentials (idrac_ip, username, password, token)    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. STEP EXECUTION (Sequential, One at a Time)                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
         ┌────────────────────────────────────────┐
         │ Step 1: get_system_info                │
         ├────────────────────────────────────────┤
         │ 1. Check condition: (none) → Execute   │
         │ 2. Substitute variables:               │
         │    system_id: ${{inputs.system_id}}    │
         │    → "System.Embedded.1"               │
         │ 3. Call tool function:                 │
         │    get_system_info(                    │
         │      idrac_ip="192.168.1.100",        │
         │      username="root",                  │
         │      password="calvin",                │
         │      system_id="System.Embedded.1"     │
         │    )                                   │
         │ 4. Extract outputs using JSONPath:     │
         │    health_status = result["Status"]["Health"]  │
         │    power_state = result["PowerState"]  │
         │ 5. Store in context:                   │
         │    steps.get_system_info.health_status │
         │    steps.get_system_info.power_state   │
         │ 6. Error handling: on_error = fail     │
         │    If error → Stop workflow            │
         └────────────────────────────────────────┘
                              ↓
         ┌────────────────────────────────────────┐
         │ Step 2: get_memory                     │
         ├────────────────────────────────────────┤
         │ 1. Check condition: (none) → Execute   │
         │ 2. Substitute variables:               │
         │    system_id: ${{inputs.system_id}}    │
         │    → "System.Embedded.1"               │
         │ 3. Call tool function:                 │
         │    get_memory_info(...)                │
         │ 4. Extract outputs:                    │
         │    memory_count = result["Members@odata.count"] │
         │ 5. Store: steps.get_memory.memory_count│
         │ 6. Error handling: on_error = continue │
         │    If error → Continue to next step    │
         └────────────────────────────────────────┘
                              ↓
         ┌────────────────────────────────────────┐
         │ Step 3: get_event_logs                 │
         ├────────────────────────────────────────┤
         │ 1. Check condition:                    │
         │    ${{inputs.include_logs}} == true    │
         │    → Evaluate: true → Execute          │
         │    (If false, skip this step)          │
         │ 2. Parameters: manager_id (static)     │
         │ 3. Call tool: get_system_event_log(...) │
         │ 4. Store outputs                       │
         │ 5. Error handling: on_error = continue │
         └────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. OUTPUT GENERATION                                            │
│    - Substitute all variables in output template:               │
│      ${{inputs.system_id}} → "System.Embedded.1"               │
│      ${{steps.get_system_info.health_status}} → "OK"          │
│      ${{steps.get_system_info.power_state}} → "On"            │
│      ${{steps.get_memory.memory_count}} → 24                  │
│    - Build final JSON output                                    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. RETURN RESULT                                                │
│    {                                                            │
│      "workflow_name": "System Health Diagnosis",               │
│      "system_id": "System.Embedded.1",                         │
│      "summary": {                                              │
│        "health": "OK",                                         │
│        "power": "On",                                          │
│        "memory_modules": 24                                    │
│      }                                                         │
│    }                                                           │
└─────────────────────────────────────────────────────────────────┘
```

### Key Workflow Features

#### 1. Variable Substitution

The executor supports multiple variable sources:

| Variable Type | Syntax | Example | Value |
|---------------|--------|---------|-------|
| Workflow inputs | `${{inputs.name}}` | `${{inputs.system_id}}` | User-provided value |
| Step outputs | `${{steps.step_name.output_name}}` | `${{steps.get_system_info.health_status}}` | Output from previous step |
| Workflow metadata | `${{workflow.name}}` | `${{workflow.timestamp}}` | Workflow execution metadata |
| Credentials | `${{credentials.idrac_ip}}` | (internal only) | Passed to tools automatically |

**Substitution Process**:
```python
# Example: parameters: { system_id: ${{inputs.system_id}} }
# 1. Find all ${{}}} patterns
# 2. Parse: inputs.system_id
# 3. Resolve: context.inputs['system_id'] = "System.Embedded.1"
# 4. Replace: system_id = "System.Embedded.1"
```

#### 2. JSONPath Output Extraction

Steps can extract specific fields from tool responses using JSONPath:

```yaml
outputs:
  health_status: "$.Status.Health"           # Simple path
  memory_count: "$.Members@odata.count"      # OData count
  all_members: "$.Members[*]"                # Array selection
```

**Extraction Process**:
```python
# Tool returns: {"Status": {"Health": "OK", "State": "Enabled"}, "PowerState": "On"}
# JSONPath: $.Status.Health
# Result: "OK"
# Stored as: context.step_outputs['get_system_info']['health_status'] = "OK"
```

#### 3. Conditional Execution

Steps can be conditionally executed:

```yaml
condition: ${{inputs.include_logs}} == true
```

**Evaluation**:
- Simple comparisons: `==`, `!=`, `>`, `<`, `>=`, `<=`
- Boolean logic: `true`, `false`
- If condition evaluates to `false`, step is skipped

#### 4. Error Handling Strategies

Each step defines how to handle errors:

| Strategy | Behavior |
|----------|----------|
| `fail` | Stop workflow immediately, return error |
| `continue` | Log error, store error in step output, continue to next step |
| `skip_remaining` | Stop executing remaining steps, but return success with partial results |

**Example**:
```python
# Step with on_error: continue
try:
    result = tool_function(...)
    context.step_outputs['step_name'] = result
except Exception as e:
    context.errors.append({'step': 'step_name', 'error': str(e)})
    context.step_outputs['step_name'] = {'error': str(e)}
    # Continue to next step
```

#### 5. Credential Propagation

Credentials are automatically passed to all underlying redfish calls associated with that tool call:

```python
# Workflow called with:
execute(workflow, idrac_ip="192.168.1.100", username="root", password="calvin", ...)

# Every tool call automatically receives:
tool_function(
    idrac_ip="192.168.1.100",  # From workflow
    username="root",            # From workflow
    password="calvin",          # From workflow
    **step_parameters           # From step definition
)
```

### Workflow as MCP Tool

Workflows are registered as MCP tools, making them indistinguishable from regular tools to the client:

**Registration** (`src/server/mcp_server.py`):
```python
# Generate tool schema (same as regular tools)
workflow_schema = {
    "name": "diagnose_system_health",
    "description": "[WORKFLOW] Comprehensive system health check",
    "inputSchema": {
        "type": "object",
        "properties": {
            "idrac_ip": {"type": "string", "description": "iDRAC IP"},
            "username": {"type": "string"},
            "password": {"type": "string"},
            "system_id": {"type": "string", "default": "System.Embedded.1"},
            "include_logs": {"type": "boolean", "default": true}
        },
        "required": ["idrac_ip"]
    }
}

# Create wrapper function
def workflow_function(idrac_ip, system_id, include_logs, username=None, password=None):
    return workflow_executor.execute(workflow, idrac_ip, username, password,
                                     system_id=system_id, include_logs=include_logs)

# Set function metadata (same as regular tools)
workflow_function.__name__ = "diagnose_system_health"
workflow_function.__signature__ = sig
workflow_function.__annotations__ = {...}

# Register with MCP
mcp.tool(name="diagnose_system_health", description="...")(workflow_function)
```

From the client's perspective:
```python
# Calling a workflow looks identical to calling a tool:
result = mcp_client.call_tool(
    "diagnose_system_health",
    {
        "idrac_ip": "192.168.1.100",
        "username": "root",
        "password": "calvin",
        "system_id": "System.Embedded.1",
        "include_logs": True
    }
)
```

---
