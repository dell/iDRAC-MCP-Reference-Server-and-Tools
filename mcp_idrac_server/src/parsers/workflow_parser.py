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


"""Parser for workflow configuration files."""

import yaml
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..models.workflow_definition import (
    WorkflowDefinition,
    WorkflowStep,
    WorkflowInput,
    ErrorStrategy,
)


class WorkflowParser:
    """
    Parser for workflow configuration YAML files.

    Reads and validates workflow definitions that compose multiple tools into
    higher-level operations.
    """

    def __init__(self, config_file: str):
        """
        Initialize workflow parser.

        Args:
            config_file: Path to workflows.yaml file
        """
        self.config_file = Path(config_file)
        self.workflows: List[WorkflowDefinition] = []
        self._parse()

    def _parse(self) -> None:
        """Parse the workflow configuration file."""
        if not self.config_file.exists():
            print(f"Warning: Workflow config file not found: {self.config_file}")
            return

        with open(self.config_file, 'r') as f:
            data = yaml.safe_load(f)

        if not data:
            return

        # Parse workflows
        workflows_data = data.get('workflows', [])
        for workflow_data in workflows_data:
            workflow = self._parse_workflow(workflow_data)
            self.workflows.append(workflow)

    def _parse_workflow(self, data: Dict[str, Any]) -> WorkflowDefinition:
        """
        Parse a single workflow definition.

        Args:
            data: Workflow data from YAML

        Returns:
            WorkflowDefinition instance
        """
        # Parse inputs
        inputs = []
        for input_data in data.get('inputs', []):
            inputs.append(WorkflowInput(
                name=input_data['name'],
                type=input_data.get('type', 'string'),
                description=input_data.get('description', ''),
                required=input_data.get('required', True),
                default=input_data.get('default'),
            ))

        # Parse steps
        steps = []
        for step_data in data.get('steps', []):
            # Parse error strategy
            on_error_str = step_data.get('on_error', 'fail')
            try:
                on_error = ErrorStrategy(on_error_str)
            except ValueError:
                print(f"Warning: Invalid error strategy '{on_error_str}', using 'fail'")
                on_error = ErrorStrategy.FAIL

            steps.append(WorkflowStep(
                name=step_data['name'],
                tool=step_data['tool'],
                description=step_data.get('description', ''),
                parameters=step_data.get('parameters', {}),
                outputs=step_data.get('outputs', {}),
                condition=step_data.get('condition'),
                on_error=on_error,
                timeout=step_data.get('timeout'),
            ))

        return WorkflowDefinition(
            name=data['name'],
            description=data.get('description', ''),
            category=data.get('category', 'custom'),
            enabled=data.get('enabled', True),
            inputs=inputs,
            steps=steps,
            output=data.get('output', {}),
            metadata=data.get('metadata', {}),
        )

    def get_workflows(self) -> List[WorkflowDefinition]:
        """
        Get all parsed workflows.

        Returns:
            List of workflow definitions
        """
        return self.workflows

    def get_enabled_workflows(self) -> List[WorkflowDefinition]:
        """
        Get only enabled workflows.

        Returns:
            List of enabled workflow definitions
        """
        return [wf for wf in self.workflows if wf.enabled]

    def get_workflow_by_name(self, name: str) -> Optional[WorkflowDefinition]:
        """
        Get a specific workflow by name.

        Args:
            name: Workflow name

        Returns:
            WorkflowDefinition if found, None otherwise
        """
        for workflow in self.workflows:
            if workflow.name == name:
                return workflow
        return None

    def validate_against_tools(self, available_tools: List[str]) -> tuple:
        """
        Validate that all workflow steps reference valid tools.

        Args:
            available_tools: List of available tool names from tools.yaml

        Returns:
            Tuple of (valid_workflows, invalid_workflows)
        """
        valid = []
        invalid = []

        for workflow in self.workflows:
            is_valid = True
            for step in workflow.steps:
                if step.tool not in available_tools:
                    print(
                        f"Warning: Workflow '{workflow.name}' step '{step.name}' "
                        f"references unknown tool '{step.tool}'"
                    )
                    is_valid = False

            if is_valid:
                valid.append(workflow.name)
            else:
                invalid.append(workflow.name)

        return (valid, invalid)
