# Event Emailer Bot

Automates email communication for Google Calendar events.

## What It Does

The Event Emailer bot monitors a Google Calendar and automatically sends two types of emails:

1. **Event Announcement Email** - Sent when a new event is detected
2. **Attendee List Email** - Sent 1 hour 20 minutes before each event

## Features

### Event Announcements

When the bot detects a new event in the monitored calendar:
- Generates 3 subject line variations for attendee invitations
- Composes an email body styled after provided templates
- Includes event details: title, date/time with timezone, Zoom link
- Sends to configured recipient
- Tracks processed events in MongoDB to avoid duplicates

### Pre-Event Attendee Lists

80 minutes before each event starts:
- Reads attendee data from a Google Sheet
- Matches attendees by event date
- Deduplicates email addresses
- Sends list to event organizer
- Handles cases with no attendees gracefully

## Configuration

The bot requires the following setup:

### Google Calendar
- **Calendar ID**: The Google Calendar to monitor (default: `c_76540dc287a40a9d6d19888566ca7e04e027278cd4e10251e132771eee0169647@group.calendar.google.com`)

### Google Sheets
- **Sheet ID**: Google Sheet containing attendee registrations (default: `1_vyl-ka59rbHU-RM2RWaE0Ob1xa_JanovwfcgdXLCF0`)
- Expected columns: `email` and `preferred date`

### Email Settings
- **From Address**: Sender email (default: `kate@smallcloud.tech`)
- **To Address**: Recipient email (default: `kate@smallcloud.tech`)

### Authentication
Requires Google OAuth authorization with the following scopes:
- Google Calendar API (read events)
- Google Sheets API (read attendee data)
- Gmail API (send emails)

## Email Formats

### Announcement Email
- **Subject**: `email_for_attendees_DD-MM-YYYY`
- **Content**: 3 subject variations + event details in casual, builder-friendly tone

### Attendee List Email
- **Subject**: `list_of_attendees_DD-MM-YYYY`
- **Content**: Deduplicated list of attendee emails

## Technical Details

### Schedule
- Runs every 72 hours (3 days) via `SCHED_ANY` schedule type
- Each run checks for:
  - New events needing announcement emails
  - Events starting in 75-85 minutes needing attendee list emails

### State Management
- Uses MongoDB to track processed events
- Prevents duplicate emails
- Stores event metadata for reference

### Error Handling
- Gracefully handles API errors
- Logs issues for debugging
- Continues operation on transient failures

## Tools

The bot uses four custom tools (all with `strict=False` to support optional parameters):

1. **calendar_ops** - List and retrieve calendar events (optional `event_id`)
2. **sheet_ops** - Read attendee data from Google Sheets
3. **email_ops** - Send emails via Gmail API
4. **state_ops** - Track processed events in MongoDB (optional `event_id`)

## Installation

```bash
pip install -e /workspace
python -m event_emailer.event_emailer_install --ws=$FLEXUS_WORKSPACE
```

## Running

```bash
python -m event_emailer.event_emailer_bot
```

## Dependencies

- flexus-client-kit
- google-auth
- google-auth-oauthlib
- google-auth-httplib2
- google-api-python-client
- motor (async MongoDB driver)
- pymongo

## Version

Current version: 0.2.1

### Changelog

- **0.2.1** - Fixed broken Flexus Client Kit API imports
  - Replaced non-existent `ckit_user_chat` with proper `ckit_client`, `ckit_bot_exec`, etc.
  - Implemented correct bot main loop pattern following frog bot reference
  - Created proper CloudTool definitions for all 4 tools
  - Fixed tool handlers to use `@rcx.on_tool_call()` decorators
  - Removed invalid decorator patterns (`@rcx.on_user_message()`, `@rcx.on_schedule()`)
  - Bot now follows standard Flexus bot architecture

- **0.2.0** - Updated schedule to EVERY:72h (3 days)
