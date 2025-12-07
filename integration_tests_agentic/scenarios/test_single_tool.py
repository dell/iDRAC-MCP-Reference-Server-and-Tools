# Licensed to You under the Apache License, Version 2.0

"""
Single Tool Execution Tests

Tests that verify the agent can correctly use individual tools
with various parameter combinations.
"""

import pytest
from typing import Any
from utils.test_runner import AgentRunner


@pytest.mark.agentic
@pytest.mark.tier1
class TestSingleToolExecution:
    """Test individual tool execution scenarios."""

    def test_list_systems_basic(
        self,
        agent_executor: Any,
        agent_runner: AgentRunner
    ):
        """Test basic list_systems tool usage."""
        result = agent_runner.run_test(
            agent_executor,
            "List all computer systems",
            expected_tools=["list_systems"]
        )

        assert result['success'], f"Test failed: {result['errors']}"
        assert result['num_iterations'] <= 3, \
            f"Agent took {result['num_iterations']} iterations (expected <= 3)"

    def test_get_system_info_with_default_parameter(
        self,
        agent_executor: Any,
        agent_runner: AgentRunner
    ):
        """Test get_system_info with default system_id parameter."""
        result = agent_runner.run_test(
            agent_executor,
            "Get information about the system",
            expected_tools=["get_system_info"]
        )

        assert result['success'], f"Test failed: {result['errors']}"
        # Should use default system_id = System.Embedded.1

    def test_get_system_info_with_explicit_parameter(
        self,
        agent_executor: Any,
        agent_runner: AgentRunner
    ):
        """Test get_system_info with explicitly specified system_id."""
        result = agent_runner.run_test(
            agent_executor,
            "Get information about system with ID System.Embedded.1",
            expected_tools=["get_system_info"],
            expected_in_output=["System.Embedded.1"]
        )

        assert result['success'], f"Test failed: {result['errors']}"

    def test_get_service_root(
        self,
        agent_executor: Any,
        agent_runner: AgentRunner
    ):
        """Test get_service_root tool (no parameters)."""
        result = agent_runner.run_test(
            agent_executor,
            "Show me the Redfish service root information",
            expected_tools=["get_service_root"]
        )

        assert result['success'], f"Test failed: {result['errors']}"

    @pytest.mark.mock_only
    def test_reset_system_understands_power_on(
        self,
        agent_executor: Any,
        agent_runner: AgentRunner
    ):
        """Test that agent can map 'power on' to reset_system tool."""
        # Note: This is mock_only to avoid actually resetting real hardware
        result = agent_runner.run_test(
            agent_executor,
            "Power on the system",
            expected_tools=["reset_system"]
        )

        assert result['success'], f"Test failed: {result['errors']}"

    def test_agent_extracts_parameters_from_natural_language(
        self,
        agent_executor: Any,
        agent_runner: AgentRunner
    ):
        """Test that agent can extract parameters from conversational input."""
        result = agent_runner.run_test(
            agent_executor,
            "I want to see details for system System.Embedded.1",
            expected_tools=["get_system_info"],
            expected_in_output=["System.Embedded.1"]
        )

        assert result['success'], f"Test failed: {result['errors']}"


@pytest.mark.agentic
@pytest.mark.tier2
class TestParameterHandling:
    """Test how agent handles different parameter scenarios."""

    def test_agent_uses_default_when_parameter_not_specified(
        self,
        agent_executor: Any,
        agent_runner: AgentRunner
    ):
        """Test that default parameters are used appropriately."""
        result = agent_runner.run_test(
            agent_executor,
            "Show me system information",
            expected_tools=["get_system_info"]
        )

        assert result['success'], f"Test failed: {result['errors']}"
        # Agent should use default system_id

    def test_agent_handles_ambiguous_parameter_requests(
        self,
        agent_executor: Any,
        agent_runner: AgentRunner
    ):
        """Test agent behavior when parameter value is ambiguous."""
        result = agent_runner.run_test(
            agent_executor,
            "Get information about the main system",
            expected_tools=["get_system_info"]
        )

        # Agent should either ask for clarification or use default
        assert len(result['output']) > 0, "Agent provided no output"


@pytest.mark.agentic
@pytest.mark.tier2
class TestToolSelection:
    """Test that agent selects appropriate tools based on user intent."""

    def test_selects_list_systems_for_inventory(
        self,
        agent_executor: Any,
        agent_runner: AgentRunner
    ):
        """Test tool selection for inventory-related queries."""
        queries = [
            "What systems are available?",
            "Show me all servers",
            "List the managed systems",
        ]

        for query in queries:
            result = agent_runner.run_test(
                agent_executor,
                query,
                expected_tools=["list_systems"]
            )

            assert result['success'], \
                f"Failed for query '{query}': {result['errors']}"

    def test_selects_get_system_info_for_details(
        self,
        agent_executor: Any,
        agent_runner: AgentRunner
    ):
        """Test tool selection for detail queries."""
        queries = [
            "Get details about System.Embedded.1",
            "Show me information for the system",
            "What is the status of System.Embedded.1?",
        ]

        for query in queries:
            result = agent_runner.run_test(
                agent_executor,
                query,
                expected_tools=["get_system_info"]
            )

            assert result['success'], \
                f"Failed for query '{query}': {result['errors']}"

    def test_selects_get_service_root_for_api_discovery(
        self,
        agent_executor: Any,
        agent_runner: AgentRunner
    ):
        """Test tool selection for API discovery queries."""
        queries = [
            "What Redfish services are available?",
            "Show me the service root",
        ]

        for query in queries:
            result = agent_runner.run_test(
                agent_executor,
                query,
                expected_tools=["get_service_root"]
            )

            assert result['success'], \
                f"Failed for query '{query}': {result['errors']}"
