import asyncio
import base64
from pathlib import Path
import json
from flexus_client_kit import ckit_bot_install, ckit_client, ckit_cloudtool
from flexus_client_kit.ckit_bot_install import FMarketplaceExpertInput

BOT_NAME = "event_emailer"
BOT_VERSION = "0.2.1"

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

BOT_DESCRIPTION = """
## Event Emailer - Calendar Email Automation

Automates email communication for Google Calendar events. Monitors a calendar and sends timely notifications to keep attendees informed.

**Key Features:**
- **Event announcements**: Sends invitation emails when new events are detected
- **Attendee lists**: Sends pre-event attendee rosters 80 minutes before start time
- **Google integration**: Works with Calendar, Sheets, and Gmail APIs
- **Smart tracking**: Uses MongoDB to prevent duplicate emails

**What it does:**
1. Monitors your Google Calendar for new events
2. Generates and sends invitation emails with event details
3. Reads attendee data from Google Sheets
4. Sends attendee lists to organizers before events start

**Perfect for:**
- Event coordinators managing multiple sessions
- Community organizers tracking RSVPs
- Teams running regular meetings with external participants

The bot handles all the email busywork so you can focus on delivering great events!
"""

pic_big = base64.b64encode(open(Path(__file__).with_name("event_emailer-1024x1536.webp"), "rb").read()).decode("ascii")
pic_small = base64.b64encode(open(Path(__file__).with_name("event_emailer-256x256.webp"), "rb").read()).decode("ascii")

async def install(
    fclient: ckit_client.FlexusClient,
    ws_id: str,
    bot_name: str,
    bot_version: str,
    tools: list[ckit_cloudtool.CloudTool],
):
    from event_emailer import event_emailer_prompts
    await ckit_bot_install.marketplace_upsert_dev_bot(
        fclient,
        ws_id=ws_id,
        marketable_name=bot_name,
        marketable_version=bot_version,
        marketable_author="Flexus",
        marketable_accent_color="#4285F4",
        marketable_occupation="Event Coordinator",
        marketable_typical_group="Automation / Events",
        marketable_github_repo="https://github.com/smallcloudai/flexus-bots.git",
        marketable_run_this="python -m event_emailer.event_emailer_bot",
        marketable_featured_actions=[
            {"feat_question": "Check for new events", "feat_expert": "default", "feat_depends_on_setup": ["CALENDAR_ID"]},
            {"feat_question": "Send attendee list for upcoming event", "feat_expert": "default", "feat_depends_on_setup": ["CALENDAR_ID", "SHEET_ID"]},
        ],
        marketable_intro_message="Hello! I'm Event Emailer, your calendar automation assistant. I monitor your Google Calendar and automatically send event announcements and attendee lists. Let me know if you need help with setup or want to check on any events.",
        marketable_daily_budget_default=50_000,
        marketable_default_inbox_default=5_000,
        marketable_title1="Event Emailer",
        marketable_title2="Automates email communication for calendar events",
        marketable_description=BOT_DESCRIPTION,
        marketable_setup_default=EVENT_EMAILER_SETUP_SCHEMA,
        marketable_preferred_model_default="grok-4-1-fast-non-reasoning",
        marketable_picture_big_b64=pic_big,
        marketable_picture_small_b64=pic_small,
        marketable_experts=[
            ("default", FMarketplaceExpertInput(
                fexp_system_prompt=event_emailer_prompts.main_prompt,
                fexp_python_kernel="",
                fexp_block_tools="",
                fexp_allow_tools="",
                fexp_app_capture_tools=json.dumps([t.openai_style_tool() for t in tools]),
            )),
        ],
        marketable_schedule=[
            {
                "sched_type": "SCHED_ANY",
                "sched_when": "EVERY:72h",
                "sched_first_question": "Check for new events and send announcement emails. Check for events needing attendee lists in 75-85 minutes.",
                "sched_fexp_name": "default",
            },
        ],
    )

    print(f"✅ {bot_name} v{bot_version} installed successfully")

if __name__ == "__main__":
    from event_emailer import event_emailer_bot
    
    fclient = ckit_client.FlexusClient(
        ckit_client.bot_service_name(BOT_NAME, BOT_VERSION),
        endpoint="/v1/jailed-bot",
    )
    
    ws_id = ckit_bot_install.bot_install_argparse().ws
    
    asyncio.run(install(fclient, ws_id, BOT_NAME, BOT_VERSION, event_emailer_bot.TOOLS))
