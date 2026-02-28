"""Vigil — Configuration from environment variables."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    app_name: str = "Vigil"
    port: int = 8000
    debug: bool = False

    # Elasticsearch
    elasticsearch_url: str = "http://elasticsearch:9200"

    # Mistral (Phase 2)
    mistral_api_key: str = ""

    # ElevenLabs (Phase 4)
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""

    # Twilio (Phase 4)
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""
    oncall_phone_number: str = ""

    # GitHub (Phase 2)
    github_token: str = ""
    github_repo: str = ""

    # Public URL for Twilio webhooks
    app_base_url: str = "http://localhost:8000"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
