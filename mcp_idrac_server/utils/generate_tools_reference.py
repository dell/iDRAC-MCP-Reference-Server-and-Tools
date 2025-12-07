#!/usr/bin/env python3
# Licensed to You under the Apache License, Version 2.0

"""
Script to generate a comprehensive tools_reference.yaml file containing all
operations from the OpenAPI specification.
"""

import yaml
from pathlib import Path


def categorize_operation(path: str, method: str, operation_id: str, tags: list) -> str:
    """Categorize an operation based on its path, method, and tags."""
    path_lower = path.lower()

    # Use tags first if available
    if tags:
        tag = tags[0].lower()
        if 'system' in tag:
            return 'system_management'
        elif 'bios' in tag:
            return 'bios_configuration'
        elif 'memory' in tag or 'processor' in tag or 'storage' in tag:
            return 'hardware_inventory'
        elif 'network' in tag or 'ethernet' in tag:
            return 'network_configuration'
        elif 'account' in tag or 'user' in tag:
            return 'account_management'
        elif 'manager' in tag:
            return 'manager_operations'
        elif 'chassis' in tag:
            return 'chassis_management'
        elif 'power' in tag or 'thermal' in tag:
            return 'power_thermal'
        elif 'cert' in tag or 'security' in tag:
            return 'security'
        elif 'log' in tag or 'event' in tag:
            return 'logging'
        elif 'update' in tag or 'firmware' in tag:
            return 'firmware_update'
        elif 'task' in tag or 'job' in tag:
            return 'task_management'

    # Fall back to path-based categorization
    if '/systems/' in path_lower:
        if '/bios' in path_lower:
            return 'bios_configuration'
        elif '/memory' in path_lower or '/processors' in path_lower:
            return 'hardware_inventory'
        elif '/ethernetinterfaces' in path_lower or '/networkinterfaces' in path_lower:
            return 'network_configuration'
        elif '/storage' in path_lower:
            return 'storage_management'
        return 'system_management'

    elif '/managers/' in path_lower:
        if '/accounts' in path_lower:
            return 'account_management'
        elif '/networkprotocol' in path_lower or '/ethernetinterfaces' in path_lower:
            return 'network_configuration'
        elif '/logs' in path_lower:
            return 'logging'
        elif '/virtualmedia' in path_lower:
            return 'virtual_media'
        return 'manager_operations'

    elif '/chassis/' in path_lower:
        if '/power' in path_lower or '/thermal' in path_lower:
            return 'power_thermal'
        return 'chassis_management'

    elif '/accountservice' in path_lower:
        return 'account_management'

    elif '/sessionservice' in path_lower or '/sessions' in path_lower:
        return 'session_management'

    elif '/updateservice' in path_lower or '/firmwareinventory' in path_lower:
        return 'firmware_update'

    elif '/taskservice' in path_lower or '/tasks' in path_lower:
        return 'task_management'

    elif '/eventservice' in path_lower or '/logservice' in path_lower:
        return 'logging'

    elif '/certificateservice' in path_lower or '/certificates' in path_lower:
        return 'security'

    return 'other'


def generate_tool_name(operation_id: str, path: str, method: str) -> str:
    """Generate a user-friendly tool name from operation details."""
    # If operation_id is already descriptive, use it
    if operation_id and not operation_id.startswith(('GET_', 'POST_', 'PUT_', 'PATCH_', 'DELETE_', 'Action_')):
        return operation_id.lower()

    # Generate from method and path
    method_lower = method.lower()

    # Extract meaningful parts from path
    path_parts = [p for p in path.split('/') if p and not p.startswith('{')]

    # Remove version and common prefixes
    path_parts = [p for p in path_parts if p not in ['redfish', 'v1']]

    if not path_parts:
        return f"{method_lower}_operation"

    # Build name
    if method_lower == 'get':
        if path.endswith('}'):  # Collection member
            prefix = 'get'
        else:  # Collection
            prefix = 'list'
    elif method_lower == 'post':
        if 'Actions' in path:
            prefix = 'action'
        else:
            prefix = 'create'
    elif method_lower == 'patch':
        prefix = 'update'
    elif method_lower == 'put':
        prefix = 'set'
    elif method_lower == 'delete':
        prefix = 'delete'
    else:
        prefix = method_lower

    # Join parts
    name = f"{prefix}_{'_'.join(path_parts)}"
    return name.lower()


def extract_parameter_mappings(operation_spec):
    """Extract parameter mappings from an operation."""
    mappings = []

    # Extract path, query, and header parameters
    params = operation_spec.get('parameters', [])
    for param_spec in params:
        # Skip references for now (simplified)
        if '$ref' in param_spec:
            continue

        param_name = param_spec.get('name', '')
        param_in = param_spec.get('in', 'query')
        param_required = param_spec.get('required', False)
        param_desc = param_spec.get('description', '')

        # Map parameter location
        location_map = {
            'path': 'path',
            'query': 'query',
            'header': 'header',
        }
        location = location_map.get(param_in, 'query')

        # Create mapping
        mapping = {
            'tool_param_name': param_name.replace('-', '_').replace('.', '_').lower(),
            'api_param_name': param_name,
            'location': location,
            'required': param_required,
        }

        if param_desc:
            mapping['description'] = param_desc

        # Add default for common path parameters
        if location == 'path' and not param_required:
            if 'system' in param_name.lower():
                mapping['default'] = 'System.Embedded.1'
            elif 'manager' in param_name.lower():
                mapping['default'] = 'iDRAC.Embedded.1'

        mappings.append(mapping)

    # Add body parameter if request body exists
    request_body = operation_spec.get('requestBody')
    if request_body:
        body_required = request_body.get('required', False)
        body_desc = request_body.get('description', 'Request body data')

        mappings.append({
            'tool_param_name': 'request_body',
            'api_param_name': 'body',
            'location': 'body',
            'required': body_required,
            'description': body_desc,
        })

    return mappings


def generate_tools_reference():
    """Generate the tools_reference.yaml file."""
    print("Loading OpenAPI specification...")

    openapi_file = Path("config/openapi.yaml")
    if not openapi_file.exists():
        print(f"Error: {openapi_file} not found!")
        return

    with open(openapi_file, 'r', encoding='utf-8') as f:
        spec = yaml.safe_load(f)

    paths = spec.get('paths', {})
    print(f"Found {len(paths)} paths in OpenAPI spec")

    # Categorize operations
    categorized_tools = {}
    total_operations = 0

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue

        # Parse each HTTP method for this path
        for method in ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']:
            if method not in path_item:
                continue

            operation_spec = path_item[method]
            total_operations += 1

            # Get operation details
            operation_id = operation_spec.get('operationId', f"{method}_{path}")
            tags = operation_spec.get('tags', [])
            if isinstance(tags, str):
                tags = [tags]

            # Categorize
            category = categorize_operation(path, method, operation_id, tags)

            if category not in categorized_tools:
                categorized_tools[category] = []

            # Generate tool definition
            tool_name = generate_tool_name(operation_id, path, method)

            # Get description
            description = operation_spec.get('summary') or operation_spec.get('description') or f"{method.upper()} {path}"
            if len(description) > 200:
                description = description[:197] + "..."

            # Extract parameter mappings
            parameter_mappings = extract_parameter_mappings(operation_spec)

            tool_def = {
                'name': tool_name,
                'description': description,
                'operation_id': operation_id,
                'enabled': False,  # Disabled by default
                'category': category,
            }

            if parameter_mappings:
                tool_def['parameter_mappings'] = parameter_mappings

            categorized_tools[category].append(tool_def)

    print(f"Processed {total_operations} operations")

    # Build final YAML structure
    tools_config = {
        'version': '1.0',
        'server': {
            'base_url': 'https://idrac_ip',
            'verify_ssl': True,
            'timeout': 30,
            'max_retries': 3,
        },
        'authentication': {
            'method': 'basic',
            'token_header': 'X-Auth-Token',
        },
    }

    # Category metadata for headers
    category_descriptions = {
        'system_management': 'System and Computer Management Operations',
        'bios_configuration': 'BIOS Configuration and Settings',
        'hardware_inventory': 'Hardware Inventory (Memory, Processors, etc.)',
        'network_configuration': 'Network and Ethernet Interface Configuration',
        'storage_management': 'Storage Controllers and Drives',
        'power_thermal': 'Power and Thermal Management',
        'manager_operations': 'iDRAC Manager Operations',
        'chassis_management': 'Chassis and Physical Components',
        'account_management': 'User Account Management',
        'session_management': 'Session Management',
        'security': 'Security and Certificates',
        'logging': 'Event Logs and Log Services',
        'firmware_update': 'Firmware Updates and Inventory',
        'task_management': 'Task and Job Management',
        'virtual_media': 'Virtual Media Operations',
        'other': 'Other Operations',
    }

    # Add tools organized by category with metadata
    category_order = [
        'system_management',
        'bios_configuration',
        'hardware_inventory',
        'network_configuration',
        'storage_management',
        'power_thermal',
        'manager_operations',
        'chassis_management',
        'account_management',
        'session_management',
        'security',
        'logging',
        'firmware_update',
        'task_management',
        'virtual_media',
        'other',
    ]

    # Store tools by category for custom formatting
    tools_by_category = {}
    for category in category_order:
        if category in categorized_tools:
            tools_by_category[category] = categorized_tools[category]

    # Add any remaining categories
    for category, tools in categorized_tools.items():
        if category not in category_order:
            tools_by_category[category] = tools

    # Write to file
    output_file = Path("config/tools_reference.yaml")

    # Count total tools
    total_tools = sum(len(tools) for tools in tools_by_category.values())
    print(f"\nWriting {total_tools} tool definitions to {output_file}...")

    with open(output_file, 'w', encoding='utf-8') as f:
        # Write header comment
        f.write("# Dell iDRAC Redfish API - Complete Tools Reference\n")
        f.write("#\n")
        f.write("# This file contains ALL operations available in the OpenAPI specification.\n")
        f.write("# All tools are disabled by default (enabled: false).\n")
        f.write("#\n")
        f.write("# To use a tool:\n")
        f.write("#   1. Copy the tool definition to config/tools.yaml\n")
        f.write("#   2. Set 'enabled: true'\n")
        f.write("#   3. Adjust parameter mappings as needed\n")
        f.write("#\n")
        f.write(f"# Total operations: {total_tools}\n")
        f.write("#\n")

        # Count by category
        f.write("# Operations by category:\n")
        for category in category_order:
            if category in tools_by_category:
                count = len(tools_by_category[category])
                desc = category_descriptions.get(category, category)
                f.write(f"#   - {category}: {count} ({desc})\n")
        f.write("#\n\n")

        # Write server configuration
        f.write("version: '1.0'\n\n")
        f.write("server:\n")
        f.write("  base_url: https://idrac_ip\n")
        f.write("  verify_ssl: true\n")
        f.write("  timeout: 30\n")
        f.write("  max_retries: 3\n\n")
        f.write("authentication:\n")
        f.write("  method: basic\n")
        f.write("  token_header: X-Auth-Token\n\n")

        # Write tools section
        f.write("tools:\n")

        # Write tools by category with headers
        for category in category_order:
            if category not in tools_by_category:
                continue

            tools = tools_by_category[category]
            if not tools:
                continue

            # Write category header
            f.write("\n")
            f.write(f"  # {'=' * 78}\n")
            f.write(f"  # {category_descriptions.get(category, category).upper()}\n")
            f.write(f"  # Category: {category}\n")
            f.write(f"  # Tools: {len(tools)}\n")
            f.write(f"  # {'=' * 78}\n")
            f.write("\n")

            # Write each tool in the category
            for i, tool in enumerate(tools):
                # Write tool definition
                f.write(f"  - name: {tool['name']}\n")
                f.write(f"    description: {tool['description']}\n")
                f.write(f"    operation_id: {tool['operation_id']}\n")
                f.write(f"    enabled: {str(tool['enabled']).lower()}\n")
                f.write(f"    category: {tool['category']}\n")

                # Write parameter mappings if present
                if 'parameter_mappings' in tool and tool['parameter_mappings']:
                    f.write("    parameter_mappings:\n")
                    for mapping in tool['parameter_mappings']:
                        f.write(f"      - tool_param_name: {mapping['tool_param_name']}\n")
                        f.write(f"        api_param_name: {mapping['api_param_name']}\n")
                        f.write(f"        location: {mapping['location']}\n")
                        f.write(f"        required: {str(mapping['required']).lower()}\n")
                        if 'description' in mapping:
                            f.write(f"        description: {mapping['description']}\n")
                        if 'default' in mapping:
                            f.write(f"        default: {mapping['default']}\n")

                # Add blank line between tools (except for the last one in category)
                if i < len(tools) - 1:
                    f.write("\n")

    print(f"\n✓ Successfully generated {output_file}")
    print(f"\nSummary:")
    print(f"  Total tools: {total_tools}")
    print(f"\nTools by category:")
    for category in category_order:
        if category in tools_by_category:
            count = len(tools_by_category[category])
            print(f"  {category:25s}: {count:3d}")


if __name__ == "__main__":
    try:
        generate_tools_reference()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
