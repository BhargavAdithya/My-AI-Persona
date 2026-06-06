"""
Calendar integration module.

Currently supports:
  - Google Calendar API (list free slots, create events)
  - Calendly link fallback

Setup for Google Calendar:
  1. Go to https://console.cloud.google.com
  2. Enable Google Calendar API
  3. Create OAuth2 credentials → download as credentials.json → place in calendar/
  4. Run: python -m calendar.calendar_tool --auth
     (opens browser for one-time OAuth consent, saves token.json)
  5. Set in .env:
       GOOGLE_CALENDAR_ID=primary   (or your specific calendar ID)

Install: pip install google-api-python-client google-auth-oauthlib
"""

import os
import sys
import json
import datetime
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CALENDAR_DIR = os.path.dirname(os.path.abspath(__file__))

CREDENTIALS_PATH = os.path.join(CALENDAR_DIR, "credentials.json")
TOKEN_PATH = os.path.join(CALENDAR_DIR, "token.json")
CALENDLY_LINK = os.getenv("CALENDLY_LINK")
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")

SCOPES = ["https://www.googleapis.com/auth/calendar"]


# ── Google Calendar Auth ────────────────────────────────────────────────────────

def get_google_calendar_service():
    """Authenticate and return a Google Calendar service object."""
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = None

    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                raise FileNotFoundError(
                    f"credentials.json not found at {CREDENTIALS_PATH}. "
                    "Please download OAuth2 credentials from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)


# ── Free Slot Discovery ─────────────────────────────────────────────────────────

def get_free_slots(
    days_ahead: int = 7,
    slot_duration_minutes: int = 30,
    working_hours: tuple = (9, 18)  # 9 AM – 6 PM
) -> list[dict]:
    """
    Find available slots in the next `days_ahead` days.
    Returns list of {"start": ISO string, "end": ISO string, "display": human-readable}.
    """
    try:
        service = get_google_calendar_service()
    except Exception as e:
        print(f"[Calendar] Google Calendar unavailable: {e}")
        return _fallback_slots(days_ahead, slot_duration_minutes, working_hours)

    now = datetime.datetime.utcnow()
    time_min = now.isoformat() + "Z"
    time_max = (now + datetime.timedelta(days=days_ahead)).isoformat() + "Z"

    # Get busy times from FreeBusy API
    body = {
        "timeMin": time_min,
        "timeMax": time_max,
        "items": [{"id": CALENDAR_ID}]
    }
    freebusy = service.freebusy().query(body=body).execute()
    busy_periods = freebusy.get("calendars", {}).get(CALENDAR_ID, {}).get("busy", [])

    # Generate candidate slots
    slots = []
    current = now.replace(hour=working_hours[0], minute=0, second=0, microsecond=0)
    end_range = now + datetime.timedelta(days=days_ahead)

    while current < end_range:
        # Skip weekends
        if current.weekday() >= 5:
            current += datetime.timedelta(days=1)
            current = current.replace(hour=working_hours[0], minute=0)
            continue

        slot_end = current + datetime.timedelta(minutes=slot_duration_minutes)

        # Check if within working hours
        if current.hour >= working_hours[1]:
            current += datetime.timedelta(days=1)
            current = current.replace(hour=working_hours[0], minute=0)
            continue

        # Check if slot conflicts with busy periods
        is_busy = False
        for period in busy_periods:
            busy_start = datetime.datetime.fromisoformat(period["start"].replace("Z", "+00:00"))
            busy_end = datetime.datetime.fromisoformat(period["end"].replace("Z", "+00:00"))
            busy_start = busy_start.replace(tzinfo=None)
            busy_end = busy_end.replace(tzinfo=None)
            if not (slot_end <= busy_start or current >= busy_end):
                is_busy = True
                break

        if not is_busy and current > now:
            slots.append({
                "start": current.isoformat(),
                "end": slot_end.isoformat(),
                "display": current.strftime("%A, %B %d at %I:%M %p")
            })

        current += datetime.timedelta(minutes=slot_duration_minutes)

        if len(slots) >= 5:  # Return top 5 slots
            break

    return slots


def _fallback_slots(days_ahead: int, slot_duration_minutes: int, working_hours: tuple) -> list[dict]:
    """Generate plausible slots when Calendar API is unavailable."""
    slots = []
    now = datetime.datetime.now()
    check = now + datetime.timedelta(days=1)
    check = check.replace(hour=10, minute=0, second=0, microsecond=0)

    for _ in range(days_ahead * 2):
        if check.weekday() < 5 and working_hours[0] <= check.hour < working_hours[1]:
            slot_end = check + datetime.timedelta(minutes=slot_duration_minutes)
            slots.append({
                "start": check.isoformat(),
                "end": slot_end.isoformat(),
                "display": check.strftime("%A, %B %d at %I:%M %p")
            })
        check += datetime.timedelta(hours=2)
        if len(slots) >= 5:
            break

    return slots


# ── Book a Meeting ──────────────────────────────────────────────────────────────

def book_meeting(
    title: str,
    start_iso: str,
    end_iso: str,
    attendee_email: str,
    description: str = "Meeting booked via AI Persona"
) -> dict:
    """
    Create a calendar event and invite the attendee.
    Returns {"success": bool, "event_link": str, "message": str}
    """
    try:
        service = get_google_calendar_service()

        event = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start_iso, "timeZone": "Asia/Kolkata"},
            "end": {"dateTime": end_iso, "timeZone": "Asia/Kolkata"},
            "attendees": [{"email": attendee_email}],
            "conferenceData": {
                "createRequest": {"requestId": f"meet_{int(datetime.datetime.now().timestamp())}"}
            },
            "reminders": {
                "useDefault": False,
                "overrides": [{"method": "email", "minutes": 60}]
            }
        }

        created = service.events().insert(
            calendarId=CALENDAR_ID,
            body=event,
            conferenceDataVersion=1,
            sendUpdates="all"
        ).execute()

        return {
            "success": True,
            "event_link": created.get("htmlLink", ""),
            "meet_link": created.get("conferenceData", {}).get("entryPoints", [{}])[0].get("uri", ""),
            "message": f"Meeting booked! Confirmation sent to {attendee_email}."
        }

    except Exception as e:
        print(f"[Calendar] Booking error: {e}")
        return {
            "success": False,
            "event_link": CALENDLY_LINK,
            "meet_link": "",
            "message": f"Couldn't auto-book. Please use: {CALENDLY_LINK}"
        }


# ── High-level handler (used by chatbot.py and voice.py) ───────────────────────

def handle_calendar_request(params: dict) -> str:
    intent = params.get("intent", "check_availability")
    duration = int(params.get("duration_minutes") or 30)
    preferred = params.get("preferred_date")

    if intent == "book_meeting":
        if preferred:
            return (
                f"Sure! To book a {duration}-minute call around {preferred}, "
                f"please use this scheduling link — it shows real-time availability:\n\n"
                f"📅 **{CALENDLY_LINK}**\n\n"
                f"Pick any slot that works and you'll get an instant confirmation email."
            )
        return (
            f"Sure! Here's the scheduling link with real-time availability:\n\n"
            f"📅 **{CALENDLY_LINK}**\n\n"
            f"Pick any slot that works and you'll get an instant confirmation email."
        )

    return (
        f"You can check availability and book a {duration}-minute call here:\n\n"
        f"📅 **{CALENDLY_LINK}**\n\n"
        f"All slots are synced with the real calendar — pick whatever works for you."
    )


# ── CLI for one-time OAuth setup ────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--auth", action="store_true", help="Run OAuth flow to generate token.json")
    parser.add_argument("--test", action="store_true", help="Test: list free slots")
    args = parser.parse_args()

    if args.auth:
        print("Running OAuth flow...")
        get_google_calendar_service()
        print(f"✅ token.json saved to {TOKEN_PATH}")

    if args.test:
        slots = get_free_slots()
        print("Available slots:")
        for s in slots:
            print(f"  {s['display']}")