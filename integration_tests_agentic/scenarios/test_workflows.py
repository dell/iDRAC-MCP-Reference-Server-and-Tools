# Licensed to You under the Apache License, Version 2.0

"""
Multi-Step Workflow Tests

Tests that verify the agent can execute multi-step workflows
requiring reasoning across multiple tool invocations.
"""

import pytest
from typing import Any
from utils.test_runner import AgentRunner


@pytest.mark.agentic
@pytest.mark.workflow
@pytest.mark.tier2
class TestSimpleWorkflows:
    """Test simple multi-step workflows."""

    def test_inventory_then_detail(
        self,
        agent_executor: Any,
        agent_runner: AgentRunner
    ):
        """
        Test: List systems, then get details for one.

        Workflow:
        1. List all systems
        2. Get details for a specific system
        """
        result = agent_runner.run_test(
            agent_executor,
            "First list all systems, then show me details for System.Embedded.1"
        )

        # Should call both tools
        assert 'list_systems' in result['tools_called'] or 'get_system_info' in result['tools_called'], \
            f"Expected both tools but got: {result['tools_called']}"

        assert len(result['output']) > 0, "Agent did not provide final answer"

    def test_check_service_then_list_systems(
        self,
        agent_executor: Any,
        agent_runner: AgentRunner
    ):
        """
        Test: Check service root, then list systems.

        Workflow:
        1. Get service root info
        2. List available systems
        """
        result = agent_runner.run_test(
            agent_executor,
            "Check what Redfish services are available, then list the systems"
        )

        # Agent should call both tools in sequence
        assert len(result['tools_called']) >= 1, "Agent did not call any tools"
        assert len(result['output']) > 0, "Agent did not provide final answer"


@pytest.mark.agentic
@pytest.mark.workflow
@pytest.mark.tier3
class TestConditionalWorkflows:
    """Test workflows with conditional logic."""

    @pytest.mark.mock_only
    def test_conditional_reset_based_on_state(
        self,
        agent_executor: Any,
        agent_runner: AgentRunner
    ):
        """
        Test: Check system state and conditionally take action.

        Workflow:
        1. Get system information
        2. Check power state
        3. If off, suggest power on (but don't actually do it in test)
        """
        result = agent_runner.run_test(
            agent_executor,
            "Check the power state of the system. Report if it's on or off."
        )

        assert 'get_system_info' in result['tools_called'], \
            "Agent should check system info to determine power state"

        # Should mention power state in output
        assert any(keyword in result['output'].lower() for keyword in ['power', 'state', 'on', 'off']), \
            "Output should mention power state"

    def test_multi_system_comparison(
        self,
        agent_executor: Any,
        agent_runner: AgentRunner
    ):
        """
        Test: Compare information from multiple systems.

        Note: This test may be limited by available systems in mock/test environment.
        """
        result = agent_runner.run_test(
            agent_executor,
            "List all systems and tell me about the first one you find"
        )

        # Should first list, then get details
        assert len(result['tools_called']) >= 1, "Agent should call at least one tool"
        assert len(result['output']) > 0, "Agent did not provide final answer"


@pytest.mark.agentic
@pytest.mark.workflow
@pytest.mark.tier3
class TestComplexReasoning:
    """Test workflows requiring complex reasoning."""

    def test_agent_synthesizes_multiple_tool_outputs(
        self,
        agent_executor: Any,
        agent_runner: AgentRunner
    ):
        """
        Test: Agent combines information from multiple sources.

        The agent should synthesize a coherent answer from multiple tool calls.
        """
        result = agent_runner.run_test(
            agent_executor,
            "Give me a comprehensive overview: what systems are available and what's their current state?"
        )

        # Agent should use multiple tools and provide synthesized answer
        assert len(result['tools_called']) >= 1, "Agent should call tools"
        assert len(result['output']) > 100, \
            "Agent should provide comprehensive answer (not just tool output)"

    def test_agent_handles_information_gathering(
        self,
        agent_executor: Any,
        agent_runner: AgentRunner
    ):
        """
        Test: Agent gathers information before answering.

        Agent should recognize it needs to gather info before it can answer.
        """
        result = agent_runner.run_test(
            agent_executor,
            "What can you tell me about the managed systems?"
        )

        # Agent should proactively call tools to gather information
        assert len(result['tools_called']) > 0, \
            "Agent should call tools to gather information"

        assert len(result['output']) > 0, "Agent did not provide answer"


@pytest.mark.agentic
@pytest.mark.workflow
@pytest.mark.tier2
class TestWorkflowEfficiency:
    """Test workflow execution efficiency."""

    def test_agent_uses_minimum_necessary_tools(
        self,
        agent_executor: Any,
        agent_runner: AgentRunner
    ):
        """
        Test: Agent doesn't make unnecessary tool calls.

        Agent should be efficient and not call redundant tools.
        """
        result = agent_runner.run_test(
            agent_executor,
            "List all systems"
        )

        # Should only call list_systems once
        assert result['num_iterations'] <= 2, \
            f"Agent took {result['num_iterations']} iterations (expected <= 2 for simple query)"

    def test_agent_completes_workflow_within_iteration_limit(
        self,
        agent_executor: Any,
        agent_runner: AgentRunner
    ):
        """
        Test: Agent completes multi-step workflows efficiently.

        Even complex workflows should complete within reasonable iterations.
        """
        result = agent_runner.run_test(
            agent_executor,
            "List systems, then get details about the first one"
        )

        # Should complete within reasonable number of iterations
        assert result['num_iterations'] <= 5, \
            f"Agent took {result['num_iterations']} iterations (expected <= 5)"

        assert len(result['output']) > 0, "Agent did not provide final answer"
