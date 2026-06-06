# AI Persona – Voice & Chat Agent

A fully autonomous AI persona that answers questions about the candidate, discusses GitHub projects, and books interviews — with no human in the loop.

**Live Demo**
- 💬 Chat: `https://main-chat-app-production.up.railway.app`
- 📞 Voice: Call the Vapi phone number (see submission form)

---

## What It Does

| Capability | Detail |
|-----------|--------|
| Voice Agent | Callable phone number, answers questions, books meetings |
| Chat Interface | Public URL, RAG-grounded, adversarial-resistant |
| Calendar Booking | Calendly integration with real-time availability |
| RAG Pipeline | Resume + 6 GitHub repos + commit history |
| Evals | Hallucination rate, retrieval precision, latency benchmarks |

---

## Architecture

```
Caller / Browser
      │
      ▼
┌─────────────────────────────────────────────┐
│              Railway (Cloud)                 │
│                                             │
│  ┌──────────────┐    ┌──────────────────┐   │
│  │  Voice Agent │    │   Chat App       │   │
│  │  FastAPI     │    │   FastAPI        │   │
│  │  port $PORT  │    │   port $PORT     │   │
│  └──────┬───────┘    └───────┬──────────┘   │
│         │                   │              │
│         └─────────┬─────────┘              │
│                   ▼                        │
│         ┌─────────────────┐                │
│         │   RAG Pipeline  │                │
│         │  ChromaDB +     │                │
│         │  MiniLM-L6-v2   │                │
│         └────────┬────────┘                │
│                  ▼                         │
│         ┌─────────────────┐                │
│         │  Gemini 2.5     │                │
│         │  Flash          │                │
│         └─────────────────┘                │
└─────────────────────────────────────────────┘
      │                    │
      ▼                    ▼
  Vapi.ai              Calendly
  (STT/TTS)         (Booking)
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| LLM | Gemini 2.5 Flash |
| Embeddings | `all-MiniLM-L6-v2` (sentence-transformers) |
| Vector DB | ChromaDB (persistent) |
| Voice Platform | Vapi.ai |
| STT | Deepgram Nova-2 |
| TTS | Vapi built-in |
| Web Framework | FastAPI + Uvicorn |
| Calendar | Calendly |
| Deployment | Railway |

---

## Project Structure

```
assignment/
├── rag/
│   ├── ingest.py          # Chunk, embed, store documents
│   ├── vector_store.py    # ChromaDB client
│   └── retriever.py       # Smart repo-aware retrieval
├── chat_app/
│   ├── app.py             # FastAPI chat server
│   ├── chatbot.py         # LLM + RAG pipeline
│   ├── prompts.py         # System prompts
│   └── index.html         # Chat UI
├── voice_agent/
│   └── voice.py           # Vapi webhook server
├── cal/
│   └── calendar_tool.py   # Calendly integration
├── evals/
│   ├── eval.py            # Evaluation suite
│   ├── questions.json     # Golden Q&A set
│   └── results/           # Eval outputs
├── data/
│   ├── resume/            # resume.pdf
│   ├── github_repos/      # 6 cloned repos
│   └── commits/           # commit history per repo
├── main.py                # Voice agent entry point
├── main_chat.py           # Chat app entry point
├── nixpacks.toml          # Railway build config
└── requirements.txt
```

---

## Setup

**1. Install dependencies**
```bash
pip install -r requirements.txt
```

**2. Configure environment**
```bash
cp .env.example .env
# Fill in your API keys
```

**3. Ingest data**
```bash
python -m rag.ingest
```

**4. Run locally**
```bash
# Chat app
uvicorn main_chat:app --host 0.0.0.0 --port 8501

# Voice webhook
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## Environment Variables

```
GEMINI_API_KEY        Gemini API key
ELEVENLABS_API_KEY    ElevenLabs (optional)
DEEPGRAM_API_KEY      Deepgram STT
VAPI_API_KEY          Vapi.ai
CALENDLY_LINK         Your Calendly booking URL
```

---

## RAG Design

- **Corpus**: Resume PDF + 6 GitHub repo files (README, source code, commits)
- **Chunking**: `RecursiveCharacterTextSplitter` — 1000 chars, 200 overlap
- **Embedding**: `all-MiniLM-L6-v2` — 384-dim vectors
- **Retrieval**: Repo-aware — detects project keywords, fetches README chunks directly by metadata filter before semantic search
- **Total chunks**: ~2638 across 93 source files

---

## Cost Breakdown

| Component | Cost |
|-----------|------|
| Gemini 2.5 Flash | ~$0.002 per chat session |
| Deepgram Nova-2 | ~$0.0043 per minute |
| Vapi built-in TTS | Included in Vapi plan |
| ChromaDB | Free (local/Railway) |
| Railway hosting | Free tier |
| **Per chat session** | **~$0.002** |
| **Per voice call (3 min)** | **~$0.013** |

---

## Evals Summary

| Metric | Score |
|--------|-------|
| Retrieval Precision | measured via keyword hit rate |
| Hallucination Rate | measured via Gemini judge model |
| Avg Response Latency | measured across 5 test queries |
| Booking Success Rate | Calendly link delivery rate |

Full report: `evals/results/` and `report/evaluation_report.pdf`