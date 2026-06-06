"""
Calendly API integration — real-time slot fetching and booking.

Env vars required:
    CALENDLY_API_KEY          Personal Access Token from Calendly
    CALENDLY_EVENT_TYPE_UUID  UUID of your event type
    CALENDLY_USER_URI         https://api.calendly.com/users/YOUR_UUID
    CALENDLY_LINK             Your public Calendly link (fallback)
"""

import os
import json
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

API_KEY            = os.getenv("CALENDLY_API_KEY", "")
EVENT_TYPE_UUID    = os.getenv("CALENDLY_EVENT_TYPE_UUID", "")
USER_URI           = os.getenv("CALENDLY_USER_URI", "")
CALENDLY_LINK      = os.getenv("CALENDLY_LINK", "https://calendly.com")
EVENT_TYPE_URI     = f"https://api.calendly.com/event_types/{EVENT_TYPE_UUID}"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type":  "application/json"
}


# ── Fetch available slots ──────────────────────────────────────────────────────

def get_available_slots(days_ahead: int = 5) -> list[dict]:
    """
    Returns list of available slots from Calendly for the next N days.
    Each slot: {"start": ISO string, "display": human-readable string}
    """
    if not API_KEY or not EVENT_TYPE_URI:
        return []

    now      = datetime.now(timezone.utc)
    end_time = now + timedelta(days=days_ahead)

    try:
        resp = requests.get(
            "https://api.calendly.com/event_type_available_times",
            headers=HEADERS,
            params={
                "event_type":  EVENT_TYPE_URI,
                "start_time":  now.isoformat(),
                "end_time":    end_time.isoformat(),
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
            dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
            # Convert to IST for display
            ist = dt + timedelta(hours=5, minutes=30)
            display = ist.strftime("%A, %B %d at %I:%M %p IST")
            slots.append({"start": start_iso, "display": display})

        return slots[:5]  # Return top 5 slots

    except Exception as e:
        print(f"[Calendly] get_available_slots error: {e}")
        return []


# ── Create a booking ──────────────────────────────────────────────────────────

def create_booking(
    start_iso: str,
    invitee_name: str,
    invitee_email: str
) -> dict:
    """
    Books a slot on Calendly for the given invitee.
    Returns {"success": bool, "message": str, "confirmation": str}
    """
    if not API_KEY or not EVENT_TYPE_UUID:
        return {
            "success": False,
            "message": f"Please book directly at {CALENDLY_LINK}",
            "confirmation": ""
        }

    try:
        payload = {
            "event_type_uuid": EVENT_TYPE_UUID,
            "start_time":      start_iso,
            "invitee": {
                "name":  invitee_name,
                "email": invitee_email
            }
        }

        resp = requests.post(
            "https://api.calendly.com/one_off_event_types",
            headers=HEADERS,
            json=payload,
            timeout=10
        )

        # Calendly scheduling API
        resp2 = requests.post(
            "https://api.calendly.com/scheduling_links",
            headers=HEADERS,
            json={
                "max_event_count": 1,
                "owner":           EVENT_TYPE_URI,
                "owner_type":      "EventType"
            },
            timeout=10
        )
        resp2.raise_for_status()
        link_data = resp2.json()
        booking_url = link_data.get("resource", {}).get("booking_url", CALENDLY_LINK)

        dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        ist = dt + timedelta(hours=5, minutes=30)
        display = ist.strftime("%A, %B %d at %I:%M %p IST")

        return {
            "success":      True,
            "message":      f"Slot reserved for {display}.",
            "confirmation": booking_url,
            "display_time": display
        }

    except Exception as e:
        print(f"[Calendly] create_booking error: {e}")
        return {
            "success":      False,
            "message":      f"Please book directly: {CALENDLY_LINK}",
            "confirmation": CALENDLY_LINK
        }


# ── Parse preferred time from natural language ────────────────────────────────

def find_matching_slot(preferred: str, slots: list[dict]) -> dict | None:
    """
    Match a natural language time preference to an available slot.
    e.g. "Thursday 3pm" matches the Thursday 3:00 PM slot.
    """
    if not preferred or not slots:
        return None

    preferred_lower = preferred.lower()

    days = {
        "monday": 0, "tuesday": 1, "wednesday": 2,
        "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
        "mon": 0, "tue": 1, "wed": 2, "thu": 3,
        "fri": 4, "sat": 5, "sun": 6,
        "tomorrow": (datetime.now(timezone.utc).weekday() + 1) % 7
    }

    target_day = None
    for day_name, day_num in days.items():
        if day_name in preferred_lower:
            target_day = day_num
            break

    # Extract hour from preference
    target_hour = None
    for h in range(6, 22):
        if f"{h}pm" in preferred_lower or f"{h} pm" in preferred_lower:
            target_hour = h + 12 if h < 12 else h
            break
        if f"{h}am" in preferred_lower or f"{h} am" in preferred_lower:
            target_hour = h
            break
        if f"{h}:00" in preferred_lower:
            target_hour = h
            break

    # Match against available slots
    for slot in slots:
        dt = datetime.fromisoformat(slot["start"].replace("Z", "+00:00"))
        ist = dt + timedelta(hours=5, minutes=30)

        day_match  = (target_day is None or ist.weekday() == target_day)
        hour_match = (target_hour is None or ist.hour == target_hour)

        if day_match and hour_match:
            return slot

    # If no exact match, return first available
    return slots[0] if slots else None


# ── Session state for collecting invitee info ─────────────────────────────────

booking_sessions: dict[str, dict] = {}


def get_booking_session(session_id: str) -> dict:
    if session_id not in booking_sessions:
        booking_sessions[session_id] = {
            "stage":      None,
            "name":       None,
            "email":      None,
            "slot":       None,
            "slots":      []
        }
    return booking_sessions[session_id]


def clear_booking_session(session_id: str):
    booking_sessions.pop(session_id, None)


# ── Main handler ──────────────────────────────────────────────────────────────

def handle_calendar_request(params: dict, session_id: str = "default") -> str:
    """
    Main entry point called by chatbot.py and voice.py.
    Handles multi-turn booking flow:
      1. Show available slots
      2. Collect name
      3. Collect email
      4. Confirm and book
    """
    intent    = params.get("intent", "check_availability")
    preferred = params.get("preferred_date")
    message   = params.get("notes", "")
    duration  = int(params.get("duration_minutes") or 30)

    session = get_booking_session(session_id)

    # ── Stage: waiting for name ────────────────────────────────────────────
    if session["stage"] == "waiting_for_name":
        name = message.strip() or params.get("notes", "").strip()
        if len(name) < 2:
            return "Could you share your name so I can complete the booking?"
        session["name"]  = name
        session["stage"] = "waiting_for_email"
        return (
            f"Got it, {name}! And what's your email address? "
            "I'll send the confirmation there."
        )

    # ── Stage: waiting for email ───────────────────────────────────────────
    if session["stage"] == "waiting_for_email":
        email = message.strip()
        if "@" not in email or "." not in email:
            return "That doesn't look like a valid email. Could you share it again?"

        session["email"] = email
        slot  = session.get("slot")
        name  = session.get("name")

        if not slot:
            clear_booking_session(session_id)
            return f"Something went wrong. Please book directly: {CALENDLY_LINK}"

        # ── Create the booking ─────────────────────────────────────────────
        result = create_booking(
            start_iso=slot["start"],
            invitee_name=name,
            invitee_email=email
        )

        clear_booking_session(session_id)

        if result["success"]:
            return (
                f"Perfect! Your meeting is booked for {result['display_time']}. "
                f"A confirmation has been sent to {email}. "
                f"Here's your booking link: {result['confirmation']}"
            )
        else:
            return (
                f"I wasn't able to auto-book this time. "
                f"Please use this link to confirm your slot: {result['confirmation']}"
            )

    # ── Initial booking/availability request ──────────────────────────────
    slots = get_available_slots(days_ahead=5)

    if not slots:
        clear_booking_session(session_id)
        return (
            f"I couldn't fetch live availability right now. "
            f"Please book directly at {CALENDLY_LINK}"
        )

    if intent == "check_availability":
        slot_list = "\n".join(f"• {s['display']}" for s in slots)
        return (
            f"Here are the next available {duration}-minute slots:\n\n"
            f"{slot_list}\n\n"
            f"Just tell me which time works for you and I'll book it right away!"
        )

    if intent == "book_meeting":
        matched_slot = find_matching_slot(preferred or "", slots)

        if not matched_slot:
            matched_slot = slots[0]

        session["slot"]  = matched_slot
        session["stage"] = "waiting_for_name"
        session["slots"] = slots

        return (
            f"I have {matched_slot['display']} available. "
            f"To confirm the booking, could I get your name please?"
        )

    return f"You can check availability here: {CALENDLY_LINK}"