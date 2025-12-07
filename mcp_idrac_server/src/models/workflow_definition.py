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


"""Data models for workflow definitions."""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from enum import Enum


class ErrorStrategy(str, Enum):
    """Strategy for handling errors in workflow steps."""
    FAIL = "fail"  # Stop workflow and raise error
    CONTINUE = "continue"  # Log error and continue to next step
    SKIP_REMAINING = "skip_remaining"  # Skip remaining steps but don't fail


@dataclass
class WorkflowInput:
    """Definition of a workflow input parameter."""
    name: str
    type: str  # string, integer, boolean, array, object
    description: str = ""
    required: bool = True
    default: Any = None


@dataclass
class WorkflowOutput:
    """Definition of how to extract output from a step."""
    name: str
    path: str  # JSONPath expression to extract data
    transform: Optional[str] = None  # Optional transformation (e.g., "length", "first")


@dataclass
class WorkflowStep:
    """Definition of a single step in a workflow."""
    name: str
    tool: str  # Name of the tool to call (from tools.yaml)
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)  # Tool parameters (supports ${} substitution)
    outputs: Dict[str, str] = field(default_factory=dict)  # name -> JSONPath mapping
    condition: Optional[str] = None  # Conditional expression (e.g., "${inputs.include_logs} == true")
    on_error: ErrorStrategy = ErrorStrategy.FAIL
    timeout: Optional[int] = None  # Override default timeout for this step


@dataclass
class WorkflowDefinition:
    """Complete workflow definition."""
    name: str
    description: str
    category: str = "custom"
    enabled: bool = True
    inputs: List[WorkflowInput] = field(default_factory=list)
    steps: List[WorkflowStep] = field(default_factory=list)
    output: Dict[str, Any] = field(default_factory=dict)  # Output structure with ${} substitutions
    metadata: Dict[str, Any] = field(default_factory=dict)  # Additional metadata


@dataclass
class WorkflowExecutionContext:
    """Runtime context for workflow execution."""
    workflow_name: str
    inputs: Dict[str, Any]  # User-provided input values
    step_outputs: Dict[str, Dict[str, Any]]  # step_name -> outputs mapping
    variables: Dict[str, Any]  # Runtime variables
    errors: List[Dict[str, Any]]  # Errors encountered during execution
    start_time: Optional[str] = None
    end_time: Optional[str] = None


@dataclass
class WorkflowExecutionResult:
    """Result of workflow execution."""
    workflow_name: str
    success: bool
    output: Dict[str, Any]  # Final structured output
    context: WorkflowExecutionContext
    error: Optional[str] = None
