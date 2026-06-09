import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from voice_agent.voice import app
from fastapi import Request
from fastapi.responses import JSONResponse


@app.get("/debug")
async def debug():
    try:
        from rag.vector_store import get_collection
        col = get_collection()
        count = col.count()
        return JSONResponse({"chunks": count, "status": "ok"})
    except Exception as e:
        return JSONResponse({"error": str(e)})


@app.post("/test")
async def test_rag(request: Request):
    try:
        body = await request.json()
        query = body.get("query", "Tell me about TALENTSCOUT")
    except Exception:
        query = "Tell me about TALENTSCOUT"

    from chat_app.chatbot import chat
    reply, _ = chat(
        user_message=query,
        history=[],
        calendar_handler=None,
        is_voice=True
    )
    return JSONResponse({"query": query, "reply": reply})