"""Utility for generating OpenAI-style tool dicts from Pydantic models."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pydantic import BaseModel


def make_tool(
    name: str,
    description: str,
    model: type[BaseModel],
) -> dict[str, Any]:
    """Return an OpenAI-style tool dict derived from ``model``'s JSON schema."""
    schema: dict[str, Any] = model.model_json_schema()
    schema.pop("title", None)
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": schema,
        },
    }
