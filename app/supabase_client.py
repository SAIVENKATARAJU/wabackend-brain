"""
Supabase Client

Initializes the Supabase client for database operations.
"""

import logging

import httpx
from supabase import Client, create_client
from supabase.lib.client_options import SyncClientOptions

from app.config import settings

logger = logging.getLogger(__name__)


def get_supabase_client() -> Client:
    """Get the Supabase client instance."""
    url = settings.SUPABASE_URL
    key = settings.SUPABASE_SERVICE_KEY

    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")

    verify_ssl = not settings.SUPABASE_DISABLE_SSL_VERIFY
    timeout = settings.SUPABASE_HTTP_TIMEOUT

    # In some ISP networks, TLS interception can cause hostname mismatch failures.
    # Keep strict TLS by default, with explicit opt-out via env flag.
    httpx_client = httpx.Client(
        verify=verify_ssl,
        timeout=timeout,
        transport=httpx.HTTPTransport(retries=2),
    )

    if not verify_ssl:
        logger.warning("Supabase SSL certificate verification is DISABLED via SUPABASE_DISABLE_SSL_VERIFY")

    options = SyncClientOptions(httpx_client=httpx_client)
    return create_client(url, key, options)


# Singleton client instance
_client: Client | None = None


def get_client() -> Client:
    """Get or create the Supabase client singleton."""
    global _client
    if _client is None:
        _client = get_supabase_client()
    return _client
