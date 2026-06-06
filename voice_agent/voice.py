import os
import sys
import time
import logging

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv(os.path.join(BASE_DIR, ".env"))

from chat_app.chatbot import chat
from cal.calendar_tool import handle_calendar_request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Voice Agent – AI Persona")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

call_histories: dict[str, list] = {}

INTRO_MESSAGE = (
    "Hi! I'm the AI representative for the candidate. "
    "I can answer questions about their background, skills, and projects, "
    "and I can also schedule a call if you'd like. "
    "What would you like to know?"
)


@app.get("/")
async def health():
    return {"status": "ok", "service": "AI Persona Voice Agent"}


@app.post("/voice/start")
async def voice_start(request: Request):
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
    t_start = time.time()
    try:
        body = await request.json()
        logger.info(f"[RAW BODY] {str(body)[:300]}")

        call_id = body.get("call", {}).get("id", "default")
        message_obj = body.get("message", {})
        message_type = message_obj.get("type", "")

        # ── Extract user text from all Vapi formats ────────────────────
        user_text = ""

        if message_type == "transcript":
            role = message_obj.get("role", "")
            # Only respond to user transcripts, not assistant
            if role == "assistant":
                return JSONResponse({"response": ""})
            user_text = message_obj.get("transcript", "").strip()

        elif message_type == "conversation-update":
            messages = message_obj.get("conversation", [])
            for m in reversed(messages):
                if m.get("role") == "user":
                    user_text = m.get("content", "").strip()
                    break

        elif message_type == "function-call":
            # Not needed but handle gracefully
            return JSONResponse({"result": ""})

        else:
            # Try all possible fields
            user_text = (
                message_obj.get("transcript", "") or
                message_obj.get("text", "") or
                message_obj.get("content", "") or
                body.get("transcript", "") or
                ""
            ).strip()

        if not user_text:
            logger.warning(f"[VOICE] Empty text. type={message_type}")
            return JSONResponse({"response": ""})

        logger.info(f"[USER] call={call_id} | text={user_text}")

        if call_id not in call_histories:
            call_histories[call_id] = []

        reply, updated_history = chat(
            user_message=user_text,
            history=call_histories[call_id],
            calendar_handler=handle_calendar_request,
            n_chunks=6,
            is_voice=True
        )

        call_histories[call_id] = updated_history

        latency_ms = int((time.time() - t_start) * 1000)
        logger.info(f"[REPLY] call={call_id} | latency={latency_ms}ms | reply={reply}")

        return JSONResponse({"response": reply})

    except Exception as e:
        logger.error(f"[VOICE ERROR] {e}", exc_info=True)
        return JSONResponse({
            "response": "I had a brief issue, could you repeat that?"
        })


@app.post("/voice/end")
async def voice_end(request: Request):
    try:
        body = await request.json()
        call_id = body.get("call", {}).get("id", "")
        call_histories.pop(call_id, None)
        logger.info(f"[CALL END] call_id={call_id}")
    except Exception as e:
        logger.error(f"[CALL END ERROR] {e}")
    return JSONResponse({"status": "ok"})


@app.get("/debug")
async def debug():
    try:
        from rag.vector_store import get_collection
        collection = get_collection()
        count = collection.count()
        return JSONResponse({
            "status": "ok",
            "vector_db_chunks": count,
            "cwd": os.getcwd()
        })
    except Exception as e:
        return JSONResponse({"error": str(e)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "voice_agent.voice:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=False
    )