#!/usr/bin/env python3
# Licensed to You under the Apache License, Version 2.0

"""
Standalone Mock iDRAC Server

Runs as a separate process to simulate Dell iDRAC Redfish API.
Can be used by multiple clients (MCP server, tests, etc.)
"""

import sys
import argparse
import signal
import logging
from pathlib import Path

# Configure logging with timestamps
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Add paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'integration_tests'))

from utils.mock_idrac import MockiDRACServer


def main():
    """Run standalone mock iDRAC server."""
    parser = argparse.ArgumentParser(
        description="Standalone Mock iDRAC Redfish API Server"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8002,
        help="Port to bind to (default: 8002)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Set log level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("=" * 60)
    logger.info("Mock iDRAC Redfish API Server")
    logger.info("=" * 60)

    # Create and start server
    print(f"[MOCK] Starting Mock iDRAC server...")
    print(f"[MOCK] Host: {args.host}")
    print(f"[MOCK] Port: {args.port}")

    server = MockiDRACServer(host=args.host, port=args.port)

    # Setup signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        print("\n[MOCK] Shutting down...")
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start server
    server.start()

    # Get credentials
    credentials = server.get_credentials("basic")

    print(f"\n[MOCK] Mock iDRAC server is running")
    print(f"[MOCK] Base URL: http://{args.host}:{args.port}")
    print(f"[MOCK] Username: {credentials['username']}")
    print(f"[MOCK] Password: {credentials['password']}")
    print(f"\n[MOCK] Available endpoints:")
    print(f"[MOCK]   - http://{args.host}:{args.port}/redfish/v1/")
    print(f"[MOCK]   - http://{args.host}:{args.port}/redfish/v1/Systems")
    print(f"[MOCK]   - http://{args.host}:{args.port}/redfish/v1/Managers")
    print(f"\n[MOCK] Press Ctrl+C to stop")

    # Keep running
    try:
        while True:
            signal.pause()
    except (KeyboardInterrupt, SystemExit):
        print("\n[MOCK] Shutting down...")
        server.stop()


if __name__ == "__main__":
    main()
