"""
Voice Agent — FastAPI webhook server for Vapi.ai

Flow:
  Caller dials Vapi number
  → Vapi sends POST /voice/start   (call start)
  → Vapi sends POST /voice/message (each user utterance)
  → This server does RAG + Gemini → returns text reply
  → Vapi converts reply text → speech via ElevenLabs (configured in Vapi dashboard)

Setup:
  1. Create account at https://vapi.ai
  2. Create an assistant, set webhook URL to https://<your-domain>/voice/message
  3. In Vapi assistant settings:
       - STT: Deepgram Nova-2
       - TTS: ElevenLabs (paste ELEVENLABS_API_KEY + voice ID in Vapi dashboard)
       - First message: handled by /voice/start endpoint below
  4. Assign a phone number to the assistant in Vapi dashboard
  5. Run: uvicorn voice_agent.voice:app --host 0.0.0.0 --port 8000
  6. Expose with: ngrok http 8000   (for local dev)

Install: pip install fastapi uvicorn python-dotenv
"""

import os
import sys
import time
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chat_app.chatbot import chat
from cal.calendar_tool import handle_calendar_request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Voice Agent – AI Persona")

# Per-call conversation history
call_histories: dict[str, list] = {}

INTRO_MESSAGE = (
    "Hi! I'm the AI representative for the candidate. "
    "I can answer questions about their background, skills, projects, and experience, "
    "and I can check availability and book a call if you'd like. "
    "What would you like to know?"
)


@app.get("/")
async def health():
    return {"status": "ok", "service": "AI Persona Voice Agent"}


@app.post("/voice/start")
async def voice_start(request: Request):
    """Called by Vapi when a new call starts."""
    try:
        body = await request.json()
        call_id = body.get("call", {}).get("id", "unknown")
        call_histories[call_id] = []
        logger.info(f"[CALL START] call_id={call_id}")
    except Exception as e:
        logger.error(f"[CALL START ERROR] {e}")

    return JSONResponse({"assistant": {"firstMessage": INTRO_MESSAGE}})


@app.post("/voice/message")
async def voice_message(request: Request):
    """Called by Vapi for each user utterance. Returns assistant reply text."""
    t_start = time.time()

    try:
        body = await request.json()

        call_id = body.get("call", {}).get("id", "default")
        message_type = body.get("message", {}).get("type", "")

        if message_type != "transcript":
            return JSONResponse({"response": ""})

        user_text = body.get("message", {}).get("transcript", "").strip()

        if not user_text:
            return JSONResponse({"response": "I didn't catch that, could you repeat?"})

        logger.info(f"[USER] call={call_id} | text={user_text[:80]}")

        if call_id not in call_histories:
            call_histories[call_id] = []

        reply, updated_history = chat(
            user_message=user_text,
            history=call_histories[call_id],
            calendar_handler=handle_calendar_request,
            n_chunks=4,
            is_voice=True
        )

        call_histories[call_id] = updated_history

        latency_ms = int((time.time() - t_start) * 1000)
        logger.info(f"[REPLY] call={call_id} | latency={latency_ms}ms | reply={reply[:80]}")

        return JSONResponse({"response": reply})

    except Exception as e:
        logger.error(f"[VOICE MESSAGE ERROR] {e}")
        return JSONResponse({
            "response": "I'm sorry, I had a brief issue. Could you repeat your question?"
        })


@app.post("/voice/end")
async def voice_end(request: Request):
    """Called by Vapi when call ends. Clean up history."""
    try:
        body = await request.json()
        call_id = body.get("call", {}).get("id", "")
        call_histories.pop(call_id, None)
        logger.info(f"[CALL END] call_id={call_id}")
    except Exception as e:
        logger.error(f"[CALL END ERROR] {e}")
    return JSONResponse({"status": "ok"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "voice_agent.voice:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=False
    )