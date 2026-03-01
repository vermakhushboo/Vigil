"""Vigil — ElevenLabs Text-to-Speech.

Converts the synthesised briefing script into spoken audio.
Audio files are saved to vigil/static/audio/ and served via FastAPI.
"""
import asyncio
import logging

from vigil.config import settings, get_elevenlabs_client, AUDIO_DIR

logger = logging.getLogger("vigil.voice.tts")

# Default voice — "Rachel" (clear, professional female voice)
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"


def _synthesize_blocking(client, text: str, voice_id: str, filepath) -> int:
    """Blocking TTS call — runs in a thread to avoid blocking the event loop."""
    audio_generator = client.text_to_speech.convert(
        text=text,
        voice_id=voice_id,
        model_id="eleven_flash_v2_5",
        output_format="mp3_44100_128",
    )

    with open(filepath, "wb") as f:
        for chunk in audio_generator:
            f.write(chunk)

    return filepath.stat().st_size


async def generate_audio(incident_id: str, text: str) -> str | None:
    """
    Convert briefing text to speech audio and save as MP3.

    Returns:
        Relative URL path to the audio file, or None if TTS is unavailable.
    """
    client = get_elevenlabs_client()
    if not client:
        logger.warning("⚠️ ELEVENLABS_API_KEY not set — TTS disabled")
        return None

    voice_id = settings.elevenlabs_voice_id or DEFAULT_VOICE_ID
    filename = f"briefing_{incident_id}.mp3"
    filepath = AUDIO_DIR / filename

    try:
        logger.info(f"🔊 [{incident_id}] Generating TTS audio (voice={voice_id})...")

        # Run blocking ElevenLabs SDK call in a thread
        file_size = await asyncio.to_thread(
            _synthesize_blocking, client, text, voice_id, filepath
        )

        logger.info(
            f"🔊 [{incident_id}] TTS audio saved: {filepath} ({file_size / 1024:.1f} KB)"
        )

        return f"/static/audio/{filename}"

    except Exception as e:
        logger.error(f"❌ [{incident_id}] TTS generation failed: {e}")
        return None
