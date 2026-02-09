from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any
from app.supabase_client import get_client

router = APIRouter(
    prefix="/auth",
    tags=["auth"]
)

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Verify the JWT token with Supabase or Mock it for dev.
    """
    token = credentials.credentials
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
    except Exception as e:
        # Fallback for dev/mock if needed, but for now strict auth
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

@router.get("/me")
async def get_me(user = Depends(get_current_user)):
    """Get current user profile."""
    return user

@router.post("/logout")
async def logout():
    """Logout endpoint (client handles token removal)."""
    return {"message": "Logged out successfully"}
