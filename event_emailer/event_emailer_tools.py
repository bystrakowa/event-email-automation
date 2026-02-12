import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any
from zoneinfo import ZoneInfo

from flexus_client_kit import ckit_cloudtool, ckit_external_auth
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

logger = logging.getLogger("event_emailer_tools")

CET = ZoneInfo("Europe/Paris")

CALENDAR_OPS_TOOL = ckit_cloudtool.CloudTool(
    strict=False,
    name="calendar_ops",
    description="Google Calendar operations: list upcoming events or get specific event details",
    parameters={
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["list", "get"],
                "description": "Operation: 'list' for upcoming events, 'get' for specific event",
            },
            "time_min": {
                "type": "string",
                "description": "ISO 8601 start time for list operation",
            },
            "time_max": {
                "type": "string",
                "description": "ISO 8601 end time for list operation",
            },
            "event_id": {
                "type": "string",
                "description": "Event ID for get operation",
            },
        },
        "required": ["operation"],
    },
)

SHEET_OPS_TOOL = ckit_cloudtool.CloudTool(
    strict=False,
    name="sheet_ops",
    description="Read attendee registrations from Google Sheets for a specific date",
    parameters={
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["read"],
                "description": "Operation: 'read' to get attendees",
            },
            "date_filter": {
                "type": "string",
                "description": "ISO 8601 date to match (will compare date only, ignoring time)",
            },
        },
        "required": ["operation"],
    },
)

EMAIL_OPS_TOOL = ckit_cloudtool.CloudTool(
    strict=False,
    name="email_ops",
    description="Send emails via Gmail API",
    parameters={
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["send"],
                "description": "Operation: 'send' to send email",
            },
            "to": {
                "type": "string",
                "description": "Recipient email address",
            },
            "subject": {
                "type": "string",
                "description": "Email subject line",
            },
            "body": {
                "type": "string",
                "description": "Email body (plain text or HTML)",
            },
        },
        "required": ["operation", "to", "subject", "body"],
    },
)

STATE_OPS_TOOL = ckit_cloudtool.CloudTool(
    strict=False,
    name="state_ops",
    description="MongoDB state tracking to prevent duplicate emails",
    parameters={
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["check_processed", "mark_processed", "mark_attendee_sent", "get_pending_attendee_emails"],
                "description": "State operation",
            },
            "event_id": {
                "type": "string",
                "description": "Calendar event ID",
            },
            "event_date": {
                "type": "string",
                "description": "Event date for pending check",
            },
        },
        "required": ["operation"],
    },
)

TOOLS = [CALENDAR_OPS_TOOL, SHEET_OPS_TOOL, EMAIL_OPS_TOOL, STATE_OPS_TOOL]


async def handle_calendar_ops(fclient, rcx, setup, toolcall, args):
    operation = args.get("operation")
    calendar_id = setup.get("CALENDAR_ID")

    try:
        token = await ckit_external_auth.get_external_auth_token(
            fclient, "google", rcx.persona.ws_id, rcx.persona.owner_fuser_id,
        )

        if not token:
            return json.dumps({
                "error": "Google OAuth not configured. Please authorize Google Calendar access in settings."
            })

        creds = Credentials(token=token.access_token)
        service = build("calendar", "v3", credentials=creds)

        if operation == "list":
            time_min = args.get("time_min", datetime.now(CET).isoformat())
            time_max = args.get("time_max", (datetime.now(CET) + timedelta(days=7)).isoformat())

            events_result = service.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            ).execute()

            events = events_result.get("items", [])
            return json.dumps({
                "success": True,
                "events": events,
                "count": len(events),
            })

        elif operation == "get":
            event_id = args.get("event_id")
            if not event_id:
                return json.dumps({"error": "event_id required for get operation"})

            event = service.events().get(
                calendarId=calendar_id,
                eventId=event_id,
            ).execute()

            return json.dumps({
                "success": True,
                "event": event,
            })

        else:
            return json.dumps({"error": f"Unknown operation: {operation}"})

    except Exception as e:
        logger.exception("Calendar operation failed")
        return json.dumps({"error": str(e)})


async def handle_sheet_ops(fclient, rcx, setup, toolcall, args):
    operation = args.get("operation")
    sheet_id = setup.get("SHEET_ID")

    try:
        token = await ckit_external_auth.get_external_auth_token(
            fclient, "google", rcx.persona.ws_id, rcx.persona.owner_fuser_id,
        )

        if not token:
            return json.dumps({
                "error": "Google OAuth not configured. Please authorize Google Sheets access in settings."
            })

        creds = Credentials(token=token.access_token)
        service = build("sheets", "v4", credentials=creds)

        if operation == "read":
            result = service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range="A:Z",
            ).execute()

            rows = result.get("values", [])
            if not rows:
                return json.dumps({"success": True, "attendees": []})

            headers = [h.lower().strip() for h in rows[0]]
            email_idx = None
            date_idx = None

            for i, h in enumerate(headers):
                if "email" in h:
                    email_idx = i
                if "date" in h or "preferred" in h:
                    date_idx = i

            if email_idx is None:
                return json.dumps({"error": "No email column found in sheet"})

            date_filter = args.get("date_filter")
            filter_date = None
            if date_filter:
                try:
                    filter_date = datetime.fromisoformat(date_filter).date()
                except:
                    pass

            attendees = []
            seen_emails = set()

            for row in rows[1:]:
                if len(row) <= email_idx:
                    continue

                email = row[email_idx].strip()
                if not email or email in seen_emails:
                    continue

                if filter_date and date_idx is not None and len(row) > date_idx:
                    try:
                        row_date_str = row[date_idx].strip()
                        row_date = datetime.strptime(row_date_str, "%Y-%m-%d").date()
                        if row_date != filter_date:
                            continue
                    except:
                        continue

                attendees.append(email)
                seen_emails.add(email)

            return json.dumps({
                "success": True,
                "attendees": attendees,
                "count": len(attendees),
            })

        else:
            return json.dumps({"error": f"Unknown operation: {operation}"})

    except Exception as e:
        logger.exception("Sheet operation failed")
        return json.dumps({"error": str(e)})


async def handle_email_ops(fclient, rcx, setup, toolcall, args):
    import base64
    from email.mime.text import MIMEText

    operation = args.get("operation")
    email_from = setup.get("EMAIL_FROM")

    try:
        token = await ckit_external_auth.get_external_auth_token(
            fclient, "google", rcx.persona.ws_id, rcx.persona.owner_fuser_id,
        )

        if not token:
            return json.dumps({
                "error": "Google OAuth not configured. Please authorize Gmail access in settings."
            })

        creds = Credentials(token=token.access_token)
        service = build("gmail", "v1", credentials=creds)

        if operation == "send":
            to = args.get("to")
            subject = args.get("subject")
            body = args.get("body")

            if not all([to, subject, body]):
                return json.dumps({"error": "to, subject, and body required"})

            message = MIMEText(body, "plain")
            message["to"] = to
            message["from"] = email_from
            message["subject"] = subject

            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

            sent_message = service.users().messages().send(
                userId="me",
                body={"raw": raw},
            ).execute()

            return json.dumps({
                "success": True,
                "message_id": sent_message.get("id"),
            })

        else:
            return json.dumps({"error": f"Unknown operation: {operation}"})

    except Exception as e:
        logger.exception("Email operation failed")
        return json.dumps({"error": str(e)})


async def handle_state_ops(mongo_collection, toolcall, args):
    operation = args.get("operation")

    try:
        if operation == "check_processed":
            event_id = args.get("event_id")
            if not event_id:
                return json.dumps({"error": "event_id required"})

            doc = await mongo_collection.find_one({"event_id": event_id})

            return json.dumps({
                "success": True,
                "processed": doc is not None,
                "announcement_sent": doc.get("announcement_sent", False) if doc else False,
                "attendee_list_sent": doc.get("attendee_list_sent", False) if doc else False,
            })

        elif operation == "mark_processed":
            event_id = args.get("event_id")
            if not event_id:
                return json.dumps({"error": "event_id required"})

            await mongo_collection.update_one(
                {"event_id": event_id},
                {
                    "$set": {
                        "event_id": event_id,
                        "announcement_sent": True,
                        "processed_at": datetime.now(CET).isoformat(),
                    }
                },
                upsert=True,
            )

            return json.dumps({"success": True})

        elif operation == "mark_attendee_sent":
            event_id = args.get("event_id")
            if not event_id:
                return json.dumps({"error": "event_id required"})

            await mongo_collection.update_one(
                {"event_id": event_id},
                {
                    "$set": {
                        "event_id": event_id,
                        "attendee_list_sent": True,
                        "attendee_sent_at": datetime.now(CET).isoformat(),
                    }
                },
                upsert=True,
            )

            return json.dumps({"success": True})

        elif operation == "get_pending_attendee_emails":
            event_date = args.get("event_date")

            docs = await mongo_collection.find({
                "attendee_list_sent": {"$ne": True},
            }).to_list(length=100)

            return json.dumps({
                "success": True,
                "pending_events": [
                    {
                        "event_id": doc.get("event_id"),
                        "processed_at": doc.get("processed_at"),
                    }
                    for doc in docs
                ],
                "count": len(docs),
            })

        else:
            return json.dumps({"error": f"Unknown operation: {operation}"})

    except Exception as e:
        logger.exception("State operation failed")
        return json.dumps({"error": str(e)})
