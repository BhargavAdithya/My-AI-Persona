import os
import sys
import uuid
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chat_app.chatbot import chat
from cal.calendar_tool import handle_calendar_request

app = FastAPI(title="AI Persona Chat")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

sessions: dict[str, list] = {}


class MessageRequest(BaseModel):
    message: str
    session_id: str


@app.get("/", response_class=HTMLResponse)
async def index():
    with open(os.path.join(os.path.dirname(__file__), "index.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.post("/chat")
async def chat_endpoint(req: MessageRequest):
    session_id = req.session_id or str(uuid.uuid4())

    if session_id not in sessions:
        sessions[session_id] = []

    def calendar_with_session(params: dict) -> str:
            return handle_calendar_request(params, session_id=session_id)

    reply, updated_history = chat(
        user_message=req.message,
        history=sessions[session_id],
        calendar_handler=calendar_with_session,
        n_chunks=6
    )

    sessions[session_id] = updated_history

    return JSONResponse({
        "reply": reply,
        "session_id": session_id
    })


@app.delete("/chat/{session_id}")
async def clear_session(session_id: str):
    sessions.pop(session_id, None)
    return JSONResponse({"status": "cleared"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "chat_app.app:app",
        host="0.0.0.0",
        port=8501,
        reload=False
    )