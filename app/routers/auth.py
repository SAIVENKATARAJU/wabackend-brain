import secrets
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.supabase_client import get_client

router = APIRouter(
    prefix="/auth",
    tags=["auth"]
)

security = HTTPBearer(auto_error=False)


def _cookie_kwargs() -> Dict[str, Any]:
    return {
        "httponly": True,
        "secure": settings.COOKIE_SECURE,
        "samesite": settings.COOKIE_SAMESITE,
        "domain": settings.COOKIE_DOMAIN,
        "path": "/",
    }


def _safe_next_path(next_path: Optional[str]) -> str:
    if not next_path:
        return "/dashboard"
    return next_path if next_path.startswith("/") else "/dashboard"


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    access_token: Optional[str] = Cookie(default=None),
):
    """
    Verify auth token via Supabase.

    Accepts either:
    - Bearer token (legacy)
    - HttpOnly cookie `access_token` (backend-managed session)
    """
    token = credentials.credentials if credentials else access_token

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    client = get_client()

    try:
        user = client.auth.get_user(token)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user.user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get("/google/start")
async def google_start(request: Request, next: str = Query(default="/dashboard")):
    """Start Google OAuth on backend, then return to backend callback."""
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_ID is not configured")

    state = secrets.token_urlsafe(32)
    next_path = _safe_next_path(next)

    redirect_uri = settings.GOOGLE_REDIRECT_URI or str(request.url_for("google_callback"))

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }

    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    response = RedirectResponse(auth_url, status_code=302)
    cookie_opts = _cookie_kwargs()
    response.set_cookie("oauth_state", state, max_age=600, **cookie_opts)
    response.set_cookie("oauth_next", next_path, max_age=600, **cookie_opts)
    return response


@router.get("/google/callback", name="google_callback")
async def google_callback(
    request: Request,
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    oauth_state: Optional[str] = Cookie(default=None),
    oauth_next: Optional[str] = Cookie(default=None),
):
    """
    Backend OAuth callback:
    1) Exchange Google auth code for id_token
    2) Exchange id_token for Supabase access_token (server-side)
    3) Set auth cookie and redirect to frontend
    """
    frontend_base = settings.FRONTEND_URL.rstrip("/")
    next_path = _safe_next_path(oauth_next)

    if error:
        return RedirectResponse(f"{frontend_base}/login?error=oauth_{error}", status_code=302)

    if not code:
        return RedirectResponse(f"{frontend_base}/login?error=missing_code", status_code=302)

    if not oauth_state or not state or oauth_state != state:
        return RedirectResponse(f"{frontend_base}/login?error=invalid_state", status_code=302)

    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google OAuth credentials are not configured")

    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="Supabase auth settings are not configured")

    redirect_uri = settings.GOOGLE_REDIRECT_URI or str(request.url_for("google_callback"))

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            token_resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            token_resp.raise_for_status()
            google_tokens = token_resp.json()
            id_token = google_tokens.get("id_token")

            if not id_token:
                return RedirectResponse(f"{frontend_base}/login?error=missing_id_token", status_code=302)

            supabase_token_url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/token?grant_type=id_token"
            supabase_resp = await client.post(
                supabase_token_url,
                headers={
                    "apikey": settings.SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "provider": "google",
                    "id_token": id_token,
                },
            )
            supabase_resp.raise_for_status()
            supabase_session = supabase_resp.json()
    except httpx.HTTPError as exc:
        return RedirectResponse(f"{frontend_base}/login?error=oauth_exchange_failed", status_code=302)

    access_token = supabase_session.get("access_token")
    if not access_token:
        return RedirectResponse(f"{frontend_base}/login?error=missing_access_token", status_code=302)

    response = RedirectResponse(f"{frontend_base}{next_path}", status_code=302)
    cookie_opts = _cookie_kwargs()

    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=settings.COOKIE_MAX_AGE_SECONDS,
        **cookie_opts,
    )
    response.delete_cookie("oauth_state", **cookie_opts)
    response.delete_cookie("oauth_next", **cookie_opts)
    return response


@router.post("/session")
async def create_session(
    payload: Dict[str, str],
    response: Response,
):
    """
    Set backend-managed auth cookie from a Supabase access token.
    Useful during migration from client-side auth to backend-managed sessions.
    """
    token = payload.get("access_token")
    if not token:
        raise HTTPException(status_code=400, detail="access_token is required")

    response.set_cookie(
        key="access_token",
        value=token,
        max_age=settings.COOKIE_MAX_AGE_SECONDS,
        **_cookie_kwargs(),
    )
    return {"status": "ok"}


@router.get("/me")
async def get_me(user=Depends(get_current_user)):
    """Get current user profile."""
    return user


@router.post("/logout")
async def logout(response: Response):
    """Logout endpoint (clears backend auth cookie)."""
    response.delete_cookie(key="access_token", domain=settings.COOKIE_DOMAIN, path="/")
    return {"message": "Logged out successfully"}
