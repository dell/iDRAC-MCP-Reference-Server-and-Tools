# Copyright 2025 Dell Inc. or its subsidiaries. All Rights Reserved.
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

"""Authentication handlers for Redfish API."""

from typing import Optional, Dict, Any
from dataclasses import dataclass
import base64


@dataclass
class Credentials:
    """Credentials for API authentication."""

    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None


class AuthenticationHandler:
    """
    Base class for authentication handlers.

    Subclasses implement specific authentication methods for Redfish API.
    """

    def get_auth_headers(self, credentials: Credentials) -> Dict[str, str]:
        """
        Get authentication headers for API requests.

        Args:
            credentials: User credentials

        Returns:
            Dictionary of HTTP headers
        """
        raise NotImplementedError("Subclasses must implement get_auth_headers")

    def validate_credentials(self, credentials: Credentials) -> bool:
        """
        Validate that credentials contain required information.

        Args:
            credentials: User credentials to validate

        Returns:
            True if credentials are valid, False otherwise
        """
        raise NotImplementedError("Subclasses must implement validate_credentials")


class BasicAuthHandler(AuthenticationHandler):
    """Handler for HTTP Basic Authentication."""

    def get_auth_headers(self, credentials: Credentials) -> Dict[str, str]:
        """
        Get Basic Auth headers.

        Args:
            credentials: Must contain username and password

        Returns:
            Dictionary with Authorization header
        """
        if not self.validate_credentials(credentials):
            raise ValueError("Username and password are required for Basic Auth")

        # Create Basic Auth header
        auth_string = f"{credentials.username}:{credentials.password}"
        auth_bytes = auth_string.encode("utf-8")
        auth_base64 = base64.b64encode(auth_bytes).decode("utf-8")

        return {"Authorization": f"Basic {auth_base64}"}

    def validate_credentials(self, credentials: Credentials) -> bool:
        """Validate that username and password are provided."""
        return bool(credentials.username and credentials.password)


class TokenAuthHandler(AuthenticationHandler):
    """
    Handler for Token-based Authentication.

    Supports both pre-existing tokens and session tokens using X-Auth-Token header.
    This unified handler replaces the previous separate token and session handlers.
    """

    def __init__(self, token_header: str = "X-Auth-Token"):
        """
        Initialize token auth handler.

        Args:
            token_header: Name of the header to use for token (default: X-Auth-Token)
        """
        self.token_header = token_header

    def get_auth_headers(self, credentials: Credentials) -> Dict[str, str]:
        """
        Get token authentication headers.

        Args:
            credentials: Must contain auth token

        Returns:
            Dictionary with token header

        Raises:
            ValueError: If no token is provided
        """
        if not self.validate_credentials(credentials):
            raise ValueError("Authentication token is required for token-based authentication")

        return {self.token_header: credentials.token or ""}

    def validate_credentials(self, credentials: Credentials) -> bool:
        """
        Validate that token is provided.

        Args:
            credentials: Credentials to validate

        Returns:
            True if token is present, False otherwise
        """
        return bool(credentials.token)


class AuthenticationFactory:
    """Factory for creating authentication handlers."""

    @staticmethod
    def create_handler(
        auth_method: str, token_header: str = "X-Auth-Token"
    ) -> AuthenticationHandler:
        """
        Create an authentication handler based on the method.

        Args:
            auth_method: Type of authentication (basic, token)
            token_header: Header name for token-based auth

        Returns:
            Appropriate AuthenticationHandler instance

        Raises:
            ValueError: If auth_method is not supported
        """
        auth_method = auth_method.lower()

        if auth_method == "basic":
            return BasicAuthHandler()
        elif auth_method == "token":
            return TokenAuthHandler(token_header)
        else:
            raise ValueError(
                f"Unsupported authentication method: {auth_method}. "
                f"Supported methods: basic, token"
            )
