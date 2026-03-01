"""Vigil — ElevenLabs Speech-to-Text.

Transcribes engineer speech (from Twilio call audio)
into text for the conversational Q&A loop.
"""
import asyncio
import logging
from pathlib import Path

from vigil.config import get_elevenlabs_client

logger = logging.getLogger("vigil.voice.stt")


def _transcribe_file_blocking(client, audio_path: Path) -> str:
    """Blocking STT call — runs in a thread to avoid blocking the event loop."""
    with open(audio_path, "rb") as audio_file:
        result = client.speech_to_text.convert(
            file=audio_file,
            model_id="scribe_v1",
            language_code="en",
        )
    return result.text


def _transcribe_bytes_blocking(client, audio_bytes: bytes) -> str:
    """Blocking STT call for raw bytes — runs in a thread."""
    result = client.speech_to_text.convert(
        file=audio_bytes,
        model_id="scribe_v1",
        language_code="en",
    )
    return result.text


async def transcribe_audio(audio_path: str) -> str | None:
    """Transcribe an audio file to text using ElevenLabs Scribe."""
    client = get_elevenlabs_client()
    if not client:
        logger.warning("⚠️ ELEVENLABS_API_KEY not set — STT disabled")
        return None

    path = Path(audio_path)
    if not path.exists():
        logger.error(f"Audio file not found: {audio_path}")
        return None

    try:
        logger.info(f"🎙️ Transcribing audio: {audio_path}")
        transcript = await asyncio.to_thread(_transcribe_file_blocking, client, path)
        logger.info(f"🎙️ Transcript: {transcript[:100]}...")
        return transcript
    except Exception as e:
        logger.error(f"❌ STT transcription failed: {e}")
        return None


async def transcribe_audio_bytes(audio_bytes: bytes) -> str | None:
    """Transcribe audio bytes directly (e.g., from a Twilio recording)."""
    client = get_elevenlabs_client()
    if not client:
        logger.warning("⚠️ ELEVENLABS_API_KEY not set — STT disabled")
        return None

    try:
        logger.info(f"🎙️ Transcribing {len(audio_bytes)} bytes of audio...")
        transcript = await asyncio.to_thread(_transcribe_bytes_blocking, client, audio_bytes)
        logger.info(f"🎙️ Transcript: {transcript[:100]}...")
        return transcript
    except Exception as e:
        logger.error(f"❌ STT transcription failed: {e}")
        return None
