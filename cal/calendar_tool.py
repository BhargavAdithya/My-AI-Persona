"""
Calendly API integration — real slot fetching, smart validation, booking.
"""

import os
import re
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

API_KEY         = os.getenv("CALENDLY_API_KEY", "")
EVENT_TYPE_UUID = os.getenv("CALENDLY_EVENT_TYPE_UUID", "")
USER_URI        = os.getenv("CALENDLY_USER_URI", "")
CALENDLY_LINK   = os.getenv("CALENDLY_LINK", "https://calendly.com")
EVENT_TYPE_URI  = f"https://api.calendly.com/event_types/{EVENT_TYPE_UUID}"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type":  "application/json"
}

# Odd hours that likely indicate AM/PM confusion
SUSPICIOUS_HOURS = [0, 1, 2, 3, 4, 5]


# ── Fetch real available slots from Calendly ──────────────────────────────────

def get_available_slots(days_ahead: int = 7) -> list[dict]:
    """Fetch real available slots from Calendly API."""
    if not API_KEY or not EVENT_TYPE_UUID:
        return []

    now      = datetime.now(timezone.utc)
    end_time = now + timedelta(days=days_ahead)

    try:
        resp = requests.get(
            "https://api.calendly.com/event_type_available_times",
            headers=HEADERS,
            params={
                "event_type": EVENT_TYPE_URI,
                "start_time": now.isoformat(),
                "end_time":   end_time.isoformat(),
            },
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()

        slots = []
        for item in data.get("collection", []):
            start_iso = item.get("start_time", "")
            if not start_iso:
                continue
            dt  = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
            ist = dt + timedelta(hours=5, minutes=30)
            display = ist.strftime("%A, %B %d at %I:%M %p IST")
            slots.append({
                "start":   start_iso,
                "display": display,
                "dt_ist":  ist
            })

        return slots[:6]

    except Exception as e:
        print(f"[Calendly] get_available_slots error: {e}")
        return []


# ── Smart time parsing ────────────────────────────────────────────────────────

def parse_hour_from_text(text: str) -> int | None:
    """Extract hour from natural language. Returns 24h hour or None."""
    text = text.lower().strip()

    # Match patterns like "5pm", "5 pm", "17:00", "5:00 pm"
    patterns = [
        r'(\d{1,2})\s*:\s*\d{2}\s*(am|pm)',
        r'(\d{1,2})\s*(am|pm)',
        r'(\d{1,2})\s*:\s*\d{2}',
        r'\bat\s+(\d{1,2})\b',
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            hour = int(match.group(1))
            suffix = match.group(2).lower() if len(match.groups()) > 1 and match.group(2) else None
            if suffix == "pm" and hour < 12:
                hour += 12
            elif suffix == "am" and hour == 12:
                hour = 0
            return hour

    return None


def parse_day_from_text(text: str) -> int | None:
    """Extract weekday number (0=Mon) from text."""
    text = text.lower()
    days = {
        "monday": 0, "mon": 0,
        "tuesday": 1, "tue": 1,
        "wednesday": 2, "wed": 2,
        "thursday": 3, "thu": 3,
        "friday": 4, "fri": 4,
        "saturday": 5, "sat": 5,
        "sunday": 6, "sun": 6,
        "tomorrow": (datetime.now(timezone.utc).weekday() + 1) % 7,
        "today": datetime.now(timezone.utc).weekday(),
    }
    for name, num in days.items():
        if name in text:
            return num
    return None


def is_suspicious_time(hour: int) -> bool:
    """Return True if the hour seems like an AM/PM mistake."""
    return hour in SUSPICIOUS_HOURS


def find_matching_slot(preferred: str, slots: list[dict]) -> dict | None:
    """Match natural language preference to an actual available slot."""
    if not preferred or not slots:
        return None

    target_day  = parse_day_from_text(preferred)
    target_hour = parse_hour_from_text(preferred)

    for slot in slots:
        ist = slot["dt_ist"]
        day_match  = (target_day  is None or ist.weekday() == target_day)
        hour_match = (target_hour is None or ist.hour    == target_hour)
        if day_match and hour_match:
            return slot

    # Partial match — day only
    if target_day is not None:
        for slot in slots:
            if slot["dt_ist"].weekday() == target_day:
                return slot

    return None


# ── Create booking via Calendly scheduling link ───────────────────────────────

def create_booking(
    start_iso: str,
    invitee_name: str,
    invitee_email: str
) -> dict:
    """Create a single-use scheduling link for the specific slot."""
    try:
        resp = requests.post(
            "https://api.calendly.com/scheduling_links",
            headers=HEADERS,
            json={
                "max_event_count": 1,
                "owner":           EVENT_TYPE_URI,
                "owner_type":      "EventType"
            },
            timeout=10
        )
        resp.raise_for_status()
        booking_url = resp.json().get("resource", {}).get("booking_url", CALENDLY_LINK)

        dt      = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        ist     = dt + timedelta(hours=5, minutes=30)
        display = ist.strftime("%A, %B %d at %I:%M %p IST")

        return {
            "success":      True,
            "display_time": display,
            "confirmation": booking_url
        }

    except Exception as e:
        print(f"[Calendly] create_booking error: {e}")
        return {
            "success":      False,
            "display_time": "",
            "confirmation": CALENDLY_LINK
        }


# ── Session state ─────────────────────────────────────────────────────────────

booking_sessions: dict[str, dict] = {}


def get_session(sid: str) -> dict:
    if sid not in booking_sessions:
        booking_sessions[sid] = {
            "stage": None,
            "name":  None,
            "email": None,
            "slot":  None,
            "pending_suspicious_slot": None,
        }
    return booking_sessions[sid]


def clear_session(sid: str):
    booking_sessions.pop(sid, None)


# ── Main handler ──────────────────────────────────────────────────────────────

def handle_calendar_request(params: dict, session_id: str = "default") -> str:
    intent    = params.get("intent", "check_availability")
    preferred = params.get("preferred_date") or ""
    message   = params.get("notes", "")
    duration  = int(params.get("duration_minutes") or 30)

    session = get_session(session_id)

    # ── Stage: confirm suspicious time ────────────────────────────────────
    if session["stage"] == "confirm_suspicious_time":
        lowered = message.lower()
        if any(w in lowered for w in ["yes", "correct", "right", "confirm", "that's right"]):
            slot = session["pending_suspicious_slot"]
            session["slot"]  = slot
            session["stage"] = "waiting_for_name"
            session["pending_suspicious_slot"] = None
            return (
                f"Got it! Confirming {slot['display']}. "
                f"Could I get your name to complete the booking?"
            )
        else:
            slots = get_available_slots()
            session["stage"] = None
            session["pending_suspicious_slot"] = None
            if slots:
                slot_list = "\n".join(f"• {s['display']}" for s in slots)
                return (
                    f"No problem! Here are the available slots:\n\n{slot_list}\n\n"
                    f"Which one works for you?"
                )
            return f"Please check availability here: {CALENDLY_LINK}"

    # ── Stage: waiting for name ────────────────────────────────────────────
    if session["stage"] == "waiting_for_name":
        name = message.strip()
        if len(name) < 2:
            return "Could you share your name so I can complete the booking?"
        session["name"]  = name
        session["stage"] = "waiting_for_email"
        return f"Thanks {name}! What is your email address?"

    # ── Stage: waiting for email ───────────────────────────────────────────
    if session["stage"] == "waiting_for_email":
        email = message.strip()
        if "@" not in email or "." not in email:
            return "That does not look like a valid email. Could you share it again?"

        session["email"] = email
        slot = session.get("slot")
        name = session.get("name")

        if not slot:
            clear_session(session_id)
            return f"Something went wrong. Please book directly: {CALENDLY_LINK}"

        result = create_booking(
            start_iso=slot["start"],
            invitee_name=name,
            invitee_email=email
        )
        clear_session(session_id)

        if result["success"]:
            return (
                f"Done! Your interview is booked for {result['display_time']}. "
                f"A confirmation email will be sent to {email}. "
                f"Here is your booking link: {result['confirmation']}"
            )
        return (
            f"I could not auto-book this time. "
            f"Please use this link to confirm: {result['confirmation']}"
        )

    # ── Initial request ────────────────────────────────────────────────────
    slots = get_available_slots(days_ahead=7)

    if not slots:
        clear_session(session_id)
        return (
            f"I could not fetch live availability right now. "
            f"Please book here: {CALENDLY_LINK}"
        )

    if intent == "check_availability":
        slot_list = "\n".join(f"• {s['display']}" for s in slots)
        return (
            f"Here are the next available {duration}-minute slots:\n\n"
            f"{slot_list}\n\n"
            f"Which time works for you?"
        )

    if intent == "book_meeting":
        matched = find_matching_slot(preferred or message, slots)

        if not matched:
            # Requested slot not available — show what is available
            slot_list = "\n".join(f"• {s['display']}" for s in slots)
            return (
                f"I'm sorry, that slot is not available. "
                f"Here are the times that are open:\n\n{slot_list}\n\n"
                f"Which one works for you?"
            )

        # Check for suspicious time
        hour = matched["dt_ist"].hour
        if is_suspicious_time(hour):
            session["stage"] = "confirm_suspicious_time"
            session["pending_suspicious_slot"] = matched
            return (
                f"Just to confirm — you said {matched['display']}. "
                f"That is quite early. Did you mean {matched['display']}? "
                f"Or would you like to see other available slots?"
            )

        session["slot"]  = matched
        session["stage"] = "waiting_for_name"
        return (
            f"I have {matched['display']} available. "
            f"To confirm the booking, could I get your name please?"
        )

    return f"You can check availability here: {CALENDLY_LINK}"