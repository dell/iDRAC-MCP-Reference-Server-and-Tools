# iDRAC MCP Client

MCP client for Dell iDRAC Redfish server management with interactive mode, CLI mode, and programmatic API.

## Features

- **Auto-discovery** - Discovers all available tools from the server
- **Self-documenting** - Parameters extracted from server schemas
- **Interactive Mode** - Guided parameter input with validation
- **CLI Mode** - Script-friendly command-line interface
- **Programmatic API** - Use in Python automation scripts
- **Type Validation** - Automatic parameter type checking
- **Dual Transport** - Streamable-HTTP and STDIO support

## Quick Start

### Installation

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Start the Client

```bash
# Interactive mode (streamable-http transport, default)
python -m client.idrac_mcp_client

# With custom server
python -m client.idrac_mcp_client --server http://<>:8000

# STDIO transport (local server)
python -m client.idrac_mcp_client --transport stdio
```

## Usage Modes

### 1. Interactive Mode (Recommended)

Best for exploration and testing:

```bash
python -m client.idrac_mcp_client
```

**Commands:**
- `list` - Show all available tools
- `info <tool>` - Get detailed tool information
- `call` - Call a tool with guided input
- `creds` - Save credentials for session
- `quit` - Exit


### 2. Command-Line Mode

Perfect for scripting:

```bash
# List all tools
python -m client.idrac_mcp_client --list

# Get tool information
python -m client.idrac_mcp_client --info get_system_info

# Call a tool
python -m client.idrac_mcp_client --call get_system_info \
  --arg idrac_ip=<> \
  --arg username=<username> \
  --arg password=<password> \
  --arg system_id=System.Embedded.1

# Call with JSON arguments
python -m client.idrac_mcp_client --call get_service_root \
  --json '{"idrac_ip":"<>","username":"<username>","password":"<password>"}'
```

### 3. Programmatic Mode

For Python automation:

```python
import asyncio
from client.idrac_mcp_client import IdracMCPClient

async def main():
    client = IdracMCPClient(
        transport="streamable-http",
        server_url="http://localhost:8000"
    )

    try:
        # Connect and discover tools
        await client.connect()

        # List available tools
        print(f"Discovered {len(client.tools)} tools")

        # Call a tool
        result = await client.call_tool(
            "get_system_info",
            {
                "idrac_ip": "<>",
                "username": "<username>",
                "password": "password",
                "system_id": "System.Embedded.1",
            }
        )

        print(result)

    finally:
        await client.close()

asyncio.run(main())
```

## Required Parameters

All tools require these authentication parameters:

1. **idrac_ip** - iDRAC IP address  - ALWAYS required

**For Basic Authentication:**
2. **username** - iDRAC username
3. **password** - iDRAC password

**For Token Authentication:**
2. **auth_token** - iDRAC X-Auth-Token (username/password not needed)

## Examples

### Example 1: Explore Available Tools

```bash
# List all tools
python -m client.idrac_mcp_client --list

# Get info about a specific tool
python -m client.idrac_mcp_client --info get_system_info
```


### Example 2: Power Management

```bash
# Check power state
python -m client.idrac_mcp_client --call get_system_info \
  --arg idrac_ip=<> \
  --arg username=<username> \
  --arg password=<password> \
  --arg system_id=System.Embedded.1

# Power on system
python -m client.idrac_mcp_client --call reset_system \
  --arg idrac_ip=<> \
  --arg username=<username> \
  --arg password=<password> \
  --arg system_id=System.Embedded.1 \
  --arg reset_type=On
```

### Example 3: Python Automation

```python
import asyncio
from client.idrac_mcp_client import IdracMCPClient

async def check_systems():
    """Check power state of all systems."""
    client = IdracMCPClient()

    try:
        await client.connect()

        # Get list of systems
        result = await client.call_tool(
            "list_systems",
            {
                "idrac_ip": "<>",
                "username": "<username>",
                "password": "<password>"
            }
        )

        # Check each system
        for system in result.systems:
            info = await client.call_tool(
                "get_system_info",
                {
                    "idrac_ip": "<>",
                    "username": "<username>",
                    "password": "<password>",
                    "system_id": system["Id"],
                }
            )
            print(f"{system['Id']}: {info['PowerState']}")

    finally:
        await client.close()

asyncio.run(check_systems())
```

## Testing

See the [Integration Test Suite](../README_INTEGRATION_TESTS.md) at the project root for comprehensive testing documentation that demonstrates client usage patterns.

## Configuration

### Transport Options

**Streamable-HTTP (Default):**
- Use when server runs in Docker or remote
- Requires server URL

```bash
python -m client.idrac_mcp_client --server http://<>:8000
```

**STDIO:**
- Use when server runs locally
- Single connection per process

```bash
python -m client.idrac_mcp_client --transport stdio
```

## Requirements

- Python 3.9+
- Running MCP iDRAC Server
- Network access to both MCP server and iDRAC


## Support

For server documentation, see `../mcp_idrac_server/README.md`
For Docker deployment, see `../mcp_idrac_server/DOCKER_DEPLOYMENT.md`
