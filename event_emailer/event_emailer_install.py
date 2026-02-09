import asyncio
import json
from flexus_client_kit import ckit_bot_install, ckit_client
from flexus_client_kit.ckit_bot_install import FMarketplaceExpertInput

BOT_NAME = "event_emailer"
BOT_VERSION = "0.1.0"

EVENT_EMAILER_SETUP_SCHEMA = [
    {
        "bs_name": "CALENDAR_ID",
        "bs_type": "string_long",
        "bs_default": "c_76540dc287a40a9d6d19888566ca7e04e027278cd4e10251e132771eee0169647@group.calendar.google.com",
        "bs_group": "Calendar",
        "bs_description": "Google Calendar ID to monitor for events",
    },
    {
        "bs_name": "SHEET_ID",
        "bs_type": "string_long",
        "bs_default": "1_vyl-ka59rbHU-RM2RWaE0Ob1xa_JanovwfcgdXLCF0",
        "bs_group": "Attendees",
        "bs_description": "Google Sheet ID containing attendee registrations",
    },
    {
        "bs_name": "EMAIL_FROM",
        "bs_type": "string_short",
        "bs_default": "kate@smallcloud.tech",
        "bs_group": "Email",
        "bs_description": "From address for emails",
    },
    {
        "bs_name": "EMAIL_TO",
        "bs_type": "string_short",
        "bs_default": "kate@smallcloud.tech",
        "bs_group": "Email",
        "bs_description": "To address for emails",
    },
]

async def install():
    from event_emailer import event_emailer_prompts
    from event_emailer import event_emailer_bot

    fclient = ckit_client.FlexusClient(
        ckit_client.bot_service_name(BOT_NAME, BOT_VERSION),
        endpoint="/v1/jailed-bot",
    )

    await ckit_bot_install.marketplace_upsert_dev_bot(
        fclient,
        marketable_name=BOT_NAME,
        marketable_version_str=BOT_VERSION,
        marketable_title="Event Emailer",
        marketable_description="Automates email communication for calendar events. Sends event announcements and pre-event attendee lists.",
        marketable_setup_default=EVENT_EMAILER_SETUP_SCHEMA,
        marketable_preferred_model_default="grok-4-1-fast-non-reasoning",
        marketable_experts=[
            ("default", FMarketplaceExpertInput(
                fexp_system_prompt=event_emailer_prompts.main_prompt,
                fexp_python_kernel="",
                fexp_app_capture_tools=json.dumps([t.openai_style_tool() for t in event_emailer_bot.TOOLS]),
            )),
        ],
        marketable_schedule=[
            {
                "sched_type": "SCHED_ANY",
                "sched_when": "EVERY:5m",
                "sched_first_question": "Check for new events and send announcement emails. Check for events needing attendee lists in 75-85 minutes.",
                "sched_fexp_name": "default",
            },
        ],
    )

    print(f"✅ {BOT_NAME} v{BOT_VERSION} installed successfully")

if __name__ == "__main__":
    asyncio.run(install())
