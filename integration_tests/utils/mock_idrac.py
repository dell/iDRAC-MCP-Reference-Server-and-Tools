# Licensed to You under the Apache License, Version 2.0

"""
Mock iDRAC Server for Integration Testing.

This module provides a mock HTTP server that simulates a Dell iDRAC Redfish API
for testing purposes. It responds to common Redfish endpoints with realistic data.
"""

import json
import base64
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from pathlib import Path
from typing import Dict, Any, Optional
import time


class MockiDRACHandler(BaseHTTPRequestHandler):
    """HTTP request handler for mock iDRAC server."""

    # Class variable to store mock responses
    mock_responses: Dict[str, Any] = {}

    # Valid credentials for testing
    valid_credentials = {
        "basic": {"username": "admin", "password": "password123"},
        "token": "mock-x-auth-token-12345"
    }

    def _send_json_response(self, status_code: int, data: Dict[str, Any]) -> None:
        """Send JSON response."""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def _send_error_response(self, status_code: int, message: str) -> None:
        """Send error response in Redfish format."""
        error_response = {
            "error": {
                "@Message.ExtendedInfo": [
                    {
                        "Message": message,
                        "MessageId": f"Base.1.0.{status_code}",
                        "Severity": "Critical" if status_code >= 500 else "Warning"
                    }
                ]
            }
        }
        self._send_json_response(status_code, error_response)

    def _check_authentication(self) -> bool:
        """Check if request has valid authentication."""
        # Check for X-Auth-Token header
        auth_token = self.headers.get('X-Auth-Token')
        if auth_token == self.valid_credentials["token"]:
            return True

        # Check for Basic Auth
        auth_header = self.headers.get('Authorization')
        if auth_header and auth_header.startswith('Basic '):
            try:
                encoded_creds = auth_header.replace('Basic ', '')
                decoded_creds = base64.b64decode(encoded_creds).decode('utf-8')
                username, password = decoded_creds.split(':', 1)

                if (username == self.valid_credentials["basic"]["username"] and
                    password == self.valid_credentials["basic"]["password"]):
                    return True
            except Exception:
                pass

        return False

    def _get_response_for_path(self, path: str, method: str) -> Optional[Dict[str, Any]]:
        """Get mock response for a given path."""
        # Remove query parameters and fragments
        from urllib.parse import urlparse
        parsed = urlparse(path)
        path = parsed.path

        # Normalize path (remove trailing slash)
        path = path.rstrip('/')

        # Map paths to responses
        if path == '/redfish/v1':
            return self.mock_responses.get('service_root')
        elif path == '/redfish/v1/Systems':
            return self.mock_responses.get('systems_collection')
        elif path.startswith('/redfish/v1/Systems/System.Embedded.1'):
            if '/Actions/ComputerSystem.Reset' in path and method == 'POST':
                return self.mock_responses.get('reset_success')
            else:
                return self.mock_responses.get('system_info')

        return None

    def do_GET(self) -> None:
        """Handle GET requests."""
        # Check authentication
        if not self._check_authentication():
            self._send_error_response(401, "Unauthorized - Invalid credentials")
            return

        # Get response for path
        response = self._get_response_for_path(self.path, 'GET')

        if response:
            self._send_json_response(200, response)
        else:
            self._send_error_response(404, f"Resource not found: {self.path}")

    def do_POST(self) -> None:
        """Handle POST requests."""
        # Check authentication
        if not self._check_authentication():
            self._send_error_response(401, "Unauthorized - Invalid credentials")
            return

        # Read request body
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b'{}'

        try:
            request_data = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError:
            self._send_error_response(400, "Invalid JSON in request body")
            return

        # Get response for path
        response = self._get_response_for_path(self.path, 'POST')

        if response:
            # For reset operations, validate ResetType
            if 'Actions/ComputerSystem.Reset' in self.path:
                reset_type = request_data.get('ResetType')
                valid_types = ['On', 'ForceOff', 'ForceRestart', 'GracefulShutdown',
                              'GracefulRestart', 'PushPowerButton', 'Nmi']
                if reset_type not in valid_types:
                    self._send_error_response(400, f"Invalid ResetType: {reset_type}")
                    return

            self._send_json_response(200, response)
        else:
            self._send_error_response(404, f"Resource not found: {self.path}")

    def do_OPTIONS(self) -> None:
        """Handle OPTIONS requests (for CORS)."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Auth-Token')
        self.end_headers()

    def log_message(self, format: str, *args) -> None:
        """Override to suppress request logging."""
        # Comment out to see request logs
        pass


class MockiDRACServer:
    """
    Mock iDRAC server for integration testing.

    This server simulates a Dell iDRAC Redfish API and can be used
    for testing without requiring actual hardware.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8888):
        """
        Initialize mock iDRAC server.

        Args:
            host: Host to bind to
            port: Port to bind to
        """
        self.host = host
        self.port = port
        self.server: Optional[HTTPServer] = None
        self.thread: Optional[Thread] = None
        self._load_mock_responses()

    def _load_mock_responses(self) -> None:
        """Load mock responses from JSON file."""
        mock_responses_file = Path(__file__).parent.parent / 'config' / 'mock_responses.json'

        with open(mock_responses_file, 'r') as f:
            MockiDRACHandler.mock_responses = json.load(f)

    def start(self) -> None:
        """Start the mock server in a background thread."""
        self.server = HTTPServer((self.host, self.port), MockiDRACHandler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

        # Wait a bit for server to start
        time.sleep(0.5)

        print(f"[INFO] Mock iDRAC server started at http://{self.host}:{self.port}")

    def stop(self) -> None:
        """Stop the mock server."""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            print(f"[INFO] Mock iDRAC server stopped")

    def get_base_url(self) -> str:
        """Get the base URL of the mock server."""
        return f"http://{self.host}:{self.port}"

    def get_credentials(self, auth_type: str = "basic") -> Dict[str, str]:
        """
        Get test credentials.

        Args:
            auth_type: Type of authentication ('basic' or 'token')

        Returns:
            Dictionary with credentials
        """
        if auth_type == "basic":
            return {
                "username": "admin",
                "password": "password123"
            }
        elif auth_type == "token":
            return {
                "auth_token": "mock-x-auth-token-12345"
            }
        else:
            raise ValueError(f"Unknown auth_type: {auth_type}")


# For standalone testing
if __name__ == "__main__":
    server = MockiDRACServer(host="127.0.0.1", port=8888)
    try:
        server.start()
        print("[INFO] Mock iDRAC server running. Press Ctrl+C to stop.")
        print(f"[INFO] Base URL: {server.get_base_url()}")
        print(f"[INFO] Test with: curl -u admin:password123 {server.get_base_url()}/redfish/v1/")

        # Keep running
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[INFO] Shutting down...")
        server.stop()
