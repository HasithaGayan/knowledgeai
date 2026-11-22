"""Day 73: strict tests for application-controlled tools."""

import math
import pytest
from backend.safe_tools import (
    ToolExecutionError, run_tool, tool_definitions,
)


def test_approved_tool_names():
    names = [x["function"]["name"] for x in tool_definitions()]
    assert names == ["calculate_average", "inspect_text"]


def test_calculate_average():
    result = run_tool("calculate_average", {"numbers": [75, 85, 95]})
    assert result == {"tool": "calculate_average", "count": 3, "average": 85.0}


def test_calculate_decimal_average():
    assert run_tool("calculate_average", {"numbers": [1.5, 2.5]})["average"] == 2.0


@pytest.mark.parametrize("args", [
    {"numbers": []},
    {"numbers": [True, 4]},
    {"numbers": ["2", 3]},
    {"numbers": [math.nan]},
    {"numbers": [math.inf]},
    {"numbers": [1] * 21},
    {"numbers": [1_000_001]},
    {"numbers": [1], "execute": True},
])
def test_invalid_average_arguments(args):
    with pytest.raises(ToolExecutionError):
        run_tool("calculate_average", args)


def test_inspect_text():
    result = run_tool("inspect_text", {"text": "Hello world\nSecond line"})
    assert result["word_count"] == 4
    assert result["line_count"] == 2
    assert result["character_count"] == len("Hello world\nSecond line")


@pytest.mark.parametrize("args", [
    {"text": "   "},
    {"text": "x" * 4001},
    {"text": 123},
    {"text": "Hello", "path": "C:/secret.txt"},
])
def test_invalid_text_arguments(args):
    with pytest.raises(ToolExecutionError):
        run_tool("inspect_text", args)


def test_unapproved_tool_blocked():
    with pytest.raises(ToolExecutionError, match="not permitted"):
        run_tool("delete_files", {"path": "C:/"})


def test_non_object_arguments_blocked():
    with pytest.raises(ToolExecutionError):
        run_tool("inspect_text", "hello")


def test_tool_schema_cannot_be_mutated():
    one = tool_definitions()
    one[0]["function"]["name"] = "bad"
    assert tool_definitions()[0]["function"]["name"] == "calculate_average"
