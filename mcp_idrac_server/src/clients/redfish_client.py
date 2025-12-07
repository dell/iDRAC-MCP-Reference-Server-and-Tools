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

"""HTTP client for making Redfish API calls."""

import requests
from typing import Dict, Any, Optional
from urllib.parse import urljoin
import json

from ..auth.authentication import AuthenticationHandler, Credentials
from ..models.api_operation import ApiOperation, HttpMethod


class RedfishAPIError(Exception):
    """Exception raised for Redfish API errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_data: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the exception.

        Args:
            message: Error message
            status_code: HTTP status code
            response_data: Response data from the API
        """
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class RedfishClient:
    """
    HTTP client for making authenticated Redfish API calls.

    This client handles authentication, request construction, and response parsing
    for Redfish API operations.
    """

    def __init__(
        self,
        basic_auth_handler: AuthenticationHandler,
        token_auth_handler: AuthenticationHandler,
        base_url: Optional[str] = None,
        verify_ssl: bool = True,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        """
        Initialize the Redfish client.

        Args:
            basic_auth_handler: Handler for basic authentication (username + password)
            token_auth_handler: Handler for token authentication (auth_token)
            base_url: (DEPRECATED) Base URL is now provided per request via idrac_ip parameter
            verify_ssl: Whether to verify SSL certificates
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        self.base_url = base_url.rstrip("/") if base_url else None
        self.basic_auth_handler = basic_auth_handler
        self.token_auth_handler = token_auth_handler
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()

        # Configure retries
        adapter = requests.adapters.HTTPAdapter(max_retries=max_retries)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def execute_operation(
        self,
        operation: ApiOperation,
        credentials: Credentials,
        base_url: str,
        path_params: Optional[Dict[str, Any]] = None,
        query_params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a Redfish API operation.

        Args:
            operation: The API operation to execute
            credentials: User credentials for authentication
            base_url: Base URL for the iDRAC (e.g., https://idrac_ip) - REQUIRED
            path_params: Path parameters to substitute in URL
            query_params: Query parameters to include in URL
            body: Request body data
            headers: Additional headers to include

        Returns:
            Response data as dictionary

        Raises:
            RedfishAPIError: If the API call fails
        """
        if not base_url:
            raise RedfishAPIError("base_url is required for each request")

        # Build the URL with the provided base_url
        url = self._build_url(operation.path, path_params, base_url.rstrip("/"))

        # Build headers
        request_headers = self._build_headers(credentials, headers)

        # Make the request
        try:
            response = self._make_request(
                method=operation.method.value,
                url=url,
                headers=request_headers,
                params=query_params,
                json_data=body,
            )

            return self._parse_response(response)

        except requests.exceptions.RequestException as e:
            raise RedfishAPIError(f"Request failed: {str(e)}")

    def _build_url(
        self, path: str, path_params: Optional[Dict[str, Any]] = None, base_url: Optional[str] = None
    ) -> str:
        """
        Build the complete URL with path parameters.

        Args:
            path: API path with placeholders (e.g., /redfish/v1/Systems/{SystemId})
            path_params: Dictionary of path parameter values
            base_url: Base URL to use (if not provided, uses self.base_url)

        Returns:
            Complete URL with substituted parameters
        """
        # Substitute path parameters
        if path_params:
            for key, value in path_params.items():
                path = path.replace(f"{{{key}}}", str(value))

        # Use provided base_url or fall back to instance base_url
        target_base_url = base_url if base_url else self.base_url

        # Combine with base URL
        return urljoin(target_base_url, path.lstrip("/"))

    def _build_headers(
        self, credentials: Credentials, additional_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """
        Build request headers including authentication.

        Args:
            credentials: User credentials
            additional_headers: Additional headers to include

        Returns:
            Complete headers dictionary
        """
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Select the appropriate auth handler based on credentials
        # If token is provided, use token auth; otherwise use basic auth
        if credentials.token:
            auth_handler = self.token_auth_handler
        else:
            auth_handler = self.basic_auth_handler

        # Add authentication headers
        auth_headers = auth_handler.get_auth_headers(credentials)
        headers.update(auth_headers)

        # Add any additional headers
        if additional_headers:
            headers.update(additional_headers)

        return headers

    def _make_request(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> requests.Response:
        """
        Make the HTTP request.

        Args:
            method: HTTP method
            url: Complete URL
            headers: Request headers
            params: Query parameters
            json_data: JSON request body

        Returns:
            Response object

        Raises:
            requests.exceptions.RequestException: If request fails
        """
        response = self.session.request(
            method=method.upper(),
            url=url,
            headers=headers,
            params=params,
            json=json_data,
            verify=self.verify_ssl,
            timeout=self.timeout,
        )

        # Check for HTTP errors
        if not response.ok:
            self._handle_error_response(response)

        return response

    def _parse_response(self, response: requests.Response) -> Dict[str, Any]:
        """
        Parse the response data.

        Args:
            response: Response object

        Returns:
            Parsed response data

        Raises:
            RedfishAPIError: If response parsing fails
        """
        # Handle empty responses
        if not response.content:
            return {"status": "success", "status_code": response.status_code}

        # Parse JSON response
        try:
            data = response.json()
            return data
        except json.JSONDecodeError as e:
            # Return raw content if not JSON
            return {
                "status": "success",
                "status_code": response.status_code,
                "content": response.text,
            }

    def _handle_error_response(self, response: requests.Response) -> None:
        """
        Handle error responses from the API.

        Args:
            response: Error response object

        Raises:
            RedfishAPIError: Always raises with error details
        """
        # Try to parse error details
        try:
            error_data = response.json()
            error_message = self._extract_error_message(error_data)
        except (json.JSONDecodeError, KeyError):
            error_message = response.text or f"HTTP {response.status_code}"
            error_data = None

        raise RedfishAPIError(
            message=f"API request failed: {error_message}",
            status_code=response.status_code,
            response_data=error_data,
        )

    def _extract_error_message(self, error_data: Dict[str, Any]) -> str:
        """
        Extract error message from Redfish error response.

        Args:
            error_data: Error response data

        Returns:
            Formatted error message
        """
        # Redfish error format: { "error": { "code": "...", "message": "..." } }
        if "error" in error_data:
            error = error_data["error"]
            message = error.get("message", "Unknown error")
            code = error.get("code", "")
            if code:
                return f"{code}: {message}"
            return message

        # Alternative error formats
        if "Message" in error_data:
            return error_data["Message"]

        return str(error_data)

    def test_connection(self, credentials: Credentials) -> bool:
        """
        Test the connection to the Redfish API.

        Args:
            credentials: User credentials

        Returns:
            True if connection is successful, False otherwise
        """
        try:
            # Try to access the service root
            url = urljoin(self.base_url, "/redfish/v1")
            headers = self._build_headers(credentials)

            response = self.session.get(
                url=url,
                headers=headers,
                verify=self.verify_ssl,
                timeout=self.timeout,
            )

            return response.ok
        except Exception:
            return False

    def close(self) -> None:
        """Close the HTTP session."""
        self.session.close()

    def __enter__(self) -> "RedfishClient":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()
