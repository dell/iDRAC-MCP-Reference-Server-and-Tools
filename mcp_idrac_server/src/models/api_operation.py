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


"""Data models for API operations parsed from OpenAPI specification."""

from typing import Dict, List, Optional, Any
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


class HttpMethod(str, Enum):
    """HTTP methods supported by the API."""

    GET = "get"
    POST = "post"
    PUT = "put"
    PATCH = "patch"
    DELETE = "delete"
    HEAD = "head"
    OPTIONS = "options"


class ParameterLocation(str, Enum):
    """Location of parameters in the HTTP request."""

    PATH = "path"
    QUERY = "query"
    HEADER = "header"
    COOKIE = "cookie"


class ParameterSchema(BaseModel):
    """Schema for a parameter in the API operation."""

    name: str
    location: ParameterLocation = Field(alias="in")
    description: Optional[str] = None
    required: bool = False
    schema_type: Optional[str] = Field(None, alias="type")
    schema_def: Optional[Dict[str, Any]] = Field(None, alias="schema")
    default: Optional[Any] = None
    enum: Optional[List[Any]] = None

    model_config = ConfigDict(populate_by_name=True)


class RequestBodySchema(BaseModel):
    """Schema for request body."""

    description: Optional[str] = None
    required: bool = False
    content: Dict[str, Any] = {}


class ResponseSchema(BaseModel):
    """Schema for API response."""

    status_code: str
    description: Optional[str] = None
    content: Optional[Dict[str, Any]] = None


class SecurityRequirement(BaseModel):
    """Security requirement for an API operation."""

    scheme_name: str
    scopes: List[str] = []


class ApiOperation(BaseModel):
    """
    Represents a single API operation from the OpenAPI specification.

    This class encapsulates all information needed to make an API call,
    including the HTTP method, path, parameters, request body, and responses.
    """

    operation_id: str
    path: str
    method: HttpMethod
    summary: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = []
    parameters: List[ParameterSchema] = []
    request_body: Optional[RequestBodySchema] = None
    responses: Dict[str, ResponseSchema] = {}
    security: Optional[List[Dict[str, List[str]]]] = None
    deprecated: bool = False

    def get_required_parameters(self) -> List[ParameterSchema]:
        """Get list of required parameters for this operation."""
        return [param for param in self.parameters if param.required]

    def get_optional_parameters(self) -> List[ParameterSchema]:
        """Get list of optional parameters for this operation."""
        return [param for param in self.parameters if not param.required]

    def requires_authentication(self) -> bool:
        """Check if this operation requires authentication."""
        if self.security is None:
            return False
        # Empty security array means no authentication required
        if isinstance(self.security, list) and len(self.security) == 0:
            return False
        return True

    def get_success_responses(self) -> Dict[str, ResponseSchema]:
        """Get successful response schemas (2xx status codes)."""
        return {
            code: response
            for code, response in self.responses.items()
            if code.startswith("2") or code == "200"
        }
