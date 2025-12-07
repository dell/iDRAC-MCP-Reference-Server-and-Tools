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


"""Executor for custom workflows that compose multiple tool calls."""

import re
import json
from datetime import datetime
from typing import Dict, Any, Callable, List, Optional
from jsonpath_ng import parse as jsonpath_parse

from ..models.workflow_definition import (
    WorkflowDefinition,
    WorkflowStep,
    WorkflowExecutionContext,
    WorkflowExecutionResult,
    ErrorStrategy,
)


class WorkflowExecutor:
    """
    Executes custom workflows by orchestrating multiple tool calls.

    Handles:
    - Variable substitution (${inputs.x}, ${steps.y.output})
    - Data flow between steps
    - Conditional execution
    - Error handling
    - Output formatting
    """

    def __init__(self, tool_registry: Dict[str, Callable]):
        """
        Initialize workflow executor.

        Args:
            tool_registry: Dictionary of tool_name -> callable function
                          These are the generated tool functions from tools.yaml
        """
        self.tool_registry = tool_registry

    def execute(
        self,
        workflow: WorkflowDefinition,
        idrac_ip: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        auth_token: Optional[str] = None,
        **workflow_inputs
    ) -> WorkflowExecutionResult:
        """
        Execute a workflow.

        Args:
            workflow: Workflow definition to execute
            idrac_ip: iDRAC IP address (required for all tool calls)
            username: iDRAC username (for Basic Auth)
            password: iDRAC password (for Basic Auth)
            auth_token: iDRAC auth token (for Token Auth)
            **workflow_inputs: User-provided input values for the workflow

        Returns:
            WorkflowExecutionResult with execution details and output

        Raises:
            ValueError: If required inputs are missing or invalid
            RuntimeError: If workflow execution fails
        """
        # Initialize execution context
        context = WorkflowExecutionContext(
            workflow_name=workflow.name,
            inputs=workflow_inputs,
            step_outputs={},
            variables={
                'workflow': {
                    'name': workflow.name,
                    'timestamp': datetime.now().isoformat(),
                }
            },
            errors=[],
            start_time=datetime.now().isoformat(),
        )

        # Validate inputs
        self._validate_inputs(workflow, workflow_inputs)

        # Store credentials in context for passing to tool calls
        context.variables['credentials'] = {
            'idrac_ip': idrac_ip,
            'username': username,
            'password': password,
            'auth_token': auth_token,
        }

        # Execute steps sequentially
        success = True
        error_message = None

        try:
            for step in workflow.steps:
                # Check condition (if specified)
                if step.condition and not self._evaluate_condition(step.condition, context):
                    print(f"[Workflow] Skipping step '{step.name}' (condition not met)")
                    continue

                # Execute step
                try:
                    print(f"[Workflow] Executing step: {step.name} (tool: {step.tool})")
                    step_result = self._execute_step(step, context)

                    # Store step output
                    context.step_outputs[step.name] = step_result

                except Exception as e:
                    # Handle error according to strategy
                    error_info = {
                        'step': step.name,
                        'error': str(e),
                        'strategy': step.on_error.value,
                    }
                    context.errors.append(error_info)

                    if step.on_error == ErrorStrategy.FAIL:
                        success = False
                        error_message = f"Step '{step.name}' failed: {str(e)}"
                        break
                    elif step.on_error == ErrorStrategy.SKIP_REMAINING:
                        print(f"[Workflow] Step '{step.name}' failed, skipping remaining steps")
                        break
                    else:  # CONTINUE
                        print(f"[Workflow] Step '{step.name}' failed but continuing: {str(e)}")
                        context.step_outputs[step.name] = {'error': str(e)}

            # Generate final output
            if success:
                final_output = self._build_output(workflow.output, context)
            else:
                final_output = {'error': error_message}

        except Exception as e:
            success = False
            error_message = f"Workflow execution failed: {str(e)}"
            final_output = {'error': error_message}

        context.end_time = datetime.now().isoformat()

        return WorkflowExecutionResult(
            workflow_name=workflow.name,
            success=success,
            output=final_output,
            context=context,
            error=error_message,
        )

    def _validate_inputs(self, workflow: WorkflowDefinition, inputs: Dict[str, Any]) -> None:
        """
        Validate that required inputs are provided.

        Args:
            workflow: Workflow definition
            inputs: User-provided inputs

        Raises:
            ValueError: If required inputs are missing
        """
        for input_def in workflow.inputs:
            if input_def.required and input_def.name not in inputs:
                if input_def.default is not None:
                    inputs[input_def.name] = input_def.default
                else:
                    raise ValueError(
                        f"Required workflow input '{input_def.name}' is missing"
                    )

    def _execute_step(
        self, step: WorkflowStep, context: WorkflowExecutionContext
    ) -> Dict[str, Any]:
        """
        Execute a single workflow step.

        Args:
            step: Step definition
            context: Execution context

        Returns:
            Dictionary of step outputs (extracted using JSONPath)

        Raises:
            ValueError: If tool not found
            RuntimeError: If tool execution fails
        """
        # Get the tool function
        tool_func = self.tool_registry.get(step.tool)
        if not tool_func:
            raise ValueError(f"Tool '{step.tool}' not found in registry")

        # Validate that tool_func is callable
        if not callable(tool_func):
            raise TypeError(
                f"Tool '{step.tool}' is not callable (got {type(tool_func).__name__}). "
                f"Check that the tool registry was populated correctly."
            )

        # Substitute variables in parameters
        resolved_params = self._resolve_parameters(step.parameters, context)

        # Add credentials to parameters
        credentials = context.variables['credentials']
        resolved_params['idrac_ip'] = credentials['idrac_ip']
        resolved_params['username'] = credentials['username']
        resolved_params['password'] = credentials['password']
        resolved_params['auth_token'] = credentials['auth_token']

        # Call the tool
        try:
            result = tool_func(**resolved_params)
        except Exception as e:
            raise RuntimeError(f"Tool '{step.tool}' execution failed: {str(e)}")

        # Extract outputs using JSONPath
        step_outputs = {}
        for output_name, jsonpath_expr in step.outputs.items():
            try:
                extracted = self._extract_with_jsonpath(result, jsonpath_expr)
                step_outputs[output_name] = extracted
            except Exception as e:
                print(f"[Workflow] Warning: Failed to extract output '{output_name}': {e}")
                step_outputs[output_name] = None

        # If no outputs specified, return entire result
        if not step.outputs:
            step_outputs['result'] = result

        return step_outputs

    def _resolve_parameters(
        self, parameters: Dict[str, Any], context: WorkflowExecutionContext
    ) -> Dict[str, Any]:
        """
        Resolve parameter values by substituting variables.

        Supports:
        - ${inputs.param_name} - User-provided inputs
        - ${steps.step_name.output_name} - Outputs from previous steps
        - ${workflow.property} - Workflow metadata

        Args:
            parameters: Parameter dict with possible ${} substitutions
            context: Execution context

        Returns:
            Resolved parameters dict
        """
        resolved = {}

        for key, value in parameters.items():
            if isinstance(value, str):
                resolved[key] = self._substitute_variables(value, context)
            elif isinstance(value, dict):
                resolved[key] = self._resolve_parameters(value, context)
            elif isinstance(value, list):
                resolved[key] = [
                    self._substitute_variables(item, context) if isinstance(item, str) else item
                    for item in value
                ]
            else:
                resolved[key] = value

        return resolved

    def _substitute_variables(self, value: str, context: WorkflowExecutionContext) -> Any:
        """
        Substitute ${} variables in a string.

        Args:
            value: String potentially containing ${variable.path}
            context: Execution context

        Returns:
            Resolved value (can be string, int, bool, dict, etc.)
        """
        # Pattern: ${inputs.name} or ${steps.step.output} or ${workflow.property}
        pattern = r'\$\{\{([^}]+)\}\}'
        matches = re.findall(pattern, value)

        if not matches:
            return value

        # If the entire string is a single variable, return its actual type
        if len(matches) == 1 and value == f"${{{{{matches[0]}}}}}":
            return self._resolve_variable_path(matches[0].strip(), context)

        # Otherwise, do string substitution
        result = value
        for match in matches:
            var_value = self._resolve_variable_path(match.strip(), context)
            result = result.replace(f"${{{{{match}}}}}", str(var_value))

        return result

    def _resolve_variable_path(self, path: str, context: WorkflowExecutionContext) -> Any:
        """
        Resolve a variable path like 'inputs.system_id' or 'steps.get_system.system_data'.

        Args:
            path: Dot-separated variable path
            context: Execution context

        Returns:
            Resolved value

        Raises:
            ValueError: If path is invalid or not found
        """
        parts = path.split('.')

        if parts[0] == 'inputs':
            # inputs.param_name
            if len(parts) < 2:
                raise ValueError(f"Invalid input path: {path}")
            return context.inputs.get(parts[1])

        elif parts[0] == 'steps':
            # steps.step_name.output_name
            if len(parts) < 3:
                raise ValueError(f"Invalid step output path: {path}")
            step_name = parts[1]
            output_name = parts[2]

            if step_name not in context.step_outputs:
                raise ValueError(f"Step '{step_name}' not found or not yet executed")

            return context.step_outputs[step_name].get(output_name)

        elif parts[0] == 'workflow':
            # workflow.property
            if len(parts) < 2:
                raise ValueError(f"Invalid workflow path: {path}")
            return context.variables['workflow'].get(parts[1])

        else:
            raise ValueError(f"Unknown variable namespace: {parts[0]}")

    def _extract_with_jsonpath(self, data: Any, jsonpath_expr: str) -> Any:
        """
        Extract data using JSONPath expression.

        Args:
            data: Data to extract from
            jsonpath_expr: JSONPath expression (e.g., "$.Members[0].Health")

        Returns:
            Extracted value(s)
        """
        if jsonpath_expr == "$":
            return data

        jsonpath_expr_obj = jsonpath_parse(jsonpath_expr)
        matches = jsonpath_expr_obj.find(data)

        if not matches:
            return None

        # Return first match if single value, otherwise list
        if len(matches) == 1:
            return matches[0].value
        else:
            return [match.value for match in matches]

    def _evaluate_condition(self, condition: str, context: WorkflowExecutionContext) -> bool:
        """
        Evaluate a conditional expression.

        Args:
            condition: Condition string (e.g., "${inputs.include_logs} == true")
            context: Execution context

        Returns:
            True if condition is met, False otherwise
        """
        try:
            # Substitute variables
            resolved = self._substitute_variables(condition, context)

            # Simple evaluation (supports ==, !=, >, <, >=, <=)
            # For safety, only eval simple comparisons
            if isinstance(resolved, bool):
                return resolved

            # Evaluate as Python expression (limited for safety)
            # This is a simple approach - could be enhanced with a proper expression parser
            result = eval(resolved, {"__builtins__": {}}, {})
            return bool(result)

        except Exception as e:
            print(f"[Workflow] Warning: Failed to evaluate condition '{condition}': {e}")
            return False

    def _build_output(
        self, output_template: Dict[str, Any], context: WorkflowExecutionContext
    ) -> Dict[str, Any]:
        """
        Build final output by substituting variables in output template.

        Args:
            output_template: Output structure with ${} substitutions
            context: Execution context

        Returns:
            Resolved output dictionary
        """
        if not output_template:
            # Default: return all step outputs
            return {
                'steps': context.step_outputs,
                'execution_time': context.start_time,
            }

        return self._resolve_parameters(output_template, context)
