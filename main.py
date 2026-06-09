import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from voice_agent.voice import app
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse
import json


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


@app.post("/vapi-llm")
async def vapi_llm(request: Request):
    """
    Custom LLM endpoint for Vapi.
    Vapi sends the full conversation messages array.
    We extract the last user message, run RAG, return the reply.
    """
    try:
        body = await request.json()

        # Extract last user message from Vapi messages array
        messages = body.get("messages", [])
        user_text = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            user_text = block.get("text", "")
                            break
                else:
                    user_text = str(content)
                break

        if not user_text.strip():
            reply = "Could you repeat that please?"
        else:
            from chat_app.chatbot import chat
            from cal.calendar_tool import handle_calendar_request

            call_id = body.get("call", {}).get("id", "vapi-default")

            # Build history from Vapi messages
            history = []
            for msg in messages[:-1]:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            content = block.get("text", "")
                            break
                if role in ("user", "assistant") and content:
                    history.append({"role": role, "content": str(content)})

            def calendar_with_session(params: dict) -> str:
                return handle_calendar_request(params, session_id=call_id)

            reply, _ = chat(
                user_message=user_text,
                history=history,
                calendar_handler=calendar_with_session,
                n_chunks=6,
                is_voice=True
            )

        # Return in OpenAI-compatible format that Vapi expects
        return JSONResponse({
            "id": "chatcmpl-persona",
            "object": "chat.completion",
            "model": "custom",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": reply
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({
            "id": "chatcmpl-persona",
            "object": "chat.completion",
            "model": "custom",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "I had a brief issue, could you repeat that?"
                    },
                    "finish_reason": "stop"
                }
            ]
        })
    
@app.post("/vapi-llm/chat/completions")
async def vapi_llm_completions(request: Request):
    """
    Vapi appends /chat/completions to the Custom LLM URL automatically.
    This endpoint handles that exact path.
    """
    return await vapi_llm(request)