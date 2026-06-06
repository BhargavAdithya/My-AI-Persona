"""
Speech-to-Text module.

Primary: Deepgram Nova-2 (low latency, <300ms)
Fallback: Google Speech-to-Text

Install:  pip install deepgram-sdk
Set env:  DEEPGRAM_API_KEY=...
"""

import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")


# ── Deepgram STT ────────────────────────────────────────────────────────────────

async def transcribe_audio_deepgram(audio_bytes: bytes, mimetype: str = "audio/wav") -> str:
    """
    Transcribe raw audio bytes using Deepgram Nova-2.
    Returns transcribed text string.
    """
    try:
        from deepgram import DeepgramClient, PrerecordedOptions

        dg = DeepgramClient(DEEPGRAM_API_KEY)

        options = PrerecordedOptions(
            model="nova-2",
            language="en-US",
            smart_format=True,
            punctuate=True,
            utterances=False,
        )

        payload = {"buffer": audio_bytes, "mimetype": mimetype}
        response = await asyncio.to_thread(
            dg.listen.prerecorded.v("1").transcribe_file,
            payload,
            options
        )

        transcript = (
            response["results"]["channels"][0]
            ["alternatives"][0]["transcript"]
        )
        return transcript.strip()

    except Exception as e:
        print(f"[STT] Deepgram error: {e}")
        return ""


def transcribe_audio_sync(audio_bytes: bytes, mimetype: str = "audio/wav") -> str:
    """Synchronous wrapper for transcribe_audio_deepgram."""
    return asyncio.run(transcribe_audio_deepgram(audio_bytes, mimetype))


# ── Streaming STT via Deepgram WebSocket ────────────────────────────────────────

class StreamingSTT:
    """
    Real-time streaming STT using Deepgram Live.
    Usage:
        stt = StreamingSTT(on_transcript_callback)
        await stt.start()
        await stt.send_audio(chunk)
        await stt.stop()
    """

    def __init__(self, on_transcript):
        self.on_transcript = on_transcript
        self._connection = None

    async def start(self):
        from deepgram import DeepgramClient, LiveOptions, LiveTranscriptionEvents

        dg = DeepgramClient(DEEPGRAM_API_KEY)
        self._connection = dg.listen.live.v("1")

        options = LiveOptions(
            model="nova-2",
            language="en-US",
            smart_format=True,
            interim_results=True,
            endpointing=300,  # ms of silence before treating as utterance end
        )

        self._connection.on(
            LiveTranscriptionEvents.Transcript,
            self._handle_transcript
        )

        await self._connection.start(options)

    def _handle_transcript(self, _self, result, **kwargs):
        sentence = result.channel.alternatives[0].transcript
        if result.is_final and sentence.strip():
            self.on_transcript(sentence.strip())

    async def send_audio(self, chunk: bytes):
        if self._connection:
            await self._connection.send(chunk)

    async def stop(self):
        if self._connection:
            await self._connection.finish()