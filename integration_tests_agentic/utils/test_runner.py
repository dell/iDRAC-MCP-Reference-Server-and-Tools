# Licensed to You under the Apache License, Version 2.0

"""
Test Runner Utilities

Provides utilities for running agentic tests with different LLM providers
and configurations.
"""

import os
import yaml
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
import json

# In latest LangChain, agents are created using langgraph
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage

from langchain_core.prompts import PromptTemplate
from langchain_core.tools import BaseTool

from .llm_logger import LLMLoggingCallback


class PromptsConfig:
    """Loads and manages prompt templates from configuration."""

    def __init__(self, config_path: str = "config/prompts_config.yaml"):
        """
        Initialize prompts configuration.

        Args:
            config_path: Path to prompts configuration YAML file
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load prompts configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Prompts config not found: {self.config_path}")

        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def get_profile(self, profile_name: str) -> Dict[str, Any]:
        """
        Get MCP server profile configuration.

        Args:
            profile_name: Name of the profile (e.g., 'idrac', 'generic')

        Returns:
            Profile configuration dictionary
        """
        profiles = self.config.get('profiles', {})
        if profile_name not in profiles:
            raise ValueError(
                f"Profile '{profile_name}' not found. "
                f"Available profiles: {list(profiles.keys())}"
            )
        return profiles[profile_name]

    def get_react_prompt_template(self, profile_name: str) -> PromptTemplate:
        """
        Get ReAct prompt template formatted for the specified profile.

        Args:
            profile_name: Name of the MCP server profile

        Returns:
            PromptTemplate configured for the profile
        """
        profile = self.get_profile(profile_name)
        template = self.config.get('react_prompt_template', '')

        # Replace profile-specific variables
        formatted_template = template.format(
            agent_role=profile['agent_role'],
            server_context=profile['server_context'],
            management_interface=profile['management_interface']
        )

        return PromptTemplate.from_template(formatted_template)

    def get_error_message(self, key: str, **kwargs) -> str:
        """Get formatted error message."""
        messages = self.config.get('error_messages', {})
        template = messages.get(key, "An error occurred")
        return template.format(**kwargs)

    def get_success_message(self, key: str, **kwargs) -> str:
        """Get formatted success message."""
        messages = self.config.get('success_messages', {})
        template = messages.get(key, "Operation successful")
        return template.format(**kwargs)


class LLMFactory:
    """Factory for creating LLM instances based on configuration."""

    @staticmethod
    def create_llm(config: Dict[str, Any]):
        """
        Create LLM instance based on provider configuration.

        Args:
            config: LLM configuration dictionary

        Returns:
            LLM instance

        Raises:
            ValueError: If provider is not supported or not configured
        """
        provider = config.get('provider', 'ollama')

        if provider == 'ollama':
            from langchain_community.llms import Ollama
            return Ollama(
                model=config['ollama']['model'],
                base_url=config['ollama'].get('base_url', 'http://localhost:11434'),
                temperature=config['ollama']['temperature'],
            )

        elif provider == 'dev_genai':
            # Import from existing orchestrator if available
            try:
                import sys
                sys.path.insert(0, '/home/cm/Desktop/agentic_projects/poweredge-agentic-ai/langchain-dev-genai')
                from langchain_dev_genai import ChatDevGenAI

                # Get base URL and key from config or environment
                base_url = config['dev_genai'].get('base_url') or os.getenv('DEV_GENAI_API_URL')
                api_key = config['dev_genai'].get('api_key') or os.getenv('DEV_GENAI_API_KEY')

                if not base_url:
                    raise ValueError(
                        "dev_genai base URL not configured. Set DEV_GENAI_API_URL environment variable "
                        "or add 'base_url' to config['dev_genai']"
                    )

                if not api_key:
                    raise ValueError(
                        "dev_genai API key not configured. Set DEV_GENAI_API_KEY environment variable "
                        "or add 'api_key' to config['dev_genai']"
                    )

                return ChatDevGenAI(
                    model=config['dev_genai']['model'],
                    base_url=base_url,
                    api_key=api_key,
                    temperature=config['dev_genai']['temperature'],
                    max_tokens=config['dev_genai'].get('max_tokens'),
                )
            except ImportError as e:
                raise ValueError(
                    "dev_genai provider requires langchain-dev-genai package. "
                    "Install from: /home/cm/Desktop/agentic_projects/poweredge-agentic-ai/langchain-dev-genai\n"
                    f"Error: {e}"
                )

        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")


class AgentRunner:
    """Runs agents with monitoring and error handling."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize agent runner.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.llm = LLMFactory.create_llm(config['llm'])
        self.traces = []

        # Load prompts configuration
        prompts_config_path = Path(__file__).parent.parent / "config" / "prompts_config.yaml"
        self.prompts_config = PromptsConfig(str(prompts_config_path))

        # Get MCP profile from config
        mcp_profile = config.get('mcp_profile', 'generic')

        # Load ReAct prompt template for the profile
        self.REACT_PROMPT = self.prompts_config.get_react_prompt_template(mcp_profile)

        # Create LLM logging callback
        # Use verbose logging if enabled in config
        llm_verbose_logging = config.get('monitoring', {}).get('log_llm_requests', True)
        self.llm_callback = LLMLoggingCallback(verbose=llm_verbose_logging)

    def create_agent(self, tools: List[BaseTool], **kwargs):
        """
        Create a ReAct agent with the given tools using LangGraph.

        Args:
            tools: List of LangChain tools
            **kwargs: Additional arguments (ignored in langgraph)

        Returns:
            Compiled LangGraph agent
        """
        agent_config = self.config.get('agent', {})

        # Create agent with langgraph (basic configuration)
        agent = create_react_agent(
            model=self.llm,
            tools=tools
        )

        # Store config and system message for use in run_test
        from langchain_core.messages import SystemMessage

        agent.config = {
            'max_iterations': agent_config.get('max_iterations', 10),
            'max_execution_time': agent_config.get('max_execution_time', 90),
            'verbose': self.config['test_execution'].get('verbose', False),
            'callbacks': [self.llm_callback]
        }

        # Create system message from the loaded REACT_PROMPT template
        # Note: LangGraph's create_react_agent handles the ReAct format internally,
        # so we extract just the role and key instructions for the system message
        mcp_profile = self.config.get('mcp_profile', 'generic')
        profile = self.prompts_config.get_profile(mcp_profile)

        # Build system message with profile-specific context
        system_message_content = f"""You are an {profile['agent_role']}.

IMPORTANT INSTRUCTIONS:
1. WHEN ASKED ABOUT CAPABILITIES: Answer directly from the tool list without calling any tools
2. WHEN EXECUTING TASKS: Execute the requested tool and use rag_search for documentation when helpful
3. INTERACTIVE ACTION CONFIRMATION: For destructive actions (reset, delete, modify), ALWAYS ask for confirmation first
4. RESPONSE STRUCTURE: Provide clear, comprehensive answers with current status and documentation notes
5. MULTI-SYSTEM SUPPORT: Check tool descriptions for multi-system capabilities. If a tool supports it and user doesn't specify a system, execute for all systems.

You are managing {profile['server_context']} via {profile['management_interface']}."""

        agent.system_message = SystemMessage(content=system_message_content)

        return agent

    def run_test(
        self,
        agent,  # LangGraph agent (compiled graph)
        input_text: str,
        expected_tools: Optional[List[str]] = None,
        expected_in_output: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Run a single test with the agent.

        Args:
            agent: LangGraph agent (compiled graph)
            input_text: Input question/prompt for the agent
            expected_tools: List of tool names expected to be called
            expected_in_output: List of strings expected in final output

        Returns:
            Test result dictionary
        """
        start_time = datetime.now()

        try:
            # Run agent with langgraph API (takes messages)
            # Prepend system message if available
            messages = []
            if hasattr(agent, 'system_message'):
                messages.append(agent.system_message)
            messages.append(HumanMessage(content=input_text))

            result = agent.invoke(
                {"messages": messages},
                config={"callbacks": agent.config.get('callbacks', [])}
            )

            # Extract messages from result
            messages = result.get('messages', [])

            # Get final output (last AI message)
            output = ""
            for msg in reversed(messages):
                if hasattr(msg, 'content') and msg.content:
                    output = msg.content
                    break

            # Analyze tool usage from messages
            tools_called = []
            for msg in messages:
                # Check for tool calls in messages
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    for tool_call in msg.tool_calls:
                        if isinstance(tool_call, dict):
                            tools_called.append(tool_call.get('name', 'unknown'))
                        elif hasattr(tool_call, 'name'):
                            tools_called.append(tool_call.name)

            # Count iterations (number of messages / 2, roughly)
            num_iterations = len([m for m in messages if hasattr(m, 'tool_calls')])
            intermediate_steps = messages  # Store all messages for debugging

            # Check expectations
            success = True
            errors = []

            if expected_tools:
                for expected_tool in expected_tools:
                    if expected_tool not in tools_called:
                        success = False
                        errors.append(f"Expected tool '{expected_tool}' was not called")

            if expected_in_output:
                for expected_str in expected_in_output:
                    if expected_str not in output:
                        success = False
                        errors.append(f"Expected '{expected_str}' not found in output")

            # Build result
            test_result = {
                'success': success,
                'output': output,
                'tools_called': tools_called,
                'num_iterations': num_iterations,
                'execution_time': (datetime.now() - start_time).total_seconds(),
                'errors': errors,
                'intermediate_steps': [str(msg) for msg in messages]
            }

            # Save trace if configured
            if self.config['test_execution'].get('save_traces'):
                self._save_trace(input_text, test_result)

            return test_result

        except Exception as e:
            return {
                'success': False,
                'output': '',
                'tools_called': [],
                'num_iterations': 0,
                'execution_time': (datetime.now() - start_time).total_seconds(),
                'errors': [str(e)],
                'intermediate_steps': []
            }

    def _save_trace(self, input_text: str, result: Dict[str, Any]):
        """Save execution trace for debugging."""
        trace_dir = Path(self.config['test_execution'].get('trace_dir', './traces'))
        trace_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        trace_file = trace_dir / f"trace_{timestamp}.json"

        trace_data = {
            'timestamp': timestamp,
            'input': input_text,
            'result': result
        }

        with open(trace_file, 'w') as f:
            json.dump(trace_data, f, indent=2)


def load_test_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load test configuration from YAML file.

    Args:
        config_path: Path to config file (defaults to config/test_config.yaml)

    Returns:
        Configuration dictionary
    """
    if config_path is None:
        config_path = Path(__file__).parent.parent / 'config' / 'test_config.yaml'

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    return config
