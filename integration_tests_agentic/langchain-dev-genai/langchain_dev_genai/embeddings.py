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


"""Dev GenAI embeddings wrapper."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx
from langchain_core.embeddings import Embeddings
from langchain_core.utils import secret_from_env
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

logger = logging.getLogger(__name__)


class DevGenAIEmbeddings(BaseModel, Embeddings):
    """Dev GenAI embeddings model.

    Example:
        .. code-block:: python

            from langchain_dev_genai import DevGenAIEmbeddings

            embeddings = DevGenAIEmbeddings(
                api_key="your-api-key", model="dev-genai-embed"
            )

            # Embed documents
            doc_embeddings = embeddings.embed_documents(["Hello world", "How are you?"])

            # Embed query
            query_embedding = embeddings.embed_query("What's up?")
    """

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    # Core configuration
    api_key: Optional[SecretStr] = Field(
        default=None,
        description="API key for Dev GenAI. If not provided, will attempt to read from environment variable DEV_GENAI_API_KEY.",
    )
    base_url: str = Field(
        default="https://genai-api-dev.dell.com/v1",
        description="Base URL for the Dev GenAI API.",
    )
    model: str = Field(
        default="bge-m3", description="Default model name to use for embeddings."
    )

    # Client configuration
    timeout: float = Field(default=60.0, ge=0)
    max_retries: int = Field(default=3, ge=0)

    # Embedding parameters
    dimensions: Optional[int] = Field(
        default=None,
        description="Number of dimensions for the embeddings. If not provided, uses model default.",
    )

    _client: Optional[httpx.Client] = None
    _async_client: Optional[httpx.AsyncClient] = None

    @model_validator(mode="before")
    @classmethod
    def validate_environment(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """Validate that api key is provided."""
        if values.get("api_key") is None:
            values["api_key"] = secret_from_env(
                "DEV_GENAI_API_KEY")
        return values

    @property
    def client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.Client(
                verify=False,
                base_url=self.base_url,
                timeout=self.timeout,
                headers={
                    "Authorization": f"Bearer {self.api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    @property
    def async_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(
                verify=False,
                base_url=self.base_url,
                timeout=self.timeout,
                headers={
                    "Authorization": f"Bearer {self.api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                },
            )
        return self._async_client

    def _get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for a list of texts."""
        # Prepare request payload
        payload = {"model": self.model, "input": texts}

        if self.dimensions:
            payload["dimensions"] = self.dimensions

        # Make API request
        response = self.client.post("/embeddings", json=payload)
        response.raise_for_status()

        response_data = response.json()

        # Extract embeddings
        embeddings = []
        for embedding_data in response_data["data"]:
            embeddings.append(embedding_data["embedding"])

        return embeddings

    async def _aget_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Async get embeddings for a list of texts."""
        # Prepare request payload
        payload = {"model": self.model, "input": texts}

        if self.dimensions:
            payload["dimensions"] = self.dimensions

        # Make API request
        response = await self.async_client.post("/embeddings", json=payload)
        response.raise_for_status()

        response_data = response.json()

        # Extract embeddings
        embeddings = []
        for embedding_data in response_data["data"]:
            embeddings.append(embedding_data["embedding"])

        return embeddings

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of documents.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embeddings, one for each text.
        """
        return self._get_embeddings(texts)

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        """Async embed a list of documents.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embeddings, one for each text.
        """
        return await self._aget_embeddings(texts)

    def embed_query(self, text: str) -> List[float]:
        """Embed a query text.

        Args:
            text: Text to embed.

        Returns:
            Embedding for the text.
        """
        embeddings = self._get_embeddings([text])
        return embeddings[0]

    async def aembed_query(self, text: str) -> List[float]:
        """Async embed a query text.

        Args:
            text: Text to embed.

        Returns:
            Embedding for the text.
        """
        embeddings = await self._aget_embeddings([text])
        return embeddings[0]
