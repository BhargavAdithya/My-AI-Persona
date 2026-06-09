import os
import sys
import json
import google.genai as genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
import google.genai as genai_lib

def _get_best_model(client) -> str:
    """Find the best available Gemini model for this API key."""
    preferred = [
        "gemini-2.5-flash-preview-05-20",
        "gemini-2.5-flash-preview-04-17",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-flash",
        "gemini-1.5-flash-latest",
    ]
    try:
        available = [m.name for m in client.models.list()]
        for model in preferred:
            if any(model in a for a in available):
                print(f"[Model] Using: {model}")
                return model
    except Exception as e:
        print(f"[Model] Could not list models: {e}")
    return "gemini-2.0-flash"

MODEL_NAME = _get_best_model(client)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag.retriever import retrieve_for_query, retrieve, format_context
from chat_app.prompts import SYSTEM_PROMPT, CALENDAR_PROMPT, FALLBACK_RESPONSE

INTRO_KEYWORDS = [
    "introduce yourself", "tell me about yourself", "who are you",
    "about yourself", "introduce", "tell me about you",
    "describe yourself", "your introduction", "give me an intro",
    "your background", "introduce yourself"
]

CALENDAR_KEYWORDS = [
    "book", "schedule", "meeting", "call", "availability",
    "available", "slot", "appointment", "calendar",
    "when can", "free time", "set up", "interview"
]


def is_intro_query(message: str) -> bool:
    return any(kw in message.lower() for kw in INTRO_KEYWORDS)


def is_calendar_intent(message: str) -> bool:
    return any(kw in message.lower() for kw in CALENDAR_KEYWORDS)


def detect_calendar_params(message: str) -> dict:
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=CALENDAR_PROMPT.format(user_message=message)
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except Exception:
        return {
            "intent": "check_availability",
            "preferred_date": None,
            "duration_minutes": 30,
            "notes": message
        }


def get_intro_context() -> str:
    """For intro queries pull resume chunks + one README chunk per repo."""
    chunks = retrieve("education skills experience background projects", n_results=5)

    from rag.vector_store import get_collection
    col = get_collection()
    all_docs = col.get(include=["documents", "metadatas"])

    seen_repos = set()
    for doc, meta in zip(all_docs["documents"], all_docs["metadatas"]):
        source = meta.get("source", "")
        if "readme" in source.lower() and "github_repos" in source.lower():
            source_norm = source.replace("\\", "/")
            parts = source_norm.split("github_repos/")
            if len(parts) > 1:
                repo_name = parts[1].split("/")[0]
                if repo_name not in seen_repos:
                    seen_repos.add(repo_name)
                    chunks.append({
                        "content": doc,
                        "source": source,
                        "distance": 0.0
                    })

    return format_context(chunks[:10])


def chat(
    user_message: str,
    history: list[dict],
    calendar_handler=None,
    n_chunks: int = 8,
    is_voice: bool = False
) -> tuple[str, list[dict]]:

    # ── Calendar ───────────────────────────────────────────────────────────
    if is_calendar_intent(user_message) and calendar_handler is not None:
        params = detect_calendar_params(user_message)
        params["notes"] = user_message
        calendar_response = calendar_handler(params)
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": calendar_response})
        return calendar_response, history

    # ── Retrieve context ───────────────────────────────────────────────────
    if is_intro_query(user_message):
        context = get_intro_context()
    else:
        chunks = retrieve_for_query(user_message, n_results=n_chunks)
        context = format_context(chunks)

    if not context.strip():
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": FALLBACK_RESPONSE})
        return FALLBACK_RESPONSE, history

    # ── History ────────────────────────────────────────────────────────────
    history_text = ""
    for turn in history[-6:]:
        role = "Interviewer" if turn["role"] == "user" else "Me"
        history_text += f"{role}: {turn['content']}\n"

    # ── Voice instruction ──────────────────────────────────────────────────
    voice_note = (
        "\nVOICE MODE: Answer in maximum 2 sentences. "
        "No lists. No markdown. Natural spoken language only.\n"
        if is_voice else
        "\nCHAT MODE: Answer in maximum 5 sentences. No bullet points. No markdown.\n"
    )

    full_prompt = (
        SYSTEM_PROMPT.format(context=context, history=history_text)
        + voice_note
        + f"\nInterviewer: {user_message}\nMe:"
    )

    # ── Generate ───────────────────────────────────────────────────────────
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=150 if is_voice else 1024,
            )
        )
        reply = response.text.strip()

        # Strip any third-person references that slipped through
        reply = reply.replace("Bhargav has", "I have")
        reply = reply.replace("Bhargav is", "I am")
        reply = reply.replace("Bhargav built", "I built")
        reply = reply.replace("Bhargav did", "I did")
        reply = reply.replace("He has", "I have")
        reply = reply.replace("He is", "I am")
        reply = reply.replace("he has", "I have")
        reply = reply.replace("he is", "I am")
        reply = reply.replace("The candidate", "I")
        reply = reply.replace("the candidate", "I")

    except Exception as e:
        reply = f"I encountered an error: {str(e)}"

    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": reply})

    return reply, history