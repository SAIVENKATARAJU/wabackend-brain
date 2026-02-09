from fastapi import APIRouter, Depends, HTTPException, Query, Body
from typing import List, Optional, Dict, Any
from app.supabase_client import get_client
from app.routers.auth import get_current_user
from app.models import StatusEnum
from app.models import StatusEnum
from datetime import datetime, timedelta, timezone

router = APIRouter(
    prefix="/conversations",
    tags=["conversations"]
)

@router.get("/")
async def list_conversations(
    status: Optional[str] = Query(None, description="Filter by status"),
    search: Optional[str] = Query(None, description="Search term"),
    tags: Optional[List[str]] = Query(None, description="Filter by tags"),
    limit: int = 50,
    offset: int = 0,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    List conversations with filtering and pagination.
    """
    client = get_client()
    
    # Start query
    query = client.table("conversations").select("*, contacts(name, email, company, tags)").eq("user_id", user.id)
    
    if status:
        query = query.eq("status", status)
    
    if search:
        # Simple search on subject or contact info (needs optimized search later)
        # Using Supabase 'ilike' or similar
        query = query.or_(f"subject.ilike.%{search}%")
        
    if tags:
        query = query.contains("tags", tags)
        
    query = query.order("last_message_at", desc=True).range(offset, offset + limit - 1)
    
    result = query.execute()
    return result.data

@router.get("/{id}")
async def get_conversation(id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Get conversation details with messages."""
    client = get_client()
    result = client.table("conversations").select("*, contacts(*)").eq("id", id).eq("user_id", user.id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Also fetch messages for this conversation
    messages_result = client.table("messages").select("*").eq("conversation_id", id).order("created_at", desc=False).execute()
    
    # Add messages to response
    result.data["messages"] = messages_result.data or []
    
    return result.data

@router.post("/{id}/snooze")
async def snooze_conversation(
    id: str, 
    duration_hours: int = Body(..., embed=True),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Snooze a conversation."""
    client = get_client()
    # Calculate next_action_at
    next_action_at = datetime.now(timezone.utc) + timedelta(hours=duration_hours)
    
    result = client.table("conversations").update({
        "status": "snoozed",
        "next_action_at": next_action_at.isoformat()
    }).eq("id", id).eq("user_id", user.id).execute()
    
    return result.data

@router.post("/{id}/close")
async def close_conversation(id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Mark conversation as closed."""
    client = get_client()
    result = client.table("conversations").update({
        "status": "closed"
    }).eq("id", id).eq("user_id", user.id).execute()
    
    return result.data

@router.patch("/{id}/tags")
async def update_tags(
    id: str, 
    tags: List[str] = Body(..., embed=True),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Update conversation tags."""
    client = get_client()
    result = client.table("conversations").update({
        "tags": tags
    }).eq("id", id).eq("user_id", user.id).execute()
    
    return result.data

@router.delete("/{id}")
async def delete_conversation(id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Delete a conversation and its associated messages."""
    client = get_client()
    
    # Delete associated messages first
    client.table("messages").delete().eq("conversation_id", id).execute()
    
    # Delete associated nudges
    client.table("nudges").delete().eq("conversation_id", id).execute()
    
    # Delete conversation
    result = client.table("conversations").delete().eq("id", id).eq("user_id", user.id).execute()
    
    return {"deleted": True}
