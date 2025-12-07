#  Copyright 2025 Dell Inc. or its subsidiaries. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.


"""Main entry point for the Redfish MCP server."""

import argparse
import sys
import signal
from pathlib import Path

from .server.mcp_server import create_server


def setup_signal_handlers() -> None:
    """Set up signal handlers for graceful shutdown."""
    def signal_handler(signum, frame):
        """Handle shutdown signals gracefully."""
        sig_name = signal.Signals(signum).name
        print(f"\n\n[SIGNAL] Received {sig_name} signal")
        print("[SHUTDOWN] Shutting down gracefully...")
        sys.exit(0)

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Termination signal


def main() -> None:
    """Main entry point for the application."""
    parser = argparse.ArgumentParser(
        description="Dell iDRAC Redfish MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--openapi",
        type=str,
        default="config/openapi.yaml",
        help="Path to OpenAPI specification file (default: config/openapi.yaml)",
    )

    parser.add_argument(
        "--config",
        type=str,
        default="config/tools.yaml",
        help="Path to tools configuration file (default: config/tools.yaml)",
    )

    parser.add_argument(
        "--workflows",
        type=str,
        default="config/workflows.yaml",
        help="Path to workflows configuration file (default: config/workflows.yaml)",
    )

    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate configuration and exit without starting the server",
    )

    parser.add_argument(
        "--transport",
        type=str,
        default="streamable-http",
        choices=["streamable-http", "stdio"],
        help="Transport type: streamable-http (default) or stdio",
    )

    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind for HTTP transport (default: 0.0.0.0)",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind for HTTP transport (default: 8000)",
    )

    args = parser.parse_args()

    # Check if files exist
    if not Path(args.openapi).exists():
        print(f"Error: OpenAPI file not found: {args.openapi}", file=sys.stderr)
        sys.exit(1)

    if not Path(args.config).exists():
        print(f"Error: Tools configuration file not found: {args.config}", file=sys.stderr)
        sys.exit(1)

    # Set up graceful shutdown handlers
    setup_signal_handlers()

    # Check if workflows file exists (optional)
    workflows_file = args.workflows if Path(args.workflows).exists() else None
    if workflows_file:
        print(f"Using workflows: {workflows_file}")

    try:
        # Create the server
        server = create_server(
            openapi_file=args.openapi,
            tools_config_file=args.config,
            workflows_config_file=workflows_file,
        )

        if args.validate_only:
            print("Configuration validated successfully!")
            sys.exit(0)

        # Run the server
        server.run(
            transport=args.transport,
            host=args.host,
            port=args.port,
        )

    except KeyboardInterrupt:
        # This should be caught by signal handler, but just in case
        print("\n\n[SIGNAL] Received interrupt signal")
        print("[SHUTDOWN] Shutting down gracefully...")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
