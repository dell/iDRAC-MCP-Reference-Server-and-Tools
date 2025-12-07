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


"""
Configuration for the Chat UI application.
"""

import os
from typing import Optional

class ChatUIConfig:
    """Configuration class for the Chat UI."""
    
    # Orchestrator connection settings - connects directly to agent orchestrator
    ORCHESTRATOR_URL: str = os.getenv("ORCHESTRATOR_URL", "http://localhost:8001")
    ORCHESTRATOR_TIMEOUT: int = int(os.getenv("ORCHESTRATOR_TIMEOUT", "180"))  # Increased from 30 to 180 seconds

    # Chat endpoints - using orchestrator's API
    CHAT_ENDPOINT: str = "/agent/invoke"
    CHAT_STREAM_ENDPOINT: str = "/agent/stream"
    
    # UI settings
    PAGE_TITLE: str = "Agentic Orchestrator Chat"
    PAGE_ICON: str = "🤖"
    
    # Streaming settings
    STREAMING_ENABLED: bool = os.getenv("STREAMING_ENABLED", "true").lower() == "true"
    STREAM_CHUNK_SIZE: int = int(os.getenv("STREAM_CHUNK_SIZE", "10"))
    STREAM_DELAY: float = float(os.getenv("STREAM_DELAY", "0.1"))
    
    # Chat settings
    MAX_MESSAGES: int = int(os.getenv("MAX_MESSAGES", "100"))
    AUTO_SCROLL: bool = os.getenv("AUTO_SCROLL", "true").lower() == "true"
    
    # Debug settings
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

# Global config instance
config = ChatUIConfig()