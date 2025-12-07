#!/usr/bin/env python3
# Licensed to You under the Apache License, Version 2.0

"""
iDRAC MCP client with automatic tool discovery and parameter introspection.

This client connects to the iDRAC MCP server, automatically discovers all
available tools, and provides interactive guidance for using them.
"""

import asyncio
import json
import sys
from typing import Any, Dict, Optional, List
from dataclasses import dataclass

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.streamable_http import streamablehttp_client
except ImportError:
    print("Error: mcp package not found. Install with: pip install mcp")
    sys.exit(1)


@dataclass
class ToolParameter:
    """Represents a tool parameter with its metadata."""
    name: str
    param_type: str
    description: str
    required: bool
    default: Optional[Any] = None
    enum: Optional[List[str]] = None


@dataclass
class ToolInfo:
    """Complete information about a discovered tool."""
    name: str
    description: str
    parameters: List[ToolParameter]
    category: Optional[str] = None


class IdracMCPClient:
    """
    iDRAC MCP client that discovers tools and parameters automatically.

    Features:
    - Automatic tool discovery
    - Parameter introspection
    - Interactive parameter input with validation
    - Dynamic tool calling
    - Dual transport support (streamable-http and stdio)
    """

    def __init__(
        self,
        transport: str = "streamable-http",
        server_url: str = "http://localhost:8000",
        server_command: Optional[str] = None
    ):
        """
        Initialize the dynamic client.

        Args:
            transport: Transport type ("streamable-http" or "stdio")
            server_url: Server URL for HTTP transport (default: http://localhost:8000)
            server_command: Command to start the server for STDIO transport
        """
        self.transport = transport
        self.server_url = server_url
        self.server_command = server_command or sys.executable
        self.session: Optional[ClientSession] = None
        self.tools: Dict[str, ToolInfo] = {}
        self.read = None
        self.write = None
        self._context = None

    async def connect(self) -> None:
        """Connect to the MCP server and discover tools."""
        print(f"[INFO] Connecting to MCP server via {self.transport}...")

        if self.transport == "streamable-http":
            # Streamable HTTP transport
            mcp_url = self.server_url if self.server_url.endswith('/mcp') else f"{self.server_url}/mcp"
            print(f"       Server: {mcp_url}")

            self._context = streamablehttp_client(mcp_url)
            self.read, self.write, _ = await self._context.__aenter__()
            self.session = await ClientSession(self.read, self.write).__aenter__()

        elif self.transport == "stdio":
            # STDIO transport
            server_params = StdioServerParameters(
                command=self.server_command,
                args=["-m", "src"],
                env=None,
            )
            print(f"       Command: {self.server_command} -m src")

            self._context = stdio_client(server_params)
            self.read, self.write = await self._context.__aenter__()
            self.session = await ClientSession(self.read, self.write).__aenter__()

        else:
            raise ValueError(f"Unsupported transport: {self.transport}. Use 'streamable-http' or 'stdio'")

        # Initialize connection
        await self.session.initialize()
        print("[SUCCESS] Connected to MCP server\n")

        # Discover tools
        await self.discover_tools()

    async def discover_tools(self) -> None:
        """Discover all available tools and their parameters."""
        if not self.session:
            raise RuntimeError("Not connected to server")

        print("[INFO] Discovering available tools...")
        response = await self.session.list_tools()

        for tool in response.tools:
            # Parse tool schema
            tool_info = self._parse_tool_schema(
                name=tool.name,
                description=tool.description,
                schema=tool.inputSchema
            )
            self.tools[tool.name] = tool_info

        print(f"[SUCCESS] Discovered {len(self.tools)} tools\n")

    def _parse_tool_schema(
        self,
        name: str,
        description: str,
        schema: Dict[str, Any]
    ) -> ToolInfo:
        """
        Parse tool schema into ToolInfo.

        Args:
            name: Tool name
            description: Tool description
            schema: JSON schema for tool parameters

        Returns:
            ToolInfo object with parsed parameters
        """
        parameters = []
        properties = schema.get("properties", {})
        required_params = schema.get("required", [])

        for param_name, param_schema in properties.items():
            param = ToolParameter(
                name=param_name,
                param_type=param_schema.get("type", "string"),
                description=param_schema.get("description", "No description"),
                required=param_name in required_params,
                default=param_schema.get("default"),
                enum=param_schema.get("enum"),
            )
            parameters.append(param)

        return ToolInfo(
            name=name,
            description=description,
            parameters=parameters,
        )

    def list_tools(self, category: Optional[str] = None) -> None:
        """
        Display all discovered tools with their descriptions.

        Args:
            category: Optional category filter
        """
        print("=" * 80)
        print("AVAILABLE TOOLS")
        print("=" * 80)

        # Group tools by category (inferred from name prefixes)
        categorized = self._categorize_tools()

        for cat, tools in sorted(categorized.items()):
            if category and cat.lower() != category.lower():
                continue

            print(f"\n[{cat}]")
            print("-" * 80)
            for tool_name in sorted(tools):
                tool = self.tools[tool_name]
                print(f"  * {tool.name}")
                print(f"    {tool.description}")
                print(f"    Parameters: {len(tool.parameters)} "
                      f"({len([p for p in tool.parameters if p.required])} required)")
        print()

    def _categorize_tools(self) -> Dict[str, List[str]]:
        """Categorize tools based on naming patterns."""
        categories: Dict[str, List[str]] = {}

        for tool_name in self.tools:
            # Infer category from tool name
            if "system" in tool_name or "list_systems" in tool_name:
                category = "System Management"
            elif "bios" in tool_name:
                category = "BIOS Configuration"
            elif "memory" in tool_name or "ethernet" in tool_name:
                category = "Hardware Inventory"
            elif "reset" in tool_name or "power" in tool_name:
                category = "Power Control"
            elif "account" in tool_name or "user" in tool_name:
                category = "User Management"
            elif "manager" in tool_name:
                category = "iDRAC Management"
            elif "service" in tool_name:
                category = "Service Information"
            else:
                category = "Other"

            if category not in categories:
                categories[category] = []
            categories[category].append(tool_name)

        return categories

    def show_tool_info(self, tool_name: str) -> None:
        """
        Display detailed information about a specific tool.

        Args:
            tool_name: Name of the tool
        """
        if tool_name not in self.tools:
            print(f"[ERROR] Tool '{tool_name}' not found")
            return

        tool = self.tools[tool_name]

        print("=" * 80)
        print(f"TOOL: {tool.name}")
        print("=" * 80)
        print(f"\nDescription:")
        print(f"  {tool.description}\n")

        # Authentication parameters
        auth_params = [p for p in tool.parameters if p.name in
                      ["username", "password", "auth_token", "token"]]

        # Other parameters
        other_params = [p for p in tool.parameters if p.name not in
                       ["username", "password", "auth_token", "token"]]

        if auth_params:
            print("Authentication Parameters:")
            for param in auth_params:
                self._print_parameter(param)

        if other_params:
            print("\nTool Parameters:")
            for param in other_params:
                self._print_parameter(param)

        print("\n" + "=" * 80)

    def _print_parameter(self, param: ToolParameter) -> None:
        """Print parameter information."""
        required_mark = "REQUIRED" if param.required else "optional"
        print(f"\n  * {param.name} ({param.param_type}) [{required_mark}]")
        print(f"    {param.description}")

        if param.default is not None:
            print(f"    Default: {param.default}")

        if param.enum:
            print(f"    Allowed values: {', '.join(param.enum)}")

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Any:
        """
        Call a tool with provided arguments.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        if not self.session:
            raise RuntimeError("Not connected to server")

        if tool_name not in self.tools:
            raise ValueError(f"Tool '{tool_name}' not found")

        # Validate arguments
        self._validate_arguments(tool_name, arguments)

        print(f"\n{'='*80}")
        print(f"[EXECUTING] {tool_name}")
        print('='*80)
        print(f"Arguments:")
        for key, value in arguments.items():
            # Mask password
            display_value = "***" if "password" in key.lower() else value
            print(f"   {key}: {display_value}")

        try:
            result = await self.session.call_tool(tool_name, arguments)
            print("\n[SUCCESS] Tool execution successful")
            return result
        except Exception as e:
            print(f"\n[ERROR] Tool execution failed: {e}")
            raise

    def _validate_arguments(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> None:
        """
        Validate that all required arguments are provided.

        Args:
            tool_name: Name of the tool
            arguments: Provided arguments

        Raises:
            ValueError: If validation fails
        """
        tool = self.tools[tool_name]

        # Check required parameters
        missing = []
        for param in tool.parameters:
            if param.required and param.name not in arguments:
                missing.append(param.name)

        if missing:
            raise ValueError(
                f"Missing required parameters: {', '.join(missing)}"
            )

    async def interactive_mode(self) -> None:
        """Run the client in interactive mode with guided input."""
        print("\n" + "=" * 80)
        print("INTERACTIVE MODE")
        print("=" * 80)
        print("\nType 'help' for commands, 'quit' to exit\n")

        # Common credentials (can be set once)
        credentials = {}

        while True:
            try:
                # Main menu
                print("\n" + "-" * 80)
                command = input("Command [list/info/call/creds/quit]: ").strip().lower()

                if command == "quit" or command == "q":
                    print("Goodbye!")
                    break

                elif command == "help" or command == "h":
                    self._print_help()

                elif command == "list" or command == "l":
                    self.list_tools()

                elif command == "creds" or command == "c":
                    credentials = await self._set_credentials()

                elif command == "info" or command == "i":
                    tool_name = input("Tool name: ").strip()
                    self.show_tool_info(tool_name)

                elif command == "call":
                    await self._interactive_call(credentials)

                else:
                    print("[ERROR] Unknown command. Type 'help' for available commands.")

            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except Exception as e:
                print(f"\n[ERROR] {e}")

    def _print_help(self) -> None:
        """Print help information."""
        print("\n" + "=" * 80)
        print("AVAILABLE COMMANDS")
        print("=" * 80)
        print("  list (l)   - List all available tools")
        print("  info (i)   - Show detailed information about a tool")
        print("  call       - Call a tool with parameters")
        print("  creds (c)  - Set default credentials")
        print("  help (h)   - Show this help message")
        print("  quit (q)   - Exit the client")
        print("=" * 80)

    async def _set_credentials(self) -> Dict[str, str]:
        """Interactively set credentials."""
        print("\nSet Default Credentials")
        print("-" * 80)

        username = input("Username: ").strip()

        # Hide password input
        import getpass
        password = getpass.getpass("Password: ")

        credentials = {
            "username": username,
            "password": password,
        }

        print("[SUCCESS] Credentials saved for this session")
        return credentials

    async def _interactive_call(self, default_credentials: Dict[str, str]) -> None:
        """Interactive tool call with guided parameter input."""
        # Select tool
        print("\n" + "=" * 80)
        print("CALL TOOL")
        print("=" * 80)

        tool_name = input("\nTool name (or 'list' to see all): ").strip()

        if tool_name.lower() == "list":
            self.list_tools()
            return

        if tool_name not in self.tools:
            print(f"[ERROR] Tool '{tool_name}' not found")
            return

        tool = self.tools[tool_name]

        print(f"\n{tool.description}\n")

        # Build arguments
        arguments = {}

        # Add default credentials if available
        if default_credentials:
            use_default = input("Use saved credentials? [Y/n]: ").strip().lower()
            if use_default != "n":
                arguments.update(default_credentials)

        # Get other parameters
        for param in tool.parameters:
            # Skip if already provided via credentials
            if param.name in arguments:
                continue

            # Skip password-related if using default creds
            if default_credentials and param.name in ["password", "username", "auth_token"]:
                continue

            # Show parameter info
            required_text = "[REQUIRED]" if param.required else "[optional]"
            default_text = f" (default: {param.default})" if param.default else ""

            print(f"\n{param.name} {required_text}{default_text}")
            print(f"  Type: {param.param_type}")
            print(f"  {param.description}")

            if param.enum:
                print(f"  Allowed: {', '.join(param.enum)}")

            # Get input
            if param.name == "password" and param.name not in arguments:
                import getpass
                value = getpass.getpass(f"  Enter value: ")
            else:
                prompt = "  Enter value"
                if not param.required:
                    prompt += " (press Enter to skip)"
                prompt += ": "
                value = input(prompt).strip()

            # Use default if empty and available
            if not value and param.default is not None:
                value = param.default

            # Convert type
            if value:
                try:
                    if param.param_type == "integer":
                        value = int(value)
                    elif param.param_type == "number":
                        value = float(value)
                    elif param.param_type == "boolean":
                        value = value.lower() in ("true", "yes", "1", "y")

                    arguments[param.name] = value
                except ValueError as e:
                    print(f"  [WARNING] Invalid type, using as string")
                    arguments[param.name] = value

        # Confirm and execute
        print(f"\n{'='*80}")
        print("CALL SUMMARY")
        print('='*80)
        print(f"Tool: {tool_name}")
        print(f"Arguments:")
        for key, value in arguments.items():
            display_value = "***" if "password" in key.lower() else value
            print(f"  {key}: {display_value}")

        confirm = input("\nExecute this call? [Y/n]: ").strip().lower()
        if confirm == "n":
            print("[CANCELLED] Call cancelled")
            return

        # Execute
        try:
            result = await self.call_tool(tool_name, arguments)

            # Display result
            print(f"\n{'='*80}")
            print("RESULT")
            print('='*80)

            # Pretty print the result
            if hasattr(result, 'content'):
                for item in result.content:
                    if hasattr(item, 'text'):
                        try:
                            # Try to parse as JSON for pretty printing
                            data = json.loads(item.text)
                            print(json.dumps(data, indent=2))
                        except:
                            print(item.text)
            else:
                print(json.dumps(result, indent=2))

        except Exception as e:
            print(f"\n[ERROR] Error executing tool: {e}")

    async def close(self) -> None:
        """Close the client connection."""
        try:
            # Close session first
            if self.session:
                try:
                    await self.session.__aexit__(None, None, None)
                except Exception as e:
                    print(f"Warning: Error closing session: {e}")

            # Close the transport context
            if self._context:
                try:
                    await self._context.__aexit__(None, None, None)
                except Exception as e:
                    print(f"Warning: Error closing transport: {e}")
        except Exception as e:
            # Silently handle any cleanup errors during quit
            pass


async def main() -> None:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="iDRAC MCP Client for Dell iDRAC Redfish API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode (recommended)
  python -m client.idrac_mcp_client

  # List all available tools
  python -m client.idrac_mcp_client --list

  # Show tool information
  python -m client.idrac_mcp_client --info get_system_info

  # Call a tool directly
  python -m client.idrac_mcp_client --call get_system_info \\
    --arg idrac_ip=192.168.1.100 --arg username=admin --arg password=mypass --arg system_id=System.Embedded.1

  # Call with JSON arguments
  python -m client.idrac_mcp_client --call reset_system \\
    --json '{"idrac_ip":"192.168.1.100","username":"admin","password":"mypass","system_id":"System.Embedded.1","reset_type":"On"}'
        """
    )

    parser.add_argument(
        "--transport", "-t",
        type=str,
        default="streamable-http",
        choices=["streamable-http", "stdio"],
        help="Transport type (default: streamable-http)"
    )

    parser.add_argument(
        "--server", "-s",
        type=str,
        default="http://localhost:8000",
        help="Server URL for HTTP transport (default: http://localhost:8000)"
    )

    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List all available tools and exit"
    )

    parser.add_argument(
        "--info", "-i",
        type=str,
        metavar="TOOL",
        help="Show detailed information about a tool and exit"
    )

    parser.add_argument(
        "--call", "-c",
        type=str,
        metavar="TOOL",
        help="Call a specific tool"
    )

    parser.add_argument(
        "--arg", "-a",
        action="append",
        metavar="KEY=VALUE",
        help="Tool argument (can be used multiple times)"
    )

    parser.add_argument(
        "--json", "-j",
        type=str,
        metavar="JSON",
        help="Tool arguments as JSON string"
    )

    args = parser.parse_args()

    # Create client with specified transport
    client = IdracMCPClient(
        transport=args.transport,
        server_url=args.server
    )

    try:
        await client.connect()

        if args.list:
            # List mode
            client.list_tools()

        elif args.info:
            # Info mode
            client.show_tool_info(args.info)

        elif args.call:
            # Call mode
            arguments = {}

            if args.json:
                arguments = json.loads(args.json)
            elif args.arg:
                for arg in args.arg:
                    if "=" not in arg:
                        print(f"[ERROR] Invalid argument format: {arg}")
                        print("        Expected: key=value")
                        sys.exit(1)
                    key, value = arg.split("=", 1)
                    arguments[key] = value

            result = await client.call_tool(args.call, arguments)

            # Display result
            print(f"\n{'='*80}")
            print("RESULT")
            print('='*80)
            if hasattr(result, 'content'):
                for item in result.content:
                    if hasattr(item, 'text'):
                        try:
                            data = json.loads(item.text)
                            print(json.dumps(data, indent=2))
                        except:
                            print(item.text)
            else:
                print(json.dumps(result, indent=2))

        else:
            # Interactive mode (default)
            await client.interactive_mode()

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
