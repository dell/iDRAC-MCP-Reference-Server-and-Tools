#!/usr/bin/env python3
# Licensed to You under the Apache License, Version 2.0

"""
MCP Client for Integration Testing

Connects to a running MCP server using the official MCP SDK.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional

try:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
except ImportError:
    raise ImportError(
        "MCP SDK not installed. Install with: pip install mcp>=1.0.0"
    )

logger = logging.getLogger(__name__)


class MCPClient:
    """Client for communicating with a running MCP server using official MCP SDK."""

    def __init__(self, base_url: str = "http://localhost:8000", timeout: int = 60):
        """
        Initialize MCP client.

        Args:
            base_url: Base URL of the MCP server
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip('/')
        # Ensure /mcp endpoint
        self.mcp_url = self.base_url if self.base_url.endswith('/mcp') else f"{self.base_url}/mcp"
        self.timeout = timeout
        self.session: Optional[ClientSession] = None
        self._context = None
        self._read = None
        self._write = None
        self._loop = None
        logger.info(f"MCP Client initialized for {self.mcp_url}")

    def _ensure_loop(self):
        """Ensure we have an event loop."""
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

    async def _connect_async(self) -> None:
        """Async connection to MCP server."""
        logger.info(f"Connecting to MCP server at {self.mcp_url}...")

        # Create streamable HTTP client
        self._context = streamablehttp_client(self.mcp_url)
        self._read, self._write, _ = await self._context.__aenter__()

        # Create session
        self.session = await ClientSession(self._read, self._write).__aenter__()

        # Initialize connection
        await self.session.initialize()

        logger.info("Successfully connected to MCP server")

    def connect(self) -> None:
        """Connect to MCP server (synchronous wrapper)."""
        self._ensure_loop()
        if self._loop.is_running():
            # If loop is already running, we can't use run_until_complete
            raise RuntimeError(
                "Cannot call connect() from an async context. Use await _connect_async() instead."
            )
        self._loop.run_until_complete(self._connect_async())

    async def list_tools_async(self) -> List[Dict[str, Any]]:
        """
        Get list of available tools from MCP server (async).

        Returns:
            List of tool definitions

        Raises:
            Exception: If request fails
        """
        if not self.session:
            await self._connect_async()

        try:
            response = await self.session.list_tools()
            tools = []

            for tool in response.tools:
                tools.append({
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.inputSchema
                })

            logger.info(f"Retrieved {len(tools)} tools from MCP server")
            return tools

        except Exception as e:
            logger.error(f"Failed to list tools: {e}")
            raise

    def list_tools(self) -> List[Dict[str, Any]]:
        """
        Get list of available tools from MCP server (synchronous wrapper).

        Returns:
            List of tool definitions

        Raises:
            Exception: If request fails
        """
        self._ensure_loop()
        if self._loop.is_running():
            # Already in async context
            raise RuntimeError(
                "Cannot call list_tools() from an async context. Use await list_tools_async() instead."
            )
        return self._loop.run_until_complete(self.list_tools_async())

    async def call_tool_async(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Execute a tool on the MCP server (async).

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            Tool execution result

        Raises:
            Exception: If tool execution fails
        """
        if not self.session:
            await self._connect_async()

        try:
            result = await self.session.call_tool(tool_name, arguments)

            # Extract text content from result
            if hasattr(result, 'content'):
                output = ""
                for item in result.content:
                    if hasattr(item, 'text'):
                        output += item.text
                return output if output else result
            else:
                return result

        except Exception as e:
            logger.error(f"Failed to call tool '{tool_name}': {e}")
            raise

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Execute a tool on the MCP server (synchronous wrapper).

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            Tool execution result

        Raises:
            Exception: If tool execution fails
        """
        self._ensure_loop()
        if self._loop.is_running():
            raise RuntimeError(
                "Cannot call call_tool() from an async context. Use await call_tool_async() instead."
            )
        return self._loop.run_until_complete(self.call_tool_async(tool_name, arguments))

    async def close_async(self) -> None:
        """Close the client connection (async)."""
        try:
            if self.session:
                try:
                    await self.session.__aexit__(None, None, None)
                except Exception as e:
                    logger.warning(f"Error closing session: {e}")

            if self._context:
                try:
                    await self._context.__aexit__(None, None, None)
                except Exception as e:
                    logger.warning(f"Error closing transport: {e}")
        except Exception:
            pass

    def close(self):
        """Close the HTTP client (synchronous wrapper)."""
        self._ensure_loop()
        if self._loop.is_running():
            # Schedule for later
            asyncio.create_task(self.close_async())
        else:
            self._loop.run_until_complete(self.close_async())

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
