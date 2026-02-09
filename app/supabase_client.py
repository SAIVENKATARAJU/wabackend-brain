"""
Supabase Client

Initializes the Supabase client for database operations.
"""

from supabase import create_client, Client
from app.config import settings


def get_supabase_client() -> Client:
    """Get the Supabase client instance."""
    url = settings.SUPABASE_URL
    key = settings.SUPABASE_SERVICE_KEY
    
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
    
    return create_client(url, key)


# Singleton client instance
_client: Client | None = None


def get_client() -> Client:
    """Get or create the Supabase client singleton."""
    global _client
    if _client is None:
        _client = get_supabase_client()
    return _client
