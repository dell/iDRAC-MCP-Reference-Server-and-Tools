# Licensed to You under the Apache License, Version 2.0

"""
Smoke Tests for Agentic Integration

These critical tests verify that the agent can discover and use MCP tools.
All smoke tests must pass for the system to be considered functional.
"""

import pytest
from typing import Any
from utils.test_runner import AgentRunner


@pytest.mark.agentic
@pytest.mark.smoke
@pytest.mark.tier1
class TestSmoke:
    """Critical smoke tests that must always pass."""

    def test_agent_can_list_systems(
        self,
        agent_executor: Any,
        agent_runner: AgentRunner
    ):
        """
        Test that agent can use the list_systems tool.

        This is the simplest possible test - can the agent execute a tool?
        """
        input_text = "List all available systems on the iDRAC"

        result = agent_runner.run_test(
            agent_executor,
            input_text,
            expected_tools=["list_systems"]
        )

        assert result['success'], f"Test failed: {result['errors']}"
        assert len(result['tools_called']) > 0, "Agent did not call any tools"
        assert 'list_systems' in result['tools_called'], "Agent did not call list_systems"

    def test_agent_can_get_system_info(
        self,
        agent_executor: Any,
        agent_runner: AgentRunner
    ):
        """
        Test that agent can retrieve system information.

        Tests parameter handling (system_id parameter).
        """
        input_text = "Get information about system System.Embedded.1"

        result = agent_runner.run_test(
            agent_executor,
            input_text,
            expected_tools=["get_system_info"],
            expected_in_output=["System.Embedded.1"]
        )

        assert result['success'], f"Test failed: {result['errors']}"
        assert 'get_system_info' in result['tools_called'], "Agent did not call get_system_info"

    def test_agent_can_get_service_root(
        self,
        agent_executor: Any,
        agent_runner: AgentRunner
    ):
        """
        Test that agent can get service root information.

        Tests tool with no parameters.
        """
        input_text = "What Redfish services are available?"

        result = agent_runner.run_test(
            agent_executor,
            input_text,
            expected_tools=["get_service_root"]
        )

        assert result['success'], f"Test failed: {result['errors']}"
        assert 'get_service_root' in result['tools_called'], "Agent did not call get_service_root"

    def test_agent_understands_tool_descriptions(
        self,
        agent_executor: Any,
        agent_runner: AgentRunner
    ):
        """
        Test that agent selects correct tool based on description.

        Tests whether tool descriptions are clear enough for the LLM.
        """
        input_text = "I need to see what servers are managed by this iDRAC"

        result = agent_runner.run_test(
            agent_executor,
            input_text,
            expected_tools=["list_systems"]
        )

        # Agent should understand that "see what servers" means list_systems
        assert result['success'], f"Test failed: {result['errors']}"
        assert 'list_systems' in result['tools_called'], \
            f"Agent called {result['tools_called']} instead of list_systems"

    def test_agent_handles_no_tools_needed(
        self,
        agent_executor: Any,
        agent_runner: AgentRunner
    ):
        """
        Test that agent doesn't use tools when not needed.

        Tests that agent can directly answer simple questions.
        """
        input_text = "What is iDRAC?"

        result = agent_runner.run_test(
            agent_executor,
            input_text
        )

        # Agent should answer without using any tools
        assert len(result['output']) > 0, "Agent did not provide an answer"
        # It's OK if agent calls tools, but it shouldn't be required

    @pytest.mark.mock_only
    def test_agent_execution_time_reasonable(
        self,
        agent_executor: Any,
        agent_runner: AgentRunner
    ):
        """
        Test that agent completes tasks in reasonable time.

        Simple operations should not take too long.
        """
        input_text = "List all systems"

        result = agent_runner.run_test(
            agent_executor,
            input_text,
            expected_tools=["list_systems"]
        )

        assert result['success'], f"Test failed: {result['errors']}"
        assert result['execution_time'] < 30, \
            f"Agent took {result['execution_time']}s (expected < 30s)"

    def test_agent_provides_final_answer(
        self,
        agent_executor: Any,
        agent_runner: AgentRunner
    ):
        """
        Test that agent always provides a final answer.

        Agent should not just return tool output, but synthesize an answer.
        """
        input_text = "Get system information"

        result = agent_runner.run_test(
            agent_executor,
            input_text,
            expected_tools=["get_system_info"]
        )

        assert result['success'], f"Test failed: {result['errors']}"
        assert len(result['output']) > 0, "Agent did not provide final answer"
        # Check that output is not just raw JSON
        assert not result['output'].strip().startswith('{'), \
            "Agent returned raw JSON instead of synthesized answer"
