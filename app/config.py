from typing import Literal, Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # LLM Provider selection
    LLM_PROVIDER: Literal["openai", "azure_openai", "gemini"] = "openai"

    # App Auth Settings
    APP_API_KEY: Optional[str] = None
    LOG_FIRE_TOKEN: Optional[str] = None

    # OpenAI settings
    OPENAI_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    
    # Azure OpenAI settings
    AZURE_OPENAI_KEY: Optional[str] = None
    AZURE_OPENAI_ENDPOINT: Optional[str] = None
    AZURE_OPENAI_DEPLOYMENT_NAME: Optional[str] = None
    AZURE_OPENAI_API_VERSION: str = "2024-02-15-preview"
    
    # Gemini settings
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL_NAME: str = "gemini-3-flash-preview"
    
    # WhatsApp Cloud API settings
    WHATSAPP_ACCESS_TOKEN: Optional[str] = None
    WHATSAPP_PHONE_NUMBER_ID: Optional[str] = None
    WHATSAPP_API_VERSION: str = "v21.0"
    WEBHOOK_VERIFY_TOKEN: Optional[str] = None

    # Supabase settings
    SUPABASE_URL: Optional[str] = None
    SUPABASE_SERVICE_KEY: Optional[str] = None


    # Network/SSL settings for regions where TLS interception can break cert validation
    SUPABASE_DISABLE_SSL_VERIFY: bool = False
    SUPABASE_HTTP_TIMEOUT: int = 30


    # CORS (comma-separated origins)
    CORS_ORIGINS: str = "http://localhost:3000,https://akasavani.vercel.app,https://akasavani.sdmai.org"

    # Auth cookie settings
    COOKIE_DOMAIN: Optional[str] = None
    COOKIE_SECURE: bool = True
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    COOKIE_MAX_AGE_SECONDS: int = 3600

    # Cron settings
    CRON_SECRET: str = "akasavani_cron_secret_2024"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
