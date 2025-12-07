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



"""Dev GenAI LLM wrapper."""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional

import httpx
from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models.llms import LLM
from langchain_core.outputs import GenerationChunk, LLMResult
from langchain_core.utils import secret_from_env
from pydantic import ConfigDict, Field, SecretStr, model_validator

logger = logging.getLogger(__name__)


class DevGenAI(LLM):
    """Dev GenAI LLM model.

    Example:
        .. code-block:: python

            from langchain_dev_genai import DevGenAI

            llm = DevGenAI(
                api_key="your-api-key", model="dev-genai-text", temperature=0.7
            )

            # Use the LLM
            response = llm.invoke("Tell me a story")
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
        default="llama-3-3-70b-instruct", description="Model name to use."
    )

    # Model parameters
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    frequency_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    presence_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)

    # Client configuration
    timeout: float = Field(default=60.0, ge=0)
    max_retries: int = Field(default=3, ge=0)

    # Advanced features
    streaming: bool = Field(default=False)

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

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        """Call the Dev GenAI API."""
        # Prepare request payload
        payload = {
            "model": self.model,
            "prompt": prompt,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
            "stream": False,
        }

        if stop:
            payload["stop"] = stop

        # Add any additional kwargs
        payload.update(kwargs)

        # Make API request
        response = self.client.post("/completions", json=payload)
        response.raise_for_status()

        response_data = response.json()

        # Extract the text
        choice = response_data["choices"][0]
        text = choice["text"]

        return text

    async def _acall(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        """Async call the Dev GenAI API."""
        # Prepare request payload
        payload = {
            "model": self.model,
            "prompt": prompt,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
            "stream": False,
        }

        if stop:
            payload["stop"] = stop

        # Add any additional kwargs
        payload.update(kwargs)

        # Make API request
        response = await self.async_client.post("/completions", json=payload)
        response.raise_for_status()

        response_data = response.json()

        # Extract the text
        choice = response_data["choices"][0]
        text = choice["text"]

        return text

    def _stream(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[GenerationChunk]:
        """Stream the Dev GenAI API."""
        # Prepare request payload
        payload = {
            "model": self.model,
            "prompt": prompt,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
            "stream": True,
        }

        if stop:
            payload["stop"] = stop

        # Add any additional kwargs
        payload.update(kwargs)

        # Stream the response
        with self.client.stream("POST", "/completions", json=payload) as response:
            response.raise_for_status()

            for line in response.iter_lines():
                if line.startswith("data: "):
                    data = line[6:]  # Remove "data: " prefix
                    if data == "[DONE]":
                        break

                    try:
                        chunk_data = json.loads(data)
                        choice = chunk_data["choices"][0]
                        text = choice.get("text", "")

                        # Create generation chunk
                        chunk = GenerationChunk(text=text)

                        if run_manager:
                            run_manager.on_llm_new_token(text)

                        yield chunk

                    except json.JSONDecodeError:
                        continue

    async def _astream(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> AsyncIterator[GenerationChunk]:
        """Async stream the Dev GenAI API."""
        # Prepare request payload
        payload = {
            "model": self.model,
            "prompt": prompt,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
            "stream": True,
        }

        if stop:
            payload["stop"] = stop

        # Add any additional kwargs
        payload.update(kwargs)

        # Stream the response
        async with self.async_client.stream(
            "POST", "/completions", json=payload
        ) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]  # Remove "data: " prefix
                    if data == "[DONE]":
                        break

                    try:
                        chunk_data = json.loads(data)
                        choice = chunk_data["choices"][0]
                        text = choice.get("text", "")

                        # Create generation chunk
                        chunk = GenerationChunk(text=text)

                        if run_manager:
                            await run_manager.on_llm_new_token(text)

                        yield chunk

                    except json.JSONDecodeError:
                        continue

    @property
    def _llm_type(self) -> str:
        """Return type of LLM."""
        return "dev-genai"

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        """Get the identifying parameters."""
        return {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
        }
