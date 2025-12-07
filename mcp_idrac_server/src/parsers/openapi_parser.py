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


"""Parser for OpenAPI specification files."""

import yaml
from typing import Dict, List, Optional, Any
from pathlib import Path

from ..models.api_operation import (
    ApiOperation,
    HttpMethod,
    ParameterSchema,
    ParameterLocation,
    RequestBodySchema,
    ResponseSchema,
)


class OpenApiParser:
    """
    Parser for OpenAPI 3.0 specification files.

    This class reads and parses OpenAPI YAML files, extracting API operations
    and their metadata for use in tool generation.
    """

    def __init__(self, openapi_file_path: str):
        """
        Initialize the OpenAPI parser.

        Args:
            openapi_file_path: Path to the OpenAPI YAML file
        """
        self.file_path = Path(openapi_file_path)
        self.spec: Dict[str, Any] = {}
        self.operations: Dict[str, ApiOperation] = {}
        self._load_spec()

    def _load_spec(self) -> None:
        """Load and parse the OpenAPI specification file."""
        if not self.file_path.exists():
            raise FileNotFoundError(f"OpenAPI file not found: {self.file_path}")

        with open(self.file_path, "r", encoding="utf-8") as f:
            self.spec = yaml.safe_load(f)

        if not self.spec:
            raise ValueError(f"Empty or invalid OpenAPI file: {self.file_path}")

        self._validate_spec()
        self._parse_operations()

    def _validate_spec(self) -> None:
        """Validate that the loaded specification is a valid OpenAPI document."""
        if "openapi" not in self.spec:
            raise ValueError("Invalid OpenAPI specification: missing 'openapi' field")

        version = self.spec["openapi"]
        if not version.startswith("3.0"):
            raise ValueError(f"Unsupported OpenAPI version: {version}. Only 3.0.x is supported.")

        if "paths" not in self.spec:
            raise ValueError("Invalid OpenAPI specification: missing 'paths' field")

    def _parse_operations(self) -> None:
        """Parse all API operations from the paths section."""
        paths = self.spec.get("paths", {})

        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue

            # Parse each HTTP method for this path
            for method in ["get", "post", "put", "patch", "delete", "head", "options"]:
                if method in path_item:
                    operation = self._parse_operation(path, method, path_item[method])
                    if operation and operation.operation_id:
                        self.operations[operation.operation_id] = operation

    def _parse_operation(
        self, path: str, method: str, operation_spec: Dict[str, Any]
    ) -> Optional[ApiOperation]:
        """
        Parse a single API operation.

        Args:
            path: The API path
            method: The HTTP method
            operation_spec: The operation specification from OpenAPI

        Returns:
            ApiOperation object or None if parsing fails
        """
        try:
            operation_id = operation_spec.get("operationId")
            if not operation_id:
                # Generate operation ID if not provided
                operation_id = f"{method}_{path.replace('/', '_').replace('{', '').replace('}', '')}"

            # Parse parameters
            parameters = self._parse_parameters(operation_spec.get("parameters", []))

            # Parse request body
            request_body = self._parse_request_body(operation_spec.get("requestBody"))

            # Parse responses
            responses = self._parse_responses(operation_spec.get("responses", {}))

            # Parse tags - handle both list and string formats
            tags = operation_spec.get("tags", [])
            if isinstance(tags, str):
                tags = [tags]
            elif not isinstance(tags, list):
                tags = []

            return ApiOperation(
                operation_id=operation_id,
                path=path,
                method=HttpMethod(method),
                summary=operation_spec.get("summary"),
                description=operation_spec.get("description"),
                tags=tags,
                parameters=parameters,
                request_body=request_body,
                responses=responses,
                security=operation_spec.get("security"),
                deprecated=operation_spec.get("deprecated", False),
            )
        except Exception as e:
            print(f"Warning: Failed to parse operation {method.upper()} {path}: {e}")
            return None

    def _parse_parameters(
        self, params_spec: List[Dict[str, Any]]
    ) -> List[ParameterSchema]:
        """Parse parameter specifications."""
        parameters = []

        for param_spec in params_spec:
            try:
                # Handle parameter references
                if "$ref" in param_spec:
                    param_spec = self._resolve_reference(param_spec["$ref"])

                param = ParameterSchema(
                    name=param_spec.get("name", ""),
                    **{"in": param_spec.get("in", "query")},
                    description=param_spec.get("description"),
                    required=param_spec.get("required", False),
                    schema=param_spec.get("schema"),
                )
                parameters.append(param)
            except Exception as e:
                print(f"Warning: Failed to parse parameter: {e}")
                continue

        return parameters

    def _parse_request_body(
        self, body_spec: Optional[Dict[str, Any]]
    ) -> Optional[RequestBodySchema]:
        """Parse request body specification."""
        if not body_spec:
            return None

        try:
            # Handle request body references
            if "$ref" in body_spec:
                body_spec = self._resolve_reference(body_spec["$ref"])

            return RequestBodySchema(
                description=body_spec.get("description"),
                required=body_spec.get("required", False),
                content=body_spec.get("content", {}),
            )
        except Exception as e:
            print(f"Warning: Failed to parse request body: {e}")
            return None

    def _parse_responses(
        self, responses_spec: Dict[str, Any]
    ) -> Dict[str, ResponseSchema]:
        """Parse response specifications."""
        responses = {}

        for status_code, response_spec in responses_spec.items():
            try:
                # Handle response references
                if "$ref" in response_spec:
                    response_spec = self._resolve_reference(response_spec["$ref"])

                responses[status_code] = ResponseSchema(
                    status_code=status_code,
                    description=response_spec.get("description"),
                    content=response_spec.get("content"),
                )
            except Exception as e:
                print(f"Warning: Failed to parse response {status_code}: {e}")
                continue

        return responses

    def _resolve_reference(self, ref: str) -> Dict[str, Any]:
        """
        Resolve a JSON reference in the OpenAPI spec.

        Args:
            ref: Reference string (e.g., '#/components/schemas/Pet')

        Returns:
            The resolved object from the spec
        """
        # This is a simplified reference resolver
        # In production, you might want to use a library like jsonschema
        if not ref.startswith("#/"):
            # External references not supported in this basic implementation
            return {}

        parts = ref[2:].split("/")
        obj = self.spec

        for part in parts:
            if isinstance(obj, dict) and part in obj:
                obj = obj[part]
            else:
                return {}

        return obj if isinstance(obj, dict) else {}

    def get_operation(self, operation_id: str) -> Optional[ApiOperation]:
        """
        Get an API operation by its operation ID.

        Args:
            operation_id: The operation ID to look up

        Returns:
            ApiOperation object or None if not found
        """
        return self.operations.get(operation_id)

    def get_operations_by_tag(self, tag: str) -> List[ApiOperation]:
        """
        Get all operations with a specific tag.

        Args:
            tag: The tag to filter by

        Returns:
            List of ApiOperation objects
        """
        return [op for op in self.operations.values() if tag in op.tags]

    def list_operation_ids(self) -> List[str]:
        """
        Get a list of all operation IDs in the specification.

        Returns:
            List of operation ID strings
        """
        return list(self.operations.keys())

    def get_info(self) -> Dict[str, Any]:
        """
        Get the info section of the OpenAPI specification.

        Returns:
            Dictionary containing API metadata
        """
        return self.spec.get("info", {})

    def get_security_schemes(self) -> Dict[str, Any]:
        """
        Get the security schemes defined in the specification.

        Returns:
            Dictionary of security scheme definitions
        """
        return self.spec.get("components", {}).get("securitySchemes", {})
