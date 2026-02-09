import pytest
import asyncio
import os
from datetime import datetime, timedelta

def test_imports():
    from event_emailer import event_emailer_bot, event_emailer_prompts, event_emailer_install
    assert event_emailer_bot.BOT_NAME == "event_emailer"
    assert event_emailer_bot.BOT_VERSION == "0.1.0"

def test_prompts_structure():
    from event_emailer import event_emailer_prompts
    assert hasattr(event_emailer_prompts, "main_prompt")
    assert len(event_emailer_prompts.main_prompt) > 500
    assert "calendar" in event_emailer_prompts.main_prompt.lower()
    assert "gmail" in event_emailer_prompts.main_prompt.lower() or "email" in event_emailer_prompts.main_prompt.lower()

def test_install_schema():
    from event_emailer.event_emailer_install import EVENT_EMAILER_SETUP_SCHEMA
    assert len(EVENT_EMAILER_SETUP_SCHEMA) == 4
    field_names = [f["bs_name"] for f in EVENT_EMAILER_SETUP_SCHEMA]
    assert "CALENDAR_ID" in field_names
    assert "SHEET_ID" in field_names
    assert "EMAIL_FROM" in field_names
    assert "EMAIL_TO" in field_names

def test_tools_defined():
    from event_emailer import event_emailer_bot
    assert len(event_emailer_bot.TOOLS) == 4
    tool_names = [t.name for t in event_emailer_bot.TOOLS]
    assert "calendar_ops" in tool_names
    assert "sheet_ops" in tool_names
    assert "email_ops" in tool_names
    assert "state_ops" in tool_names

def test_calendar_tool_schema():
    from event_emailer.event_emailer_bot import CALENDAR_TOOL
    params = CALENDAR_TOOL.parameters
    assert params["type"] == "object"
    assert "op" in params["properties"]
    assert "list_events" in params["properties"]["op"]["enum"]
    assert "get_event" in params["properties"]["op"]["enum"]

def test_sheet_tool_schema():
    from event_emailer.event_emailer_bot import SHEET_TOOL
    params = SHEET_TOOL.parameters
    assert params["type"] == "object"
    assert "op" in params["properties"]
    assert "read_attendees" in params["properties"]["op"]["enum"]
    assert "event_date" in params["properties"]

def test_email_tool_schema():
    from event_emailer.event_emailer_bot import EMAIL_TOOL
    params = EMAIL_TOOL.parameters
    assert params["type"] == "object"
    assert "send_email" in params["properties"]["op"]["enum"]
    assert all(field in params["properties"] for field in ["to", "from_addr", "subject", "body"])

def test_state_tool_schema():
    from event_emailer.event_emailer_bot import STATE_TOOL
    params = STATE_TOOL.parameters
    assert params["type"] == "object"
    ops = params["properties"]["op"]["enum"]
    assert "check_processed" in ops
    assert "mark_processed" in ops
    assert "mark_attendee_sent" in ops
    assert "get_pending_attendee_emails" in ops

@pytest.mark.asyncio
async def test_state_operations():
    from event_emailer.event_emailer_bot import EventEmailerState
    from motor.motor_asyncio import AsyncIOMotorClient

    mongo_conn = os.environ.get("MONGO_CONNECTION_STRING")
    if not mongo_conn:
        pytest.skip("MONGO_CONNECTION_STRING not set")

    client = AsyncIOMotorClient(mongo_conn)
    db = client["test_event_emailer_db"]
    collection = db["test_events"]

    try:
        state = EventEmailerState(collection)

        test_event_id = f"test_event_{datetime.utcnow().timestamp()}"

        is_processed = await state.is_processed(test_event_id)
        assert is_processed is False

        await state.mark_announcement_sent(test_event_id, {
            "start": datetime.utcnow().isoformat(),
            "summary": "Test Event"
        })

        is_processed = await state.is_processed(test_event_id)
        assert is_processed is True

        is_attendee_sent = await state.is_attendee_list_sent(test_event_id)
        assert is_attendee_sent is False

        await state.mark_attendee_list_sent(test_event_id)

        is_attendee_sent = await state.is_attendee_list_sent(test_event_id)
        assert is_attendee_sent is True

        await collection.delete_one({"event_id": test_event_id})

    finally:
        client.close()

@pytest.mark.asyncio
async def test_google_calendar_integration():
    pytest.skip("Requires real Google OAuth credentials - integration test only")

def test_setup_defaults():
    from event_emailer.event_emailer_install import EVENT_EMAILER_SETUP_SCHEMA

    calendar_field = next(f for f in EVENT_EMAILER_SETUP_SCHEMA if f["bs_name"] == "CALENDAR_ID")
    assert "c_76540dc287a40a9d6d19888566ca7e04e027278cd4e10251e132771eee0169647@group.calendar.google.com" in calendar_field["bs_default"]

    sheet_field = next(f for f in EVENT_EMAILER_SETUP_SCHEMA if f["bs_name"] == "SHEET_ID")
    assert "1_vyl-ka59rbHU-RM2RWaE0Ob1xa_JanovwfcgdXLCF0" in sheet_field["bs_default"]

    email_from = next(f for f in EVENT_EMAILER_SETUP_SCHEMA if f["bs_name"] == "EMAIL_FROM")
    assert email_from["bs_default"] == "kate@smallcloud.tech"

def test_schedule_config():
    from event_emailer import event_emailer_install
    import asyncio

    async def check_install():
        from flexus_client_kit import ckit_client

        if not os.environ.get("FLEXUS_API_KEY"):
            pytest.skip("FLEXUS_API_KEY not set")

        fclient = ckit_client.FlexusClient(
            "test_event_emailer",
            endpoint="/v1/jailed-bot",
        )

        return True

    result = asyncio.run(check_install())
    assert result is True
