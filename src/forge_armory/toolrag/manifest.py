"""Capability manifest template rendering for Tool RAG.

The capability manifest is a template that describes available tools.
It supports the {{TOOL_LIST}} placeholder which gets replaced with
an auto-generated list of tools grouped by backend.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from forge_armory.db.models import Tool

# Placeholder for auto-generated tool list
TOOL_LIST_PLACEHOLDER = "{{TOOL_LIST}}"

# Default template when none is configured
DEFAULT_TEMPLATE = """Search for tools to help with your task. Available capabilities include:

{{TOOL_LIST}}

Describe what you need in natural language."""


def generate_tool_list(tools: list[Tool], group_by_backend: bool = True) -> str:
    """Generate a formatted tool list from database tools.

    Args:
        tools: List of Tool objects from the database
        group_by_backend: If True, group tools by backend prefix

    Returns:
        Formatted string listing tools, e.g.:
        - mcp_weather: get_current_weather, get_forecast
        - mcp_web_search: brave_web_search, brave_local_search
    """
    if not tools:
        return "(No tools available)"

    if group_by_backend:
        # Group tools by backend prefix (extracted from prefixed_name)
        backends: dict[str, list[str]] = {}
        for tool in tools:
            # prefixed_name format: "backend__tool_name"
            if "__" in tool.prefixed_name:
                prefix, name = tool.prefixed_name.split("__", 1)
            else:
                prefix = "default"
                name = tool.prefixed_name

            if prefix not in backends:
                backends[prefix] = []
            backends[prefix].append(name)

        # Format as lines
        lines = []
        for prefix in sorted(backends.keys()):
            tool_names = sorted(backends[prefix])
            lines.append(f"- {prefix}: {', '.join(tool_names)}")

        return "\n".join(lines)
    else:
        # Simple flat list
        tool_names = sorted(t.prefixed_name for t in tools)
        return "\n".join(f"- {name}" for name in tool_names)


def render_manifest(template: str, tools: list[Tool]) -> str:
    """Render a manifest template by replacing placeholders.

    Args:
        template: Template string with {{TOOL_LIST}} placeholder
        tools: List of Tool objects to generate tool list from

    Returns:
        Rendered manifest with placeholders replaced
    """
    if not template:
        template = DEFAULT_TEMPLATE

    tool_list = generate_tool_list(tools)
    return template.replace(TOOL_LIST_PLACEHOLDER, tool_list)


def get_default_template() -> str:
    """Get the default manifest template."""
    return DEFAULT_TEMPLATE
