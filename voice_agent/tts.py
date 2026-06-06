"""
Text-to-Speech module.

Primary: ElevenLabs (natural voice, ~300ms latency with streaming)
Fallback: gTTS (free, higher latency)

Install:  pip install elevenlabs gtts
Set env:  ELEVENLABS_API_KEY=...
          ELEVENLABS_VOICE_ID=... (optional, defaults to "Rachel")
"""

import os
import io
from dotenv import load_dotenv

load_dotenv()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Rachel


# ── ElevenLabs TTS ──────────────────────────────────────────────────────────────

def synthesize_elevenlabs(text: str) -> bytes:
    """
    Convert text to speech using ElevenLabs.
    Returns MP3 audio bytes.
    """
    try:
        from elevenlabs.client import ElevenLabs
        from elevenlabs import VoiceSettings

        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

        audio = client.text_to_speech.convert(
            voice_id=ELEVENLABS_VOICE_ID,
            text=text,
            model_id="eleven_turbo_v2",        # Lowest latency model
            voice_settings=VoiceSettings(
                stability=0.5,
                similarity_boost=0.75,
                style=0.0,
                use_speaker_boost=True,
            ),
            output_format="mp3_44100_128",
        )

        return b"".join(audio)

    except Exception as e:
        print(f"[TTS] ElevenLabs error: {e}, falling back to gTTS")
        return synthesize_gtts(text)


def synthesize_gtts(text: str) -> bytes:
    """
    Fallback TTS using gTTS (Google). Returns MP3 bytes.
    """
    try:
        from gtts import gTTS
        buf = io.BytesIO()
        tts = gTTS(text=text, lang="en", slow=False)
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    except Exception as e:
        print(f"[TTS] gTTS fallback error: {e}")
        return b""


def synthesize(text: str) -> bytes:
    """
    Main TTS entry point. Uses ElevenLabs if key present, else gTTS.
    """
    if ELEVENLABS_API_KEY:
        return synthesize_elevenlabs(text)
    return synthesize_gtts(text)


# ── Streaming TTS via ElevenLabs ────────────────────────────────────────────────

def stream_synthesize(text: str):
    """
    Generator that yields audio chunks for real-time streaming playback.
    Used by Vapi/Retell webhooks that support audio streaming.
    """
    try:
        from elevenlabs.client import ElevenLabs
        from elevenlabs import VoiceSettings

        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

        audio_stream = client.text_to_speech.convert_as_stream(
            voice_id=ELEVENLABS_VOICE_ID,
            text=text,
            model_id="eleven_turbo_v2",
            voice_settings=VoiceSettings(
                stability=0.5,
                similarity_boost=0.75,
            ),
            output_format="mp3_44100_128",
        )

        for chunk in audio_stream:
            if chunk:
                yield chunk

    except Exception as e:
        print(f"[TTS] Streaming error: {e}")
        # Fallback: yield entire gTTS audio as single chunk
        yield synthesize_gtts(text)