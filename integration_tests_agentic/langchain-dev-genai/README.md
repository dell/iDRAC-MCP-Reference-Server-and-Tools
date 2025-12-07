# langchain-dev-genai

This package contains the LangChain integration for Dev GenAI.

## Installation

```bash
cd langchain-dev-genai
uv pip install .
```

## Usage

### Chat Models

```python
from langchain_dev_genai import ChatDevGenAI

chat = ChatDevGenAI(
    api_key="your-api-key",
    model="dev-genai-chat",
    temperature=0.7,
)

response = chat.invoke("Tell me a joke")
print(response.content)
```

### LLMs

```python
from langchain_dev_genai import DevGenAI

llm = DevGenAI(
    api_key="your-api-key",
    model="dev-genai-text",
    temperature=0.7,
)

response = llm.invoke("Complete this story: Once upon a time...")
print(response)
```

### Embeddings

```python
from langchain_dev_genai import DevGenAIEmbeddings

embeddings = DevGenAIEmbeddings(
    api_key="your-api-key",
    model="dev-genai-embed",
)

# Embed documents
doc_embeddings = embeddings.embed_documents([
    "Hello world",
    "How are you?"
])

# Embed query
query_embedding = embeddings.embed_query("What's up?")
```

## Configuration

### Environment Variables

You can set your API key using environment variables:

```bash
export DEV_GENAI_API_KEY="your-api-key"
```

### Parameters

All models support the following common parameters:

- `api_key`: Your Dev GenAI API key
- `base_url`: Base URL for the API (default: "https://api.dev-genai.com/v1")
- `timeout`: Request timeout in seconds (default: 60.0)
- `max_retries`: Maximum number of retries (default: 3)

#### Chat Models and LLMs

- `model`: Model name to use
- `temperature`: Sampling temperature (0.0 to 2.0)
- `max_tokens`: Maximum tokens to generate
- `top_p`: Nucleus sampling parameter
- `frequency_penalty`: Frequency penalty (-2.0 to 2.0)
- `presence_penalty`: Presence penalty (-2.0 to 2.0)
- `streaming`: Enable streaming responses

#### Embeddings

- `model`: Embedding model name to use
- `dimensions`: Number of dimensions for embeddings (optional)

## Features

### Streaming

Both chat models and LLMs support streaming:

```python
from langchain_dev_genai import ChatDevGenAI

chat = ChatDevGenAI(api_key="your-api-key", streaming=True)

for chunk in chat.stream("Tell me a long story"):
    print(chunk.content, end="", flush=True)
```

### Async Support

All models support async operations:

```python
import asyncio
from langchain_dev_genai import ChatDevGenAI

async def main():
    chat = ChatDevGenAI(api_key="your-api-key")
    response = await chat.ainvoke("Hello!")
    print(response.content)

asyncio.run(main())
```

### Tool Calling

Chat models support tool calling:

```python
from langchain_core.tools import tool
from langchain_dev_genai import ChatDevGenAI

@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return f"The weather in {city} is sunny."

chat = ChatDevGenAI(api_key="your-api-key")
chat_with_tools = chat.bind_tools([get_weather])

response = chat_with_tools.invoke("What's the weather in San Francisco?")
```

## Development

### Running Tests

To be updated

### Contributing

Please see the main LangChain contributing guide for information on how to contribute to this package.
