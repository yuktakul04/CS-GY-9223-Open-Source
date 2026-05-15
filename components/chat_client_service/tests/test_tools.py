"""Tests for chat_client_service.tools — Pydantic models and tool list."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from chat_client_service.tools import (
    TOOLS,
    CreateIssueArgs,
    GetIssuesArgs,
    GetMessagesArgs,
    SendMessageArgs,
    ToolCallValidationError,
    UpdateIssueArgs,
    validate_tool_args,
)


def test_tools_list_contains_all_expected_tools() -> None:
    """Every chat and issue-tracker tool name is present in TOOLS."""
    names = {t["function"]["name"] for t in TOOLS}
    expected = {
        "get_messages",
        "get_message",
        "send_message",
        "delete_message",
        "get_channels",
        "get_channel",
        "get_boards",
        "get_issues",
        "create_issue",
        "update_issue",
        "delete_issue",
        "create_board",
    }
    assert names == expected


def test_each_tool_has_function_type() -> None:
    """Every entry in TOOLS has ``type == 'function'``."""
    for tool in TOOLS:
        assert tool["type"] == "function"


def test_each_tool_has_non_empty_description() -> None:
    """Every tool carries a non-empty description string."""
    for tool in TOOLS:
        fn = tool["function"]
        assert isinstance(fn["description"], str)
        assert fn["description"]


def test_get_messages_args_accepts_valid_input() -> None:
    """Valid args parse without error; defaults are applied."""
    validated = GetMessagesArgs.model_validate({"channel_id": "ch-1", "limit": 5})

    assert validated.channel_id == "ch-1"
    assert validated.limit == 5
    assert validated.cursor is None


def test_get_messages_args_applies_default_limit() -> None:
    """``limit`` defaults to 10 when omitted."""
    validated = GetMessagesArgs.model_validate({"channel_id": "ch-1"})

    assert validated.limit == 10


def test_get_messages_args_rejects_missing_channel_id() -> None:
    """Missing required ``channel_id`` raises ``ValidationError``."""
    with pytest.raises(ValidationError):
        GetMessagesArgs.model_validate({"limit": 5})


def test_create_issue_args_defaults_status_to_to_do() -> None:
    """``status`` defaults to ``'to_do'`` when omitted."""
    validated = CreateIssueArgs.model_validate({"title": "Bug", "board_id": "b-1"})

    assert validated.status == "to_do"


def test_create_issue_args_rejects_invalid_status() -> None:
    """An out-of-range ``status`` value raises ``ValidationError``."""
    with pytest.raises(ValidationError):
        CreateIssueArgs.model_validate(
            {"title": "Bug", "board_id": "b-1", "status": "invalid"}
        )


def test_update_issue_args_all_fields_optional_except_issue_id() -> None:
    """Only ``issue_id`` is required; all other fields default to None."""
    validated = UpdateIssueArgs.model_validate({"issue_id": "i-1"})

    assert validated.issue_id == "i-1"
    assert validated.title is None
    assert validated.desc is None
    assert validated.status is None


def test_send_message_args_channel_id_is_optional() -> None:
    """``channel_id`` is optional; only ``text`` is required."""
    validated = SendMessageArgs.model_validate({"text": "Hello"})

    assert validated.text == "Hello"
    assert validated.channel_id is None


def test_validate_tool_args_returns_validated_model() -> None:
    """Happy-path: ``validate_tool_args`` returns the parsed model instance."""
    result = validate_tool_args("get_issues", GetIssuesArgs, {"board_id": "b-99"})

    assert result.board_id == "b-99"


def test_validate_tool_args_raises_tool_call_validation_error_on_bad_args() -> None:
    """Missing required fields raise ``ToolCallValidationError``."""
    with pytest.raises(ToolCallValidationError) as exc_info:
        validate_tool_args("get_issues", GetIssuesArgs, {})

    assert exc_info.value.tool_name == "get_issues"
    assert "board_id" in str(exc_info.value)


def test_tool_call_validation_error_is_value_error() -> None:
    """``ToolCallValidationError`` is a subclass of ``ValueError``."""
    with pytest.raises(ValueError):  # noqa: PT011
        validate_tool_args("get_issues", GetIssuesArgs, {})


def test_tool_call_validation_error_exposes_cause() -> None:
    """The ``cause`` attribute holds the original ``ValidationError``."""
    from pydantic import ValidationError as PydanticValidationError

    exc: ToolCallValidationError | None = None
    try:
        validate_tool_args("get_issues", GetIssuesArgs, {})
    except ToolCallValidationError as e:
        exc = e

    assert exc is not None
    assert isinstance(exc.cause, PydanticValidationError)
