import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional
import base64

from motor.motor_asyncio import AsyncIOMotorClient
import google.oauth2.credentials
import googleapiclient.discovery
from googleapiclient.errors import HttpError

from flexus_client_kit import (
    ckit_bot_exec,
    ckit_client,
    ckit_cloudtool,
    ckit_external_auth,
    ckit_mongo,
    ckit_shutdown,
)

BOT_NAME = "event_emailer"
BOT_VERSION = "0.1.1"

logger = logging.getLogger(__name__)

CALENDAR_TOOL = ckit_cloudtool.CloudTool(
    strict=False,
    name="calendar_ops",
    description="Google Calendar operations for monitoring events",
    parameters={
        "type": "object",
        "properties": {
            "op": {
                "type": "string",
                "enum": ["list_events", "get_event"],
                "description": "Operation to perform",
            },
            "event_id": {
                "type": "string",
                "description": "Event ID for get_event operation",
            },
        },
        "required": ["op"],
        "additionalProperties": False,
    },
)

SHEET_TOOL = ckit_cloudtool.CloudTool(
    strict=False,
    name="sheet_ops",
    description="Google Sheets operations for reading attendee lists",
    parameters={
        "type": "object",
        "properties": {
            "op": {
                "type": "string",
                "enum": ["read_attendees"],
                "description": "Operation to perform",
            },
            "event_date": {
                "type": "string",
                "description": "Event date in YYYY-MM-DD format to match attendees",
            },
        },
        "required": ["op", "event_date"],
        "additionalProperties": False,
    },
)

EMAIL_TOOL = ckit_cloudtool.CloudTool(
    strict=False,
    name="email_ops",
    description="Gmail operations for sending emails",
    parameters={
        "type": "object",
        "properties": {
            "op": {
                "type": "string",
                "enum": ["send_email"],
                "description": "Operation to perform",
            },
            "to": {
                "type": "string",
                "description": "To email address",
            },
            "from_addr": {
                "type": "string",
                "description": "From email address",
            },
            "subject": {
                "type": "string",
                "description": "Email subject",
            },
            "body": {
                "type": "string",
                "description": "Email body (plain text)",
            },
        },
        "required": ["op", "to", "from_addr", "subject", "body"],
        "additionalProperties": False,
    },
)

STATE_TOOL = ckit_cloudtool.CloudTool(
    strict=False,
    name="state_ops",
    description="MongoDB state operations for tracking processed events",
    parameters={
        "type": "object",
        "properties": {
            "op": {
                "type": "string",
                "enum": [
                    "check_processed",
                    "mark_processed",
                    "mark_attendee_sent",
                    "get_pending_attendee_emails",
                ],
                "description": "Operation to perform",
            },
            "event_id": {
                "type": "string",
                "description": "Event ID for check/mark operations",
            },
        },
        "required": ["op"],
        "additionalProperties": False,
    },
)

TOOLS = [CALENDAR_TOOL, SHEET_TOOL, EMAIL_TOOL, STATE_TOOL]

class EventEmailerState:
    def __init__(self, mongo_collection):
        self.collection = mongo_collection

    async def is_processed(self, event_id: str) -> bool:
        doc = await self.collection.find_one({"event_id": event_id})
        return doc is not None and doc.get("announcement_sent", False)

    async def mark_announcement_sent(self, event_id: str, event_data: dict):
        await self.collection.update_one(
            {"event_id": event_id},
            {
                "$set": {
                    "event_id": event_id,
                    "announcement_sent": True,
                    "announcement_sent_at": datetime.utcnow(),
                    "event_start": event_data.get("start"),
                    "event_summary": event_data.get("summary"),
                }
            },
            upsert=True,
        )

    async def is_attendee_list_sent(self, event_id: str) -> bool:
        doc = await self.collection.find_one({"event_id": event_id})
        return doc is not None and doc.get("attendee_list_sent", False)

    async def mark_attendee_list_sent(self, event_id: str):
        await self.collection.update_one(
            {"event_id": event_id},
            {"$set": {"attendee_list_sent": True, "attendee_list_sent_at": datetime.utcnow()}},
            upsert=True,
        )

    async def get_events_needing_attendee_list(self, min_minutes: int, max_minutes: int):
        now = datetime.utcnow()
        min_time = now + timedelta(minutes=min_minutes)
        max_time = now + timedelta(minutes=max_minutes)

        cursor = self.collection.find({
            "announcement_sent": True,
            "attendee_list_sent": {"$ne": True},
            "event_start": {"$gte": min_time.isoformat(), "$lte": max_time.isoformat()},
        })

        events = []
        async for doc in cursor:
            events.append(doc)
        return events

async def get_google_service(fclient, ws_id: str, owner_fuser_id: str, service_name: str, version: str):
    token = await ckit_external_auth.get_external_auth_token(
        fclient, "google", ws_id, owner_fuser_id,
    )

    if not token:
        return None, "Not authenticated with Google. Please authorize access."

    try:
        creds = google.oauth2.credentials.Credentials(token=token.access_token)
        service = googleapiclient.discovery.build(service_name, version, credentials=creds)
        return service, None
    except Exception as e:
        logger.error(f"Failed to build Google service: {e}")
        return None, f"Error building Google service: {str(e)}"

async def handle_calendar_ops(fclient, rcx, args):
    op = args["op"]

    calendar_service, error = await get_google_service(
        fclient, rcx.persona.ws_id, rcx.persona.owner_fuser_id, "calendar", "v3"
    )

    if error:
        return error

    setup = ckit_bot_exec.official_setup_mixing_procedure(
        [], rcx.persona.persona_setup,
    )

    from event_emailer.event_emailer_install import EVENT_EMAILER_SETUP_SCHEMA
    setup = ckit_bot_exec.official_setup_mixing_procedure(
        EVENT_EMAILER_SETUP_SCHEMA, rcx.persona.persona_setup,
    )

    calendar_id = setup.get("CALENDAR_ID")

    try:
        if op == "list_events":
            now = datetime.utcnow().isoformat() + "Z"
            max_time = (datetime.utcnow() + timedelta(days=30)).isoformat() + "Z"

            events_result = calendar_service.events().list(
                calendarId=calendar_id,
                timeMin=now,
                timeMax=max_time,
                maxResults=50,
                singleEvents=True,
                orderBy="startTime",
            ).execute()

            events = events_result.get("items", [])

            if not events:
                return "No upcoming events found in the next 30 days."

            result = []
            for event in events:
                start = event.get("start", {}).get("dateTime", event.get("start", {}).get("date"))
                result.append({
                    "id": event.get("id"),
                    "summary": event.get("summary"),
                    "start": start,
                    "hangoutLink": event.get("hangoutLink"),
                    "description": event.get("description", ""),
                })

            return json.dumps(result, indent=2)

        elif op == "get_event":
            event_id = args.get("event_id")
            if not event_id:
                return "Error: event_id required for get_event"

            event = calendar_service.events().get(
                calendarId=calendar_id,
                eventId=event_id,
            ).execute()

            return json.dumps({
                "id": event.get("id"),
                "summary": event.get("summary"),
                "start": event.get("start", {}).get("dateTime", event.get("start", {}).get("date")),
                "end": event.get("end", {}).get("dateTime", event.get("end", {}).get("date")),
                "hangoutLink": event.get("hangoutLink"),
                "description": event.get("description", ""),
                "created": event.get("created"),
            }, indent=2)

    except HttpError as e:
        logger.error(f"Calendar API error: {e}")
        return f"Calendar API error: {e.resp.status} {e.error_details}"
    except Exception as e:
        logger.error(f"Error in calendar_ops: {e}")
        return f"Error: {str(e)}"

async def handle_sheet_ops(fclient, rcx, args):
    op = args["op"]

    sheets_service, error = await get_google_service(
        fclient, rcx.persona.ws_id, rcx.persona.owner_fuser_id, "sheets", "v4"
    )

    if error:
        return error

    from event_emailer.event_emailer_install import EVENT_EMAILER_SETUP_SCHEMA
    setup = ckit_bot_exec.official_setup_mixing_procedure(
        EVENT_EMAILER_SETUP_SCHEMA, rcx.persona.persona_setup,
    )

    sheet_id = setup.get("SHEET_ID")

    try:
        if op == "read_attendees":
            event_date = args.get("event_date")
            if not event_date:
                return "Error: event_date required for read_attendees"

            result = sheets_service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range="Sheet1!A:B",
            ).execute()

            rows = result.get("values", [])

            if not rows:
                return json.dumps({"attendees": [], "count": 0})

            header = rows[0] if rows else []
            email_col = None
            date_col = None

            for i, cell in enumerate(header):
                if cell.lower() == "email":
                    email_col = i
                elif "date" in cell.lower():
                    date_col = i

            if email_col is None:
                return "Error: 'email' column not found in sheet"

            attendees = set()
            for row in rows[1:]:
                if len(row) <= email_col:
                    continue

                email = row[email_col].strip()
                if not email:
                    continue

                if date_col is not None and len(row) > date_col:
                    row_date = row[date_col].strip()
                    if event_date in row_date or row_date in event_date:
                        attendees.add(email)
                else:
                    attendees.add(email)

            return json.dumps({
                "attendees": sorted(list(attendees)),
                "count": len(attendees),
                "event_date": event_date,
            }, indent=2)

    except HttpError as e:
        logger.error(f"Sheets API error: {e}")
        return f"Sheets API error: {e.resp.status} {e.error_details}"
    except Exception as e:
        logger.error(f"Error in sheet_ops: {e}")
        return f"Error: {str(e)}"

async def handle_email_ops(fclient, rcx, args):
    op = args["op"]

    gmail_service, error = await get_google_service(
        fclient, rcx.persona.ws_id, rcx.persona.owner_fuser_id, "gmail", "v1"
    )

    if error:
        return error

    try:
        if op == "send_email":
            to = args.get("to")
            from_addr = args.get("from_addr")
            subject = args.get("subject")
            body = args.get("body")

            message_text = f"From: {from_addr}\r\nTo: {to}\r\nSubject: {subject}\r\n\r\n{body}"
            message_bytes = message_text.encode("utf-8")
            message_b64 = base64.urlsafe_b64encode(message_bytes).decode("utf-8")

            message = {"raw": message_b64}

            sent_message = gmail_service.users().messages().send(
                userId="me",
                body=message,
            ).execute()

            return json.dumps({
                "status": "sent",
                "message_id": sent_message.get("id"),
                "to": to,
                "subject": subject,
            }, indent=2)

    except HttpError as e:
        logger.error(f"Gmail API error: {e}")
        return f"Gmail API error: {e.resp.status} {e.error_details}"
    except Exception as e:
        logger.error(f"Error in email_ops: {e}")
        return f"Error: {str(e)}"

async def handle_state_ops(state: EventEmailerState, args):
    op = args["op"]

    try:
        if op == "check_processed":
            event_id = args.get("event_id")
            if not event_id:
                return "Error: event_id required"

            is_processed = await state.is_processed(event_id)
            return json.dumps({
                "event_id": event_id,
                "announcement_sent": is_processed,
            })

        elif op == "mark_processed":
            event_id = args.get("event_id")
            if not event_id:
                return "Error: event_id required"

            await state.mark_announcement_sent(event_id, {})
            return json.dumps({
                "event_id": event_id,
                "status": "marked_as_processed",
            })

        elif op == "mark_attendee_sent":
            event_id = args.get("event_id")
            if not event_id:
                return "Error: event_id required"

            await state.mark_attendee_list_sent(event_id)
            return json.dumps({
                "event_id": event_id,
                "status": "attendee_list_marked_sent",
            })

        elif op == "get_pending_attendee_emails":
            events = await state.get_events_needing_attendee_list(75, 85)
            return json.dumps({
                "events": events,
                "count": len(events),
            }, indent=2, default=str)

    except Exception as e:
        logger.error(f"Error in state_ops: {e}")
        return f"Error: {str(e)}"

async def bot_main_loop(fclient, rcx):
    from event_emailer.event_emailer_install import EVENT_EMAILER_SETUP_SCHEMA

    setup = ckit_bot_exec.official_setup_mixing_procedure(
        EVENT_EMAILER_SETUP_SCHEMA, rcx.persona.persona_setup,
    )

    mongo_conn_str = await ckit_mongo.mongo_fetch_creds(fclient, rcx.persona.persona_id)
    mongo_client = AsyncIOMotorClient(mongo_conn_str, maxPoolSize=50)
    events_collection = mongo_client[rcx.persona.persona_id + "_db"]["events_state"]

    state = EventEmailerState(events_collection)

    @rcx.on_tool_call(CALENDAR_TOOL.name)
    async def toolcall_calendar(toolcall, args):
        return await handle_calendar_ops(fclient, rcx, args)

    @rcx.on_tool_call(SHEET_TOOL.name)
    async def toolcall_sheet(toolcall, args):
        return await handle_sheet_ops(fclient, rcx, args)

    @rcx.on_tool_call(EMAIL_TOOL.name)
    async def toolcall_email(toolcall, args):
        return await handle_email_ops(fclient, rcx, args)

    @rcx.on_tool_call(STATE_TOOL.name)
    async def toolcall_state(toolcall, args):
        return await handle_state_ops(state, args)

    logger.info(f"Event Emailer bot started for persona {rcx.persona.persona_id}")

    try:
        while not ckit_shutdown.shutdown_event.is_set():
            await rcx.unpark_collected_events(sleep_if_no_work=10.0)
    finally:
        await rcx.wait_for_bg_tasks()
        mongo_client.close()
        logger.info("Event Emailer bot stopped")

def main():
    fclient = ckit_client.FlexusClient(
        ckit_client.bot_service_name(BOT_NAME, BOT_VERSION),
        endpoint="/v1/jailed-bot",
    )

    from event_emailer import event_emailer_install

    scenario_fn = ckit_bot_exec.parse_bot_args()

    asyncio.run(ckit_bot_exec.run_bots_in_this_group(
        fclient,
        marketable_name=BOT_NAME,
        marketable_version_str=BOT_VERSION,
        bot_main_loop=bot_main_loop,
        inprocess_tools=TOOLS,
        scenario_fn=scenario_fn,
        install_func=event_emailer_install.install,
    ))

if __name__ == "__main__":
    main()
