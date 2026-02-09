from fastapi import APIRouter, Depends, HTTPException, Body
from typing import Dict, Any, List
from app.supabase_client import get_client
from app.routers.auth import get_current_user

router = APIRouter(
    prefix="/contacts",
    tags=["contacts"]
)

@router.get("/")
async def list_contacts(user: Dict[str, Any] = Depends(get_current_user)):
    """List all contacts."""
    client = get_client()
    result = client.table("contacts").select("*").eq("user_id", user.id).execute()
    return result.data

@router.post("/")
async def create_contact(
    contact_data: Dict[str, Any] = Body(...),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Create a new contact."""
    client = get_client()
    
    # Validate required fields
    if "email" not in contact_data:
        raise HTTPException(status_code=400, detail="Email is required")
        
    # Prepare data
    new_contact = {
        "user_id": user.id,
        "email": contact_data["email"],
        "name": contact_data.get("name"),
        "company": contact_data.get("company"),
        "phone_number": contact_data.get("phone"), # Map 'phone' from frontend to 'phone_number'
        "tags": contact_data.get("tags", []),
        "metadata": {} 
    }
    
    try:
        result = client.table("contacts").insert(new_contact).execute()
        return result.data[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{id}")
async def get_contact(id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Get contact details with history."""
    client = get_client()
    contact = client.table("contacts").select("*").eq("id", id).eq("user_id", user.id).single().execute()
    
    if not contact.data:
        raise HTTPException(status_code=404, detail="Contact not found")
        
    # Fetch history (conversations)
    history = client.table("conversations").select("*").eq("contact_id", id).eq("user_id", user.id).order("created_at", desc=True).execute()
    
    return {
        **contact.data,
        "history": history.data
    }

@router.put("/{id}")
async def update_contact(
    id: str, 
    contact_data: Dict[str, Any] = Body(...),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Update contact metadata."""
    client = get_client()
    # Sanitize input - map frontend 'phone' to backend 'phone_number'
    allowed_fields = ["name", "email", "company", "timezone", "tags", "metadata", "phone_number"]
    update_data = {}
    for k, v in contact_data.items():
        if k == "phone":
            update_data["phone_number"] = v
        elif k in allowed_fields:
            update_data[k] = v
    
    result = client.table("contacts").update(update_data).eq("id", id).eq("user_id", user.id).execute()
    return result.data

@router.delete("/{id}")
async def delete_contact(id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Delete a contact."""
    client = get_client()
    result = client.table("contacts").delete().eq("id", id).eq("user_id", user.id).execute()
    return {"message": "Contact deleted", "deleted": len(result.data) > 0 if result.data else False}
