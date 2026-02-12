import pytest
import json


def test_imports():
    from event_emailer import event_emailer_bot, event_emailer_prompts, event_emailer_install, event_emailer_tools


def test_bot_structure():
    from event_emailer import event_emailer_bot

    assert event_emailer_bot.BOT_NAME == "event_emailer"
    assert event_emailer_bot.BOT_VERSION == "0.2.1"
    assert len(event_emailer_bot.TOOLS) == 4
    assert hasattr(event_emailer_bot, 'main')
    assert hasattr(event_emailer_bot, 'bot_main_loop')


def test_tools_definition():
    from event_emailer import event_emailer_tools

    assert len(event_emailer_tools.TOOLS) == 4

    tool_names = {tool.name for tool in event_emailer_tools.TOOLS}
    assert "calendar_ops" in tool_names
    assert "sheet_ops" in tool_names
    assert "email_ops" in tool_names
    assert "state_ops" in tool_names


def test_prompts_structure():
    from event_emailer import event_emailer_prompts

    assert hasattr(event_emailer_prompts, "main_prompt")
    assert len(event_emailer_prompts.main_prompt) > 100
    assert "Event Emailer" in event_emailer_prompts.main_prompt
    assert "calendar_ops" in event_emailer_prompts.main_prompt
    assert "sheet_ops" in event_emailer_prompts.main_prompt
    assert "email_ops" in event_emailer_prompts.main_prompt
    assert "state_ops" in event_emailer_prompts.main_prompt


def test_install_schema():
    from event_emailer import event_emailer_install

    assert event_emailer_install.BOT_NAME == "event_emailer"
    assert event_emailer_install.BOT_VERSION == "0.2.1"
    assert len(event_emailer_install.EVENT_EMAILER_SETUP_SCHEMA) == 4

    schema_names = {s["bs_name"] for s in event_emailer_install.EVENT_EMAILER_SETUP_SCHEMA}
    assert "CALENDAR_ID" in schema_names
    assert "SHEET_ID" in schema_names
    assert "EMAIL_FROM" in schema_names
    assert "EMAIL_TO" in schema_names


def test_tool_schemas():
    from event_emailer import event_emailer_tools

    for tool in event_emailer_tools.TOOLS:
        openai_tool = tool.openai_style_tool()
        assert openai_tool["type"] == "function"
        assert "name" in openai_tool["function"]
        assert "description" in openai_tool["function"]
        assert "parameters" in openai_tool["function"]

        params = openai_tool["function"]["parameters"]
        assert params["type"] == "object"
        assert "properties" in params
        assert "operation" in params["properties"]


@pytest.mark.asyncio
async def test_state_ops_basic():
    from event_emailer import event_emailer_tools
    from unittest.mock import AsyncMock, MagicMock

    mock_collection = AsyncMock()
    mock_collection.find_one = AsyncMock(return_value=None)

    toolcall = MagicMock()
    args = {
        "operation": "check_processed",
        "event_id": "test_event_123",
    }

    result = await event_emailer_tools.handle_state_ops(mock_collection, toolcall, args)
    result_data = json.loads(result)

    assert result_data["success"] is True
    assert result_data["processed"] is False
    mock_collection.find_one.assert_called_once_with({"event_id": "test_event_123"})
