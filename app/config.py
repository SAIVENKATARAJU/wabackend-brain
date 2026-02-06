from typing import Literal, Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # LLM Provider selection
    LLM_PROVIDER: Literal["openai", "azure_openai", "gemini"] = "openai"

    # App Auth Settings
    APP_API_KEY: Optional[str] = None
    LOGFIRE_TOKEN: Optional[str] = None  # Also reads LOG_FIRE_TOKEN

    # OpenAI settings
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    
    # Azure OpenAI settings
    AZURE_OPENAI_API_KEY: Optional[str] = None
    AZURE_OPENAI_ENDPOINT: Optional[str] = None
    AZURE_OPENAI_DEPLOYMENT: Optional[str] = None
    AZURE_OPENAI_API_VERSION: str = "2024-02-15-preview"
    
    # Gemini settings
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-1.5-flash"
    
    # WhatsApp Cloud API settings
    WHATSAPP_ACCESS_TOKEN: Optional[str] = None
    WHATSAPP_PHONE_NUMBER_ID: Optional[str] = None
    WHATSAPP_API_VERSION: str = "v21.0"
    WEBHOOK_VERIFY_TOKEN: Optional[str] = None

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
