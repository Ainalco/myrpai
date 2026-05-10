"""
Unified variable substitution service for all components.

Handles {{variable_name}} substitution in component prompts and configurations
with support for field-level and component-level variable references.
"""

import re
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def substitute_variables(
    text: str,
    input_data: Dict[str, Any],
    component_outputs: Optional[Dict[str, Any]] = None,
    component_name: str = "Unknown"
) -> str:
    """
    Substitute {{variable}} placeholders with actual values from execution data.

    Supports two types of variable references:
    1. Field-level: {{Pain Points}}, {{summary}}, {{participants}}
    2. Component-level: {{component:ComponentName}} (requires component_outputs)

    Args:
        text: Template string containing {{variable}} placeholders
        input_data: Runtime execution data with extracted_information and other fields
        component_outputs: Optional dict of component outputs for {{component:Name}} syntax
        component_name: Name of component requesting substitution (for logging)

    Returns:
        Text with variables substituted. Missing variables are left unchanged.

    Examples:
        >>> data = {"extracted_information": {"Pain Points": ["Cost", "Time"]}}
        >>> substitute_variables("Issues: {{Pain Points}}", data)
        "Issues: Cost, Time"

        >>> data = {"summary": "Call summary"}
        >>> substitute_variables("Summary: {{summary}}", data)
        "Summary: Call summary"
    """
    if not text:
        return text

    pattern = r'\{\{([^}]+)\}\}'
    substitution_count = 0
    missing_variables = []

    def replace_variable(match):
        nonlocal substitution_count, missing_variables

        var_reference = match.group(1).strip()

        # Handle component-level references: {{component:ComponentName}}
        if var_reference.lower().startswith("component:"):
            component_ref = var_reference[10:].strip()  # Remove "component:" prefix

            if component_outputs and component_ref in component_outputs:
                value = component_outputs[component_ref]

                # Convert complex objects to JSON string
                if isinstance(value, (dict, list)):
                    result = json.dumps(value, indent=2)
                else:
                    result = str(value)

                logger.info(
                    f"[{component_name}] Component-level substitution: "
                    f"'{{{{component:{component_ref}}}}}' -> (component output)"
                )
                substitution_count += 1
                return result
            else:
                logger.warning(
                    f"[{component_name}] Component not found: '{component_ref}'. "
                    f"Available components: {list(component_outputs.keys()) if component_outputs else []}"
                )
                missing_variables.append(f"component:{component_ref}")
                return match.group(0)  # Keep original placeholder

        # Field-level variable lookup (case-insensitive with flexible matching)
        value = find_variable_value(var_reference, input_data)

        if value is not None:
            # Format the value based on type
            formatted_value = format_variable_value(value)

            # Log the substitution (truncate long values for readability)
            truncated_value = formatted_value[:100] + '...' if len(formatted_value) > 100 else formatted_value
            logger.debug(
                f"[{component_name}] Variable substitution: '{{{{{var_reference}}}}}' = '{truncated_value}'"
            )
            substitution_count += 1
            return formatted_value
        else:
            logger.warning(
                f"[{component_name}] Variable not found: '{var_reference}'. "
                f"Leaving placeholder unchanged."
            )
            missing_variables.append(var_reference)
            return match.group(0)  # Keep original placeholder

    # Perform substitution
    result = re.sub(pattern, replace_variable, text)

    # Log summary
    if substitution_count > 0 or missing_variables:
        logger.info(
            f"[{component_name}] Variable substitution complete: "
            f"{substitution_count} substituted, {len(missing_variables)} missing"
        )
        if missing_variables:
            logger.info(f"[{component_name}] Missing variables: {missing_variables}")

    return result


def find_variable_value(var_name: str, input_data: Dict[str, Any]) -> Optional[Any]:
    """
    Find variable value in input_data with flexible, case-insensitive matching.

    Searches in this order:
    1. extracted_information dict (for variables from Text Generation)
    2. Top-level input_data fields (for summary, participants, etc.)

    Args:
        var_name: Variable name to find (e.g., "Pain Points", "summary")
        input_data: Runtime execution data

    Returns:
        Variable value if found, None otherwise
    """
    # Normalize the search key (lowercase, replace spaces/underscores)
    normalized_search = normalize_key(var_name)

    # 1. Check extracted_information first (highest priority)
    extracted_info = input_data.get("extracted_information", {})
    if isinstance(extracted_info, dict):
        for key, value in extracted_info.items():
            if normalize_key(key) == normalized_search:
                return value

    # 2. Check top-level input_data (excluding complex objects and metadata)
    excluded_keys = {"extracted_information", "__component_outputs__", "input_data"}
    for key, value in input_data.items():
        if key in excluded_keys:
            continue

        # Skip dict values at top level (except for simple dicts)
        if isinstance(value, dict) and len(value) > 10:
            continue

        if normalize_key(key) == normalized_search:
            return value

    return None


def normalize_key(key: str) -> str:
    """
    Normalize a key for case-insensitive comparison.

    Converts to lowercase and replaces spaces/underscores with nothing
    to allow flexible matching.

    Examples:
        "Pain Points" -> "painpoints"
        "pain_points" -> "painpoints"
        "PainPoints" -> "painpoints"
    """
    return key.lower().replace(" ", "").replace("_", "").replace("-", "")


def format_variable_value(value: Any) -> str:
    """
    Format a variable value for substitution into text.

    Handles different data types appropriately:
    - Lists: Join with comma
    - Dicts: Convert to JSON
    - Booleans: "Yes"/"No"
    - None: "[Not Available]"
    - Strings/numbers: Direct conversion

    Args:
        value: The value to format

    Returns:
        Formatted string representation
    """
    if value is None:
        return "[Not Available]"

    if isinstance(value, bool):
        return "Yes" if value else "No"

    if isinstance(value, list):
        # Handle list of strings
        if all(isinstance(item, str) for item in value):
            return ", ".join(value)
        # Handle list of other types
        return ", ".join(str(item) for item in value)

    if isinstance(value, dict):
        # Convert dict to readable JSON
        return json.dumps(value, indent=2)

    # Handle transcript truncation (special case for long text)
    if isinstance(value, str) and len(value) > 8000:
        return value[:8000] + "... [truncated]"

    return str(value)


def log_available_variables(input_data: Dict[str, Any], component_name: str = "Component"):
    """
    Log all available variables for debugging purposes.

    Useful for troubleshooting when users can't figure out what variables are available.

    Args:
        input_data: Runtime execution data
        component_name: Name of component (for logging context)
    """
    variables = []

    # From extracted_information
    extracted_info = input_data.get("extracted_information", {})
    if isinstance(extracted_info, dict):
        for key in extracted_info.keys():
            variables.append(f"{{{{{{{{}}}}}}}} (from extracted_information)".format(key))

    # From top-level
    excluded_keys = {"extracted_information", "__component_outputs__", "input_data"}
    for key in input_data.keys():
        if key not in excluded_keys and not isinstance(input_data[key], dict):
            variables.append(f"{{{{{{{{}}}}}}}} (from input data)".format(key))

    # From component outputs
    component_outputs = input_data.get("__component_outputs__", {})
    if isinstance(component_outputs, dict):
        for key in component_outputs.keys():
            variables.append(f"{{{{component:{key}}}}} (component output)")

    if variables:
        logger.info(f"[{component_name}] Available variables: {', '.join(variables[:10])}")
        if len(variables) > 10:
            logger.info(f"[{component_name}] ... and {len(variables) - 10} more")
    else:
        logger.warning(f"[{component_name}] No variables available in input_data")
