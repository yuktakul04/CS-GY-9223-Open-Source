"""Tests for ai_client_api.tool_schema.make_tool."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from ai_client_api.tool_schema import make_tool


class _WeatherArgs(BaseModel):
    city: str
    units: str = "metric"


class _EmptyArgs(BaseModel):
    pass


def test_make_tool_produces_openai_tool_dict() -> None:
    """``make_tool`` returns a dict with type, name, description, and parameters."""
    tool = make_tool("get_weather", "Get weather for a city.", _WeatherArgs)

    assert tool["type"] == "function"
    fn = tool["function"]
    assert fn["name"] == "get_weather"
    assert fn["description"] == "Get weather for a city."


def test_make_tool_schema_includes_required_fields() -> None:
    """Required Pydantic fields appear in the ``required`` list."""
    tool = make_tool("get_weather", "desc", _WeatherArgs)
    params: dict[str, Any] = tool["function"]["parameters"]

    assert params["type"] == "object"
    assert "city" in params["properties"]
    assert "required" in params
    assert "city" in params["required"]
    assert "units" not in params.get("required", [])


def test_make_tool_strips_title_from_schema() -> None:
    """The top-level ``title`` Pydantic adds is removed from the parameters."""
    tool = make_tool("get_weather", "desc", _WeatherArgs)
    params = tool["function"]["parameters"]

    assert "title" not in params


def test_make_tool_empty_model_produces_valid_schema() -> None:
    """A model with no fields still produces a valid tool dict."""
    tool = make_tool("no_args_tool", "No args needed.", _EmptyArgs)

    assert tool["function"]["name"] == "no_args_tool"
    params: dict[str, Any] = tool["function"]["parameters"]
    assert params["type"] == "object"
    assert params.get("required", []) == []


def test_make_tool_schema_is_consistent_with_model_json_schema() -> None:
    """Parameters match model_json_schema() minus the title key."""
    expected = _WeatherArgs.model_json_schema()
    expected.pop("title", None)

    tool = make_tool("get_weather", "desc", _WeatherArgs)

    assert tool["function"]["parameters"] == expected


@pytest.mark.parametrize(
    ("name", "description"),
    [
        ("tool_a", "First tool"),
        ("tool_b", "Second tool"),
    ],
)
def test_make_tool_uses_provided_name_and_description(
    name: str,
    description: str,
) -> None:
    """The ``name`` and ``description`` arguments are reflected in the output."""
    tool = make_tool(name, description, _EmptyArgs)

    assert tool["function"]["name"] == name
    assert tool["function"]["description"] == description
