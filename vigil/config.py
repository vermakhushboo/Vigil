"""Vigil — Configuration from environment variables."""
import logging
from pathlib import Path

from pydantic_settings import BaseSettings

logger = logging.getLogger("vigil.config")


class Settings(BaseSettings):
    # App
    app_name: str = "Vigil"
    port: int = 8000
    debug: bool = False

    # Elasticsearch
    elasticsearch_url: str = "http://elasticsearch:9200"

    # Mistral (via NVIDIA API)
    mistral_api_key: str = ""

    # ElevenLabs (Voice)
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""

    # Twilio (Phone)
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""
    oncall_phone_number: str = ""

    # GitHub
    github_token: str = ""
    github_repo: str = ""

    # Public URL for Twilio webhooks
    app_base_url: str = "http://localhost:8000"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()


# ─── Model Constants ───
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
MODEL_LARGE = "mistralai/mistral-large-3-675b-instruct-2512"
MODEL_SMALL = "mistralai/mistral-small-3.1-24b-instruct-2503"


# ─── Singleton Clients ───

_llm_client = None
_llm_async_client = None
_elevenlabs_client = None


def get_llm_client():
    """Singleton synchronous OpenAI client for NVIDIA API."""
    global _llm_client
    if _llm_client is None:
        from openai import OpenAI
        _llm_client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=settings.mistral_api_key)
    return _llm_client


def get_async_llm_client():
    """Singleton async OpenAI client for NVIDIA API."""
    global _llm_async_client
    if _llm_async_client is None:
        from openai import AsyncOpenAI
        _llm_async_client = AsyncOpenAI(base_url=NVIDIA_BASE_URL, api_key=settings.mistral_api_key)
    return _llm_async_client


def get_elevenlabs_client():
    """Singleton ElevenLabs client, or None if not configured."""
    global _elevenlabs_client
    if not settings.elevenlabs_api_key:
        return None
    if _elevenlabs_client is None:
        from elevenlabs import ElevenLabs
        _elevenlabs_client = ElevenLabs(api_key=settings.elevenlabs_api_key)
    return _elevenlabs_client


# ─── Static Paths ───
STATIC_DIR = Path(__file__).parent / "static"
AUDIO_DIR = STATIC_DIR / "audio"
