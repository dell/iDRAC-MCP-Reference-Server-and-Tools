#!/usr/bin/env python3
# Licensed to You under the Apache License, Version 2.0

"""
LLM Logging Callback Handler

Logs all LLM inputs and outputs for debugging and monitoring.
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

logger = logging.getLogger(__name__)


class LLMLoggingCallback(BaseCallbackHandler):
    """Callback handler that logs all LLM interactions."""

    def __init__(self, verbose: bool = True):
        """
        Initialize LLM logging callback.

        Args:
            verbose: If True, log full prompts and responses. If False, log summaries only.
        """
        self.verbose = verbose
        self.call_count = 0
        self.total_tokens = 0

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        **kwargs: Any
    ) -> None:
        """Run when LLM starts running."""
        self.call_count += 1

        logger.info("=" * 80)
        logger.info(f"[LLM CALL #{self.call_count}] START")
        logger.info("=" * 80)

        # Log model info
        if serialized:
            model_name = serialized.get("name", "unknown")
            model_id = serialized.get("id", ["unknown"])
            if isinstance(model_id, list):
                model_id = model_id[-1] if model_id else "unknown"
        else:
            model_name = "unknown"
            model_id = "unknown"

        logger.info(f"Model: {model_name} ({model_id})")
        logger.info(f"Timestamp: {datetime.now().isoformat()}")
        logger.info(f"Number of prompts: {len(prompts)}")
        logger.info("-" * 80)

        # Log prompts
        for i, prompt in enumerate(prompts, 1):
            if self.verbose:
                logger.info(f"[PROMPT #{i}]")
                logger.info(prompt)
                logger.info("-" * 80)
            else:
                # Log summary
                prompt_preview = prompt[:200] + "..." if len(prompt) > 200 else prompt
                logger.info(f"[PROMPT #{i}] Length: {len(prompt)} chars")
                logger.info(f"Preview: {prompt_preview}")
                logger.info("-" * 80)

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Run when LLM ends running."""
        logger.info("=" * 80)
        logger.info(f"[LLM CALL #{self.call_count}] END")
        logger.info("=" * 80)

        # Extract generations
        for i, generation_list in enumerate(response.generations, 1):
            logger.info(f"[GENERATION #{i}]")

            for j, generation in enumerate(generation_list, 1):
                response_text = generation.text

                if self.verbose:
                    logger.info(f"Response {j}:")
                    logger.info(response_text)
                else:
                    # Log summary
                    response_preview = response_text[:200] + "..." if len(response_text) > 200 else response_text
                    logger.info(f"Response {j} Length: {len(response_text)} chars")
                    logger.info(f"Preview: {response_preview}")

                # Log token usage if available
                if generation.generation_info:
                    logger.info(f"Generation Info: {generation.generation_info}")

            logger.info("-" * 80)

        # Log token usage from response metadata
        if response.llm_output:
            logger.info("LLM Output Metadata:")

            # Token usage
            token_usage = response.llm_output.get("token_usage", {})
            if token_usage:
                prompt_tokens = token_usage.get("prompt_tokens", 0)
                completion_tokens = token_usage.get("completion_tokens", 0)
                total_tokens = token_usage.get("total_tokens", 0)

                logger.info(f"  Prompt tokens: {prompt_tokens}")
                logger.info(f"  Completion tokens: {completion_tokens}")
                logger.info(f"  Total tokens: {total_tokens}")

                self.total_tokens += total_tokens
                logger.info(f"  Cumulative total tokens: {self.total_tokens}")

            # Model name
            model_name = response.llm_output.get("model_name")
            if model_name:
                logger.info(f"  Model: {model_name}")

            logger.info("-" * 80)

        logger.info(f"[LLM CALL #{self.call_count}] COMPLETED")
        logger.info("=" * 80)
        logger.info("")  # Blank line for readability

    def on_llm_error(
        self,
        error: Exception,
        **kwargs: Any
    ) -> None:
        """Run when LLM errors."""
        logger.error("=" * 80)
        logger.error(f"[LLM CALL #{self.call_count}] ERROR")
        logger.error("=" * 80)
        logger.error(f"Error: {error}", exc_info=True)
        logger.error("=" * 80)
        logger.error("")

    def on_chain_start(
        self,
        serialized: Dict[str, Any],
        inputs: Dict[str, Any],
        **kwargs: Any
    ) -> None:
        """Run when chain starts running."""
        chain_name = serialized.get("name", "unknown") if serialized else "unknown"
        logger.debug(f"[CHAIN START] {chain_name}")
        if inputs:
            logger.debug(f"  Inputs: {list(inputs.keys())}")

    def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> None:
        """Run when chain ends running."""
        logger.debug(f"[CHAIN END]")
        logger.debug(f"  Outputs: {list(outputs.keys())}")

    def on_chain_error(
        self,
        error: Exception,
        **kwargs: Any
    ) -> None:
        """Run when chain errors."""
        logger.error(f"[CHAIN ERROR] {error}", exc_info=True)

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        **kwargs: Any
    ) -> None:
        """Run when tool starts running."""
        tool_name = serialized.get("name", "unknown") if serialized else "unknown"
        logger.info(f"[TOOL START] {tool_name}")

        if self.verbose:
            logger.info(f"  Input: {input_str}")
        else:
            input_preview = input_str[:100] + "..." if len(input_str) > 100 else input_str
            logger.info(f"  Input preview: {input_preview}")

    def on_tool_end(self, output: str, **kwargs: Any) -> None:
        """Run when tool ends running."""
        logger.info(f"[TOOL END]")

        if self.verbose:
            logger.info(f"  Output: {output}")
        else:
            output_preview = output[:100] + "..." if len(output) > 100 else output
            logger.info(f"  Output preview: {output_preview}")

    def on_tool_error(
        self,
        error: Exception,
        **kwargs: Any
    ) -> None:
        """Run when tool errors."""
        logger.error(f"[TOOL ERROR] {error}", exc_info=True)

    def on_agent_action(self, action: Any, **kwargs: Any) -> None:
        """Run on agent action."""
        logger.info(f"[AGENT ACTION] Tool: {action.tool}, Input: {action.tool_input}")

    def on_agent_finish(self, finish: Any, **kwargs: Any) -> None:
        """Run on agent finish."""
        output = ""
        if finish and hasattr(finish, 'return_values') and finish.return_values:
            output = finish.return_values.get('output', '')[:100]
        logger.info(f"[AGENT FINISH] Output: {output}...")

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about LLM usage."""
        return {
            "total_llm_calls": self.call_count,
            "total_tokens": self.total_tokens,
        }
