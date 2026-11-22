"""Day 73: two side-effect-free, permission-controlled AI tools."""

from copy import deepcopy
import math
import re


class ToolExecutionError(ValueError):
    """A requested tool or its arguments are not permitted."""


_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "calculate_average",
            "description": "Calculate the arithmetic mean of up to 20 numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "numbers": {
                        "type": "array", "items": {"type": "number"},
                        "minItems": 1, "maxItems": 20,
                    }
                },
                "required": ["numbers"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "inspect_text",
            "description": "Count words, lines and characters in supplied text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "minLength": 1, "maxLength": 4000}
                },
                "required": ["text"],
                "additionalProperties": False,
            },
        },
    },
]


def tool_definitions() -> list[dict]:
    """Return Ollama-compatible schemas without exposing internal state."""
    return deepcopy(_TOOL_DEFINITIONS)


def run_tool(name: str, arguments: dict) -> dict:
    """Execute only two permitted, read-only operations."""
    if not isinstance(arguments, dict):
        raise ToolExecutionError("Tool arguments must be an object")

    if name == "calculate_average":
        if set(arguments) != {"numbers"}:
            raise ToolExecutionError("Expected only the numbers field")
        values = arguments["numbers"]
        if not isinstance(values, list) or not 1 <= len(values) <= 20:
            raise ToolExecutionError("Provide between 1 and 20 numbers")
        for value in values:
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or abs(value) > 1_000_000):
                raise ToolExecutionError("Numbers must be finite and within limits")
        return {
            "tool": name,
            "count": len(values),
            "average": round(sum(values) / len(values), 4),
        }

    if name == "inspect_text":
        if set(arguments) != {"text"}:
            raise ToolExecutionError("Expected only the text field")
        content = arguments["text"]
        if not isinstance(content, str) or not content.strip() or len(content) > 4000:
            raise ToolExecutionError("Text must contain 1 to 4000 characters")
        return {
            "tool": name,
            "word_count": len(re.findall(r"\b[\w'-]+\b", content)),
            "line_count": len(content.splitlines()),
            "character_count": len(content),
        }

    raise ToolExecutionError("Tool not permitted")
