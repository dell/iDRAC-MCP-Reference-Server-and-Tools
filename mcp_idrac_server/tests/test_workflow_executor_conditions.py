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


"""Tests for WorkflowExecutor._evaluate_condition and its helpers."""

import inspect
import re

import pytest

from src.generators.workflow_executor import WorkflowExecutor
from src.models.workflow_definition import WorkflowExecutionContext


def make_context(inputs=None, step_outputs=None, workflow=None):
    """Build a minimal WorkflowExecutionContext for tests."""
    return WorkflowExecutionContext(
        workflow_name="test-workflow",
        inputs=inputs or {},
        step_outputs=step_outputs or {},
        variables={"workflow": workflow or {"name": "test-workflow"}},
        errors=[],
        start_time="2025-01-01T00:00:00",
    )


@pytest.fixture
def executor():
    return WorkflowExecutor({})


def test_no_eval_in_source():
    source = inspect.getsource(WorkflowExecutor)
    assert not re.search(r"\beval\(", source)
    assert not re.search(r"\bexec\(", source)


def test_include_logs_regression_true(executor):
    ctx = make_context(inputs={"include_logs": True})
    assert executor._evaluate_condition("${{inputs.include_logs}} == true", ctx) is True


def test_include_logs_regression_false(executor):
    ctx = make_context(inputs={"include_logs": False})
    assert executor._evaluate_condition("${{inputs.include_logs}} == true", ctx) is False


@pytest.mark.parametrize(
    "condition,expected",
    [
        ("${{inputs.a}} == ${{inputs.b}}", True),
        ("${{inputs.a}} != ${{inputs.b}}", False),
        ("${{inputs.a}} >= ${{inputs.b}}", True),
        ("${{inputs.a}} <= ${{inputs.b}}", True),
        ("${{inputs.a}} > ${{inputs.b}}", False),
        ("${{inputs.a}} < ${{inputs.b}}", False),
    ],
)
def test_numeric_operators_equal_operands(executor, condition, expected):
    ctx = make_context(inputs={"a": 5, "b": 5})
    assert executor._evaluate_condition(condition, ctx) is expected


@pytest.mark.parametrize(
    "condition,expected",
    [
        ("${{inputs.a}} == ${{inputs.b}}", False),
        ("${{inputs.a}} != ${{inputs.b}}", True),
        ("${{inputs.a}} >= ${{inputs.b}}", False),
        ("${{inputs.a}} <= ${{inputs.b}}", True),
        ("${{inputs.a}} > ${{inputs.b}}", False),
        ("${{inputs.a}} < ${{inputs.b}}", True),
        ("${{inputs.b}} >= ${{inputs.a}}", True),
        ("${{inputs.b}} > ${{inputs.a}}", True),
    ],
)
def test_numeric_operators_different_operands(executor, condition, expected):
    ctx = make_context(inputs={"a": 3, "b": 7})
    assert executor._evaluate_condition(condition, ctx) is expected


@pytest.mark.parametrize(
    "condition,expected",
    [
        ('${{inputs.a}} == "abc"', True),
        ('${{inputs.a}} != "abd"', True),
        ('${{inputs.a}} < "abd"', True),
        ('${{inputs.a}} <= "abc"', True),
        ('${{inputs.a}} > "aaa"', True),
        ('${{inputs.a}} >= "abc"', True),
    ],
)
def test_string_operators(executor, condition, expected):
    ctx = make_context(inputs={"a": "abc"})
    assert executor._evaluate_condition(condition, ctx) is expected


def test_bare_truthy_true(executor):
    ctx = make_context(inputs={"flag": True})
    assert executor._evaluate_condition("${{inputs.flag}}", ctx) is True


def test_bare_truthy_false(executor):
    ctx = make_context(inputs={"flag": False})
    assert executor._evaluate_condition("${{inputs.flag}}", ctx) is False


def test_bare_truthy_none(executor):
    ctx = make_context(inputs={"flag": None})
    assert executor._evaluate_condition("${{inputs.flag}}", ctx) is False


def test_bare_truthy_empty_string(executor):
    ctx = make_context(inputs={"flag": ""})
    assert executor._evaluate_condition("${{inputs.flag}}", ctx) is False


def test_bare_truthy_zero(executor):
    ctx = make_context(inputs={"flag": 0})
    assert executor._evaluate_condition("${{inputs.flag}}", ctx) is False


def test_bare_truthy_nonempty_string(executor):
    ctx = make_context(inputs={"flag": "hello"})
    assert executor._evaluate_condition("${{inputs.flag}}", ctx) is True


def test_quoted_literal_on_right(executor):
    ctx = make_context(step_outputs={"get_system_info": {"health_status": "OK"}})
    assert (
        executor._evaluate_condition('${{steps.get_system_info.health_status}} == "OK"', ctx)
        is True
    )
    ctx2 = make_context(step_outputs={"get_system_info": {"health_status": "Critical"}})
    assert (
        executor._evaluate_condition('${{steps.get_system_info.health_status}} == "OK"', ctx2)
        is False
    )


def test_malformed_unknown_namespace_returns_false(executor):
    ctx = make_context()
    assert executor._evaluate_condition("${{bogus.thing}} == true", ctx) is False


def test_malformed_missing_step_returns_false(executor):
    ctx = make_context()
    assert executor._evaluate_condition("${{steps.never_ran.output}} == true", ctx) is False


def test_malformed_garbage_does_not_raise(executor):
    ctx = make_context()
    # No comparison operator and no placeholder: treated as a plain literal
    # string. Not an exploit vector (never executed), and does not raise.
    result = executor._evaluate_condition(") or (", ctx)
    assert isinstance(result, bool)


def test_security_bare_payload_not_executed(executor, tmp_path):
    marker = tmp_path / "pwned"
    payload = f"__import__('os').system('touch {marker}')"
    ctx = make_context(inputs={"payload": payload})

    result = executor._evaluate_condition("${{inputs.payload}}", ctx)

    assert isinstance(result, bool)
    assert not marker.exists()


def test_security_payload_in_comparison_not_executed(executor, tmp_path):
    marker = tmp_path / "pwned2"
    payload = f"__import__('os').system('touch {marker}')"
    ctx = make_context(inputs={"payload": payload})

    result = executor._evaluate_condition("${{inputs.payload}} == 1", ctx)

    assert result is False
    assert not marker.exists()


def test_security_operand_treated_as_literal_string(executor):
    ctx = make_context(inputs={"expr": "1 == 1"})
    assert executor._evaluate_condition("${{inputs.expr}} == 1", ctx) is False
    assert executor._evaluate_condition("${{inputs.expr}}", ctx) is True
