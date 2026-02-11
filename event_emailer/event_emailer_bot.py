#!/usr/bin/env python3
"""
Event Emailer Bot - Automated email notifications for Google Calendar events

Schedule:
- Every Monday at 9:00 AM CET: Check calendar for upcoming week
- 90 minutes before event: Send announcement email
- 80 minutes before event: Send attendee list email

On-demand commands:
- "Check this week for events"
- "Send me email and attendees list for event on [DATE]"
"""

import asyncio
import os
import re
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from dateutil import parser as dateparser
from flexus_client_kit import ckit_user_chat as rcx
from flexus_client_kit import ckit_bot_exec

# Import tool implementations and prompts
from event_emailer.event_emailer_tools import (
    calendar_ops,
    sheet_ops,
    email_ops,
    state_ops,
)
from event_emailer.event_emailer_prompts import system_prompt

BOT_NAME = "event_emailer"
BOT_VERSION = "0.2.0"

CET = ZoneInfo("Europe/Paris")


async def check_and_schedule_emails(rcaller: rcx.ResponderCaller) -> str:
    """
    Check calendar for events in the upcoming week and schedule emails.
    Returns summary of what was scheduled.
    """
    # Get events for the upcoming week
    now = datetime.now(CET)
    week_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = week_start + timedelta(days=7)
    
    time_min = week_start.isoformat()
    time_max = week_end.isoformat()
    
    # List events
    result = await calendar_ops(
        rcaller,
        operation="list",
        time_min=time_min,
        time_max=time_max,
    )
    
    if "error" in result:
        return f"Error checking calendar: {result['error']}"
    
    events = result.get("events", [])
    if not events:
        return "No events found in the upcoming week."
    
    scheduled_count = 0
    summary_lines = ["Found events for the upcoming week:\n"]
    
    for event in events:
        event_id = event.get("id")
        event_title = event.get("summary", "Untitled Event")
        event_start = event.get("start", {}).get("dateTime")
        
        if not event_start:
            continue
            
        # Parse event time
        event_dt = dateparser.parse(event_start)
        if event_dt.tzinfo is None:
            event_dt = event_dt.replace(tzinfo=CET)
        
        # Check if already processed
        state_result = await state_ops(
            rcaller,
            operation="get",
            event_id=event_id,
        )
        
        if "event_state" in state_result and state_result["event_state"].get("announcement_sent"):
            summary_lines.append(f"- {event_title} ({event_dt.strftime('%b %d, %H:%M')}) - already scheduled")
            continue
        
        # Schedule announcement email (90 min before)
        announcement_time = event_dt - timedelta(minutes=90)
        await state_ops(
            rcaller,
            operation="schedule_email",
            event_id=event_id,
            email_type="announcement",
            send_at=announcement_time.isoformat(),
            event_data={
                "title": event_title,
                "start_time": event_start,
                "zoom_link": event.get("hangoutLink", event.get("location", "")),
            }
        )
        
        # Schedule attendee list email (80 min before)
        attendee_time = event_dt - timedelta(minutes=80)
        await state_ops(
            rcaller,
            operation="schedule_email",
            event_id=event_id,
            email_type="attendee_list",
            send_at=attendee_time.isoformat(),
            event_data={
                "title": event_title,
                "start_time": event_start,
            }
        )
        
        # Mark as processed
        await state_ops(
            rcaller,
            operation="update",
            event_id=event_id,
            updates={"announcement_sent": True, "attendee_list_sent": True},
        )
        
        scheduled_count += 1
        summary_lines.append(
            f"- {event_title} ({event_dt.strftime('%b %d, %H:%M')})\n"
            f"  → Announcement: {announcement_time.strftime('%b %d, %H:%M')}\n"
            f"  → Attendee list: {attendee_time.strftime('%b %d, %H:%M')}"
        )
    
    summary_lines.append(f"\nScheduled emails for {scheduled_count} event(s).")
    return "\n".join(summary_lines)


async def send_scheduled_emails(rcaller: rcx.ResponderCaller) -> None:
    """
    Background task that checks for and sends scheduled emails.
    Runs every minute.
    """
    while True:
        try:
            # Get emails that need to be sent now (within 2-minute window)
            now = datetime.now(CET)
            result = await state_ops(
                rcaller,
                operation="get_emails_to_send",
                current_time=now.isoformat(),
            )
            
            emails_to_send = result.get("emails", [])
            
            for email_data in emails_to_send:
                email_id = email_data.get("email_id")
                email_type = email_data.get("email_type")
                event_data = email_data.get("event_data", {})
                
                try:
                    if email_type == "announcement":
                        # Generate and send announcement email
                        await rcaller.respond_with_llm(
                            f"Generate an announcement email for event: {event_data.get('title')}. "
                            f"Event time: {event_data.get('start_time')}. "
                            f"Zoom link: {event_data.get('zoom_link')}. "
                            f"Include 3 subject line variations in the email body. "
                            f"Use the template style but vary it slightly to avoid spam filters."
                        )
                        
                    elif email_type == "attendee_list":
                        # Get attendee list and send
                        event_start = event_data.get("start_time")
                        sheet_result = await sheet_ops(
                            rcaller,
                            operation="read",
                            date_filter=event_start,
                        )
                        
                        attendees = sheet_result.get("attendees", [])
                        await rcaller.respond_with_llm(
                            f"Send attendee list email for event: {event_data.get('title')}. "
                            f"Attendees: {', '.join(attendees) if attendees else 'No attendees registered'}."
                        )
                    
                    # Mark email as sent
                    await state_ops(
                        rcaller,
                        operation="mark_email_sent",
                        email_id=email_id,
                    )
                    
                except Exception as e:
                    print(f"Error sending email {email_id}: {e}")
                    continue
        
        except Exception as e:
            print(f"Error in send_scheduled_emails: {e}")
        
        # Wait 60 seconds before checking again
        await asyncio.sleep(60)


@rcx.on_user_message()
async def handle_user_message(rcaller: rcx.ResponderCaller):
    """Handle user messages with LLM and tools."""
    
    user_msg = rcaller.msg_user_text.lower()
    
    # Check for specific commands
    if "check this week" in user_msg or "check for events" in user_msg:
        # Run calendar check and ask user about scheduling
        summary = await check_and_schedule_emails(rcaller)
        await rcaller.respond_with_text(
            summary + "\n\nEmails have been scheduled to send automatically at the specified times. "
            "Would you like to send them now instead?"
        )
        return
    
    # Check for date-specific request
    date_match = re.search(r'event on (.+?)(?:\s|$)', user_msg)
    if date_match:
        date_str = date_match.group(1)
        try:
            # Parse the date
            target_date = dateparser.parse(date_str)
            if not target_date:
                await rcaller.respond_with_text(f"Couldn't understand the date: {date_str}")
                return
            
            # Search for event on that date
            time_min = target_date.replace(hour=0, minute=0, second=0).isoformat()
            time_max = target_date.replace(hour=23, minute=59, second=59).isoformat()
            
            result = await calendar_ops(
                rcaller,
                operation="list",
                time_min=time_min,
                time_max=time_max,
            )
            
            events = result.get("events", [])
            if not events:
                await rcaller.respond_with_text(f"No event found on {target_date.strftime('%B %d, %Y')}.")
                return
            
            # Found event(s), ask about scheduling
            event = events[0]  # Take first event if multiple
            event_start = dateparser.parse(event.get("start", {}).get("dateTime"))
            announcement_time = event_start - timedelta(minutes=90)
            attendee_time = event_start - timedelta(minutes=80)
            
            await rcaller.respond_with_text(
                f"Found event: **{event.get('summary')}** on {event_start.strftime('%B %d at %H:%M')}.\n\n"
                f"Send now or schedule it?\n"
                f"- Email at: {announcement_time.strftime('%B %d at %H:%M')}\n"
                f"- Attendee list at: {attendee_time.strftime('%B %d at %H:%M')}"
            )
            return
            
        except Exception as e:
            await rcaller.respond_with_text(f"Error processing date request: {e}")
            return
    
    # Default: use LLM with tools
    await rcaller.respond_with_llm(system_prompt)


@rcx.on_schedule(cron="0 9 * * 1", timezone="Europe/Paris")
async def monday_check(rcaller: rcx.ResponderCaller):
    """
    Scheduled task: Every Monday at 9:00 AM CET
    Check calendar for upcoming week and schedule emails.
    """
    summary = await check_and_schedule_emails(rcaller)
    await rcaller.respond_with_text(
        f"📅 **Weekly Calendar Check**\n\n{summary}"
    )


async def main():
    """Main entry point."""
    scenario_fn = ckit_bot_exec.parse_bot_args()
    
    # Start background email sender
    async def run_with_background_tasks():
        # Create background task
        email_task = asyncio.create_task(
            send_scheduled_emails(
                rcx.ResponderCaller(
                    msg_id="background",
                    msg_user_text="",
                    chat_id="system",
                    workspace_id=os.environ.get("FLEXUS_WORKSPACE", ""),
                )
            )
        )
        
        # Run main bot
        await rcx.run_bots_in_this_group(
            scenario_fn=scenario_fn,
            tools=[calendar_ops, sheet_ops, email_ops, state_ops],
        )
        
        # Cancel background task when bot stops
        email_task.cancel()
    
    await run_with_background_tasks()


if __name__ == "__main__":
    asyncio.run(main())
