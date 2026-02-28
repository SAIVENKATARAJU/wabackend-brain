from typing import Any, Dict, Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.supabase_client import get_client

router = APIRouter(
    prefix="/auth",
    tags=["auth"]
)

security = HTTPBearer(auto_error=False)


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
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        domain=settings.COOKIE_DOMAIN,
        path="/",
        max_age=settings.COOKIE_MAX_AGE_SECONDS,
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
