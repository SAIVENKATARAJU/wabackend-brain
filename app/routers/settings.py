from fastapi import APIRouter, Depends, HTTPException, Body
from typing import Dict, Any, List, Optional
from app.supabase_client import get_client
from app.routers.auth import get_current_user
from pydantic import BaseModel

router = APIRouter(
    prefix="/settings",
    tags=["settings"]
)

class WhatsAppConfig(BaseModel):
    phone_number_id: str
    business_account_id: str
    access_token: str

@router.get("/integrations")
async def get_integrations(user: Dict[str, Any] = Depends(get_current_user)):
    """Get all connected integrations for the user."""
    client = get_client()
    result = client.table("integrations").select("*").eq("user_id", user.id).execute()
    return result.data

@router.post("/integrations/whatsapp")
async def connect_whatsapp(
    config: WhatsAppConfig,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Connect or update WhatsApp integration."""
    client = get_client()
    
    # Check if integration already exists
    existing = client.table("integrations").select("*").eq("user_id", user.id).eq("provider", "whatsapp").execute()
    
    data = {
        "user_id": user.id,
        "provider": "whatsapp",
        "access_token": config.access_token,
        "metadata": {
            "phone_number_id": config.phone_number_id,
            "business_account_id": config.business_account_id
        },
        "updated_at": "now()"
    }

    if existing.data:
        # Update
        result = client.table("integrations").update(data).eq("id", existing.data[0]["id"]).execute()
    else:
        # Insert
        result = client.table("integrations").insert(data).execute()
        
    return result.data[0]

@router.delete("/integrations/{provider}")
async def disconnect_integration(
    provider: str,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Disconnect an integration."""
    client = get_client()
    result = client.table("integrations").delete().eq("user_id", user.id).eq("provider", provider).execute()
    return {"message": "Integration disconnected"}

class UserPreferences(BaseModel):
    default_wait_time: Optional[int] = None
    max_nudges: Optional[int] = None
    default_tone: Optional[str] = None
    default_channel: Optional[str] = None
    auto_approve: Optional[bool] = None
    timezone: Optional[str] = None

@router.get("/preferences")
async def get_preferences(user: Dict[str, Any] = Depends(get_current_user)):
    """Get user preferences."""
    client = get_client()
    result = client.table("user_preferences").select("*").eq("user_id", user.id).execute()
    if result.data and len(result.data) > 0:
        return result.data[0]
    # Return defaults if no preferences exist
    return {
        "default_wait_time": 32,
        "max_nudges": 3,
        "default_tone": "warm",
        "default_channel": "email",
        "auto_approve": False,
        "timezone": "Asia/Kolkata"
    }

@router.put("/preferences")
async def update_preferences(
    prefs: UserPreferences,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Update user preferences."""
    client = get_client()
    
    existing = client.table("user_preferences").select("*").eq("user_id", user.id).execute()
    
    update_data = {k: v for k, v in prefs.dict().items() if v is not None}
    update_data["user_id"] = user.id
    
    if existing.data and len(existing.data) > 0:
        result = client.table("user_preferences").update(update_data).eq("user_id", user.id).execute()
    else:
        result = client.table("user_preferences").insert(update_data).execute()
    
    return result.data[0] if result.data else update_data
