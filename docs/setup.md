# Setup Guide

## 1. Install dependencies

```bash
pip install -r requirements.txt
pip install fastapi uvicorn deepgram-sdk elevenlabs gtts
```

## 2. Configure environment

```bash
cp .env.example .env
# Fill in your API keys in .env
```

## 3. Run RAG ingestion (one-time)

```bash
cd assignment/
python -m rag.ingest
```

This reads all files from `data/resume/`, `data/github_repos/`, and `data/commits/`,
chunks them, embeds with `all-MiniLM-L6-v2`, and stores in ChromaDB at `vector_db/`.

## 4. Run the Chat App

```bash
uvicorn chat_app.app:app --host 0.0.0.0 --port 8501
```

Visit `http://localhost:8501` to chat.

## 5. Set up Google Calendar (optional but recommended)

```bash
# Place credentials.json from Google Cloud Console into calendar/
python -m calendar.calendar_tool --auth
# Opens browser for one-time OAuth consent → saves token.json
python -m calendar.calendar_tool --test   # Verify free slots are returned
```

## 6. Run the Voice Agent

```bash
uvicorn voice_agent.voice:app --host 0.0.0.0 --port 8000
```

For local development, expose with ngrok:
```bash
ngrok http 8000
# Copy the https URL → paste into Vapi assistant webhook settings
```

### Vapi Dashboard Setup
1. Go to https://vapi.ai → Create Assistant
2. Set **Server URL** to `https://<your-ngrok-url>/voice/message`
3. Set **STT** to Deepgram Nova-2
4. Set **TTS** to ElevenLabs, paste your API key + Voice ID
5. Set **First Message URL** to `https://<your-ngrok-url>/voice/start`
6. Assign a phone number → you're live

## 7. Run Evaluations

```bash
python -m evals.eval --mode all
# Results saved to evals/results/
```

## File Structure

```
assignment/
├── rag/
│   ├── ingest.py          # One-time: chunk + embed + store
│   ├── vector_store.py    # ChromaDB client + embedding model
│   └── retriever.py       # Query → top-k chunks
├── chat_app/
│   ├── app.py             # Streamlit UI
│   ├── chatbot.py         # Gemini + RAG + calendar routing
│   └── prompts.py         # System prompt + fallback strings
├── voice_agent/
│   ├── voice.py           # FastAPI webhooks for Vapi
│   ├── stt.py             # Deepgram STT (used if self-hosting)
│   └── tts.py             # ElevenLabs TTS (used if self-hosting)
├── calendar/
│   ├── calendar_tool.py   # Google Calendar + Calendly fallback
│   └── credentials.json   # (you add this — from Google Cloud Console)
├── evals/
│   ├── eval.py            # Full eval suite
│   ├── questions.json     # Golden Q&A set
│   └── results/           # JSON result files
├── data/
│   ├── resume/            # resume.pdf
│   ├── github_repos/      # cloned repos
│   └── commits/           # *_commits.txt files
├── vector_db/             # ChromaDB persistent storage
├── .env                   # Your secrets (never commit)
└── .env.example           # Template
```

## Cost Breakdown (approximate)

| Component | Cost |
|-----------|------|
| Gemini 1.5 Flash (chat) | ~$0.000075 / 1K tokens → **~$0.002 per chat session** |
| ElevenLabs Turbo v2 (TTS) | ~$0.0003 / 1K chars → **~$0.003 per call minute** |
| Deepgram Nova-2 (STT) | $0.0043 / minute → **~$0.013 per 3-min call** |
| ChromaDB | Free (local) |
| **Per chat session** | **~$0.002** |
| **Per voice call (3 min)** | **~$0.016** |