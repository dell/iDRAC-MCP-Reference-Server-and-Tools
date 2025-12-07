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


"""Dev GenAI chat model wrapper."""

from __future__ import annotations

import json
import logging
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
    Type,
    Union,
)

import httpx
from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models.chat_models import (
    BaseChatModel,
    generate_from_stream,
    agenerate_from_stream,
)
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    BaseMessageChunk,
    ChatMessage,
    FunctionMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.messages.ai import UsageMetadata
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_core.utils import (
    build_extra_kwargs,
    get_pydantic_field_names,
    secret_from_env,
)
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import ConfigDict, Field, SecretStr, model_validator

logger = logging.getLogger(__name__)


def _convert_message_to_dev_genai_format(message: BaseMessage) -> Dict[str, Any]:
    """Convert LangChain message to Dev GenAI API format."""
    if isinstance(message, HumanMessage):
        return {"role": "user", "content": message.content}
    elif isinstance(message, AIMessage):
        content = {"role": "assistant", "content": message.content}
        if message.tool_calls:
            content["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["args"]),
                    },
                }
                for tc in message.tool_calls
            ]
        return content
    elif isinstance(message, SystemMessage):
        return {"role": "system", "content": message.content}
    elif isinstance(message, ToolMessage):
        return {
            "role": "tool",
            "content": message.content,
            "tool_call_id": message.tool_call_id,
        }
    elif isinstance(message, FunctionMessage):
        return {"role": "function", "content": message.content, "name": message.name}
    elif isinstance(message, ChatMessage):
        return {"role": message.role, "content": message.content}
    else:
        raise ValueError(f"Unsupported message type: {type(message)}")


def _convert_chunk_to_message_chunk(
    chunk: Dict[str, Any], default_chunk_class: Type[BaseMessageChunk]
) -> BaseMessageChunk:
    """Convert API response chunk to LangChain message chunk."""
    delta = chunk.get("delta", {})
    role = delta.get("role")
    content = delta.get("content", "")

    if role == "assistant":
        return AIMessageChunk(content=content)
    elif role == "user":
        return default_chunk_class(content=content)
    elif role == "system":
        return default_chunk_class(content=content)
    else:
        return default_chunk_class(content=content)


class ChatDevGenAI(BaseChatModel):
    """Chat model for Dev GenAI API.

    Example:
        .. code-block:: python

            from langchain_dev_genai import ChatDevGenAI

            model = ChatDevGenAI(
                api_key="your-api-key", model="dev-genai-model", temperature=0.7
            )

            # Use the model
            response = model.invoke("Tell me a joke")
    """

    model_config = ConfigDict(
        extra="forbid", protected_namespaces=(), arbitrary_types_allowed=True
    )

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
        default="llama-3-3-70b-instruct", description="Available default model"
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
            values["api_key"] = secret_from_env("DEV_GENAI_API_KEY")
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

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Generate chat completion."""
        if self.streaming:
            return generate_from_stream(
                self._stream(messages, stop=stop, run_manager=run_manager, **kwargs)
            )

        # Convert messages to API format
        formatted_messages = [
            _convert_message_to_dev_genai_format(msg) for msg in messages
        ]

        # Prepare request payload
        payload = {
            "model": self.model,
            "messages": formatted_messages,
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
        response = self.client.post("/chat/completions", json=payload)
        response.raise_for_status()

        response_data = response.json()

        # Extract the message
        choice = response_data["choices"][0]
        message_data = choice["message"]

        # Extract content (handle None for Pydantic V2 compatibility)
        content = message_data.get("content") or ""

        # Extract tool_calls if present (standard OpenAI format)
        tool_calls = []
        if "tool_calls" in message_data and message_data["tool_calls"]:
            for tool_call in message_data["tool_calls"]:
                try:
                    func = tool_call.get("function", {})
                    args_str = func.get("arguments", "{}")
                    # Parse arguments if they're a JSON string
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str

                    tool_calls.append({
                        "name": func.get("name"),
                        "args": args,
                        "id": tool_call.get("id"),
                        "type": "tool_call"
                    })
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    logger.warning(f"Failed to parse tool call: {e}")

        # Create AI message with content and tool_calls
        ai_message = AIMessage(
            content=content,
            tool_calls=tool_calls if tool_calls else []
        )

        # Add usage metadata if available
        usage = response_data.get("usage", {})
        if usage:
            ai_message.usage_metadata = UsageMetadata(
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            )

        generation = ChatGeneration(message=ai_message)
        return ChatResult(generations=[generation])

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Async generate chat completion."""
        if self.streaming:
            return await agenerate_from_stream(
                self._astream(messages, stop=stop, run_manager=run_manager, **kwargs)
            )

        # Convert messages to API format
        formatted_messages = [
            _convert_message_to_dev_genai_format(msg) for msg in messages
        ]

        # Prepare request payload
        payload = {
            "model": self.model,
            "messages": formatted_messages,
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
        response = await self.async_client.post("/chat/completions", json=payload)
        response.raise_for_status()

        response_data = response.json()

        # Extract the message
        choice = response_data["choices"][0]
        message_data = choice["message"]

        # Extract content (handle None for Pydantic V2 compatibility)
        content = message_data.get("content") or ""

        # Extract tool_calls if present (standard OpenAI format)
        tool_calls = []
        if "tool_calls" in message_data and message_data["tool_calls"]:
            for tool_call in message_data["tool_calls"]:
                try:
                    func = tool_call.get("function", {})
                    args_str = func.get("arguments", "{}")
                    # Parse arguments if they're a JSON string
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str

                    tool_calls.append({
                        "name": func.get("name"),
                        "args": args,
                        "id": tool_call.get("id"),
                        "type": "tool_call"
                    })
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    logger.warning(f"Failed to parse tool call: {e}")

        # Create AI message with content and tool_calls
        ai_message = AIMessage(
            content=content,
            tool_calls=tool_calls if tool_calls else []
        )

        # Add usage metadata if available
        usage = response_data.get("usage", {})
        if usage:
            ai_message.usage_metadata = UsageMetadata(
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            )

        generation = ChatGeneration(message=ai_message)
        return ChatResult(generations=[generation])

    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """Stream chat completion."""
        # Convert messages to API format
        formatted_messages = [
            _convert_message_to_dev_genai_format(msg) for msg in messages
        ]

        # Prepare request payload
        payload = {
            "model": self.model,
            "messages": formatted_messages,
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
        with self.client.stream("POST", "/chat/completions", json=payload) as response:
            response.raise_for_status()

            for line in response.iter_lines():
                if line.startswith("data: "):
                    data = line[6:]  # Remove "data: " prefix
                    if data == "[DONE]":
                        break

                    try:
                        chunk_data = json.loads(data)
                        choice = chunk_data["choices"][0]

                        # Convert to message chunk
                        chunk = _convert_chunk_to_message_chunk(choice, AIMessageChunk)

                        # Create generation chunk
                        generation_chunk = ChatGenerationChunk(message=chunk)

                        if run_manager:
                            run_manager.on_llm_new_token(chunk.content)

                        yield generation_chunk

                    except json.JSONDecodeError:
                        continue

    async def _astream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        """Async stream chat completion."""
        # Convert messages to API format
        formatted_messages = [
            _convert_message_to_dev_genai_format(msg) for msg in messages
        ]

        # Prepare request payload
        payload = {
            "model": self.model,
            "messages": formatted_messages,
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
            "POST", "/chat/completions", json=payload
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

                        # Convert to message chunk
                        chunk = _convert_chunk_to_message_chunk(choice, AIMessageChunk)

                        # Create generation chunk
                        generation_chunk = ChatGenerationChunk(message=chunk)

                        if run_manager:
                            await run_manager.on_llm_new_token(chunk.content)

                        yield generation_chunk

                    except json.JSONDecodeError:
                        continue

    @property
    def _llm_type(self) -> str:
        """Return type of LLM."""
        return "dev-genai-chat"

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

    def bind_tools(
        self,
        tools: List[Union[Dict[str, Any], Type, Callable, BaseTool]],
        **kwargs: Any,
    ) -> Runnable[Dict[str, Any], str]:
        """Bind tools to the model."""
        # Convert tools to OpenAI format (Dev GenAI uses similar format)
        formatted_tools = []
        for tool in tools:
            if isinstance(tool, BaseTool):
                formatted_tools.append(convert_to_openai_tool(tool))
            elif isinstance(tool, type):
                formatted_tools.append(convert_to_openai_tool(tool))
            elif callable(tool):
                formatted_tools.append(convert_to_openai_tool(tool))
            else:
                formatted_tools.append(tool)

        return self.bind(tools=formatted_tools, **kwargs)

    def with_structured_output(
        self, schema: Union[Dict[str, Any], Type], **kwargs: Any
    ) -> Runnable[Dict[str, Any], Any]:
        """Enable structured output for the model."""
        # This would be implemented based on Dev GenAI's structured output capabilities
        # For now, return the model itself
        return self.bind(**kwargs)
