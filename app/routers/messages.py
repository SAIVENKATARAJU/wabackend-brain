"""
Messages Router - Message status tracking and retry functionality
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from app.supabase_client import get_client
from app.routers.auth import get_current_user

router = APIRouter(
    prefix="/messages",
    tags=["messages"]
)


@router.get("/")
async def list_messages(
    conversation_id: Optional[str] = None,
    status: Optional[str] = None,
    direction: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """List messages with optional filters."""
    client = get_client()
    query = client.table("messages").select("*").eq("user_id", user.id)
    
    if conversation_id:
        query = query.eq("conversation_id", conversation_id)
    if status:
        query = query.eq("status", status)
    if direction:
        query = query.eq("direction", direction)
    
    result = query.order("created_at", desc=False).range(offset, offset + limit - 1).execute()
    return result.data


@router.get("/failed")
async def list_failed_messages(
    user: Dict[str, Any] = Depends(get_current_user)
):
    """List all failed messages for the user."""
    client = get_client()
    result = client.table("messages").select(
        "*, conversations(subject), contacts(name, phone_number)"
    ).eq("user_id", user.id).eq("status", "failed").order("created_at", desc=True).execute()
    return result.data


@router.get("/{id}")
async def get_message(id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Get a single message with full status details."""
    client = get_client()
    result = client.table("messages").select("*").eq("id", id).eq("user_id", user.id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Message not found")
    return result.data


@router.post("/{id}/retry")
async def retry_message(id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """
    Retry sending a failed message.
    
    Creates a new message record and sends via WhatsApp.
    The original failed message is kept for audit trail.
    """
    client = get_client()
    
    # 1. Get the failed message
    msg_result = client.table("messages").select("*").eq("id", id).eq("user_id", user.id).single().execute()
    
    if not msg_result.data:
        raise HTTPException(status_code=404, detail="Message not found")
    
    original_msg = msg_result.data
    
    if original_msg.get("status") not in ("failed",):
        raise HTTPException(status_code=400, detail="Only failed messages can be retried")
    
    # 2. Check retry limit
    retry_count = original_msg.get("retry_count", 0) or 0
    max_retries = original_msg.get("max_retries", 3) or 3
    
    if retry_count >= max_retries:
        raise HTTPException(
            status_code=400, 
            detail=f"Maximum retry limit ({max_retries}) reached. Please create a new message."
        )
    
    # 3. Get contact phone number
    contact_id = original_msg.get("contact_id")
    if not contact_id:
        raise HTTPException(status_code=400, detail="No contact associated with this message")
    
    contact_result = client.table("contacts").select("phone_number").eq("id", contact_id).single().execute()
    if not contact_result.data or not contact_result.data.get("phone_number"):
        raise HTTPException(status_code=400, detail="Contact phone number not found")
    
    contact_phone = contact_result.data["phone_number"]
    
    # 4. Get WhatsApp integration credentials
    integration_data = client.table("integrations").select("*").eq(
        "user_id", user.id
    ).eq("provider", "whatsapp").single().execute()
    
    if not integration_data.data:
        raise HTTPException(status_code=400, detail="WhatsApp integration not configured")
    
    integration = integration_data.data
    access_token = integration.get("access_token")
    metadata = integration.get("metadata") or {}
    phone_number_id = metadata.get("phone_number_id")
    
    if not access_token or not phone_number_id:
        raise HTTPException(status_code=400, detail="WhatsApp credentials incomplete")
    
    # 5. Retry the send using smart logic (handles 24-hour window + templates)
    from app.delivery_engine import send_smart_nudge, DeliveryError
    
    content = original_msg.get("content", "")
    
    # Build a nudge-like dict for send_smart_nudge
    nudge_data = {
        "approved_content": content,
        "conversation_id": original_msg.get("conversation_id")
    }
    
    try:
        result = await send_smart_nudge(
            client_supabase=client,
            nudge=nudge_data,
            contact_phone=contact_phone,
            access_token=access_token,
            phone_number_id=phone_number_id
        )
        
        # 6. Update the original message with new message_id and status
        client.table("messages").update({
            "status": "sent",
            "whatsapp_message_id": result.message_id,
            "retry_count": retry_count + 1,
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "error_code": None,
            "error_message": None,
            "failed_at": None
        }).eq("id", id).execute()
        
        return {
            "success": True,
            "message_id": result.message_id,
            "retry_count": retry_count + 1,
            "status": "sent"
        }
        
    except DeliveryError as e:
        # Update retry count and error info
        client.table("messages").update({
            "retry_count": retry_count + 1,
            "error_code": str(e.status_code) if e.status_code else "unknown",
            "error_message": str(e.message),
            "failed_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", id).execute()
        
        raise HTTPException(
            status_code=500,
            detail={
                "error": str(e),
                "retry_count": retry_count + 1,
                "max_retries": max_retries,
                "can_retry": (retry_count + 1) < max_retries
            }
        )
    except Exception as e:
        client.table("messages").update({
            "retry_count": retry_count + 1,
            "error_message": str(e),
            "failed_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", id).execute()
        
        raise HTTPException(status_code=500, detail=f"Retry failed: {str(e)}")


@router.get("/conversation/{conversation_id}/status-summary")
async def get_conversation_message_status(
    conversation_id: str,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get a summary of message statuses for a conversation.
    Useful for showing overall delivery health.
    """
    client = get_client()
    
    result = client.table("messages").select(
        "id, status, direction, whatsapp_message_id, error_code, error_message, retry_count, max_retries"
    ).eq("conversation_id", conversation_id).eq("user_id", user.id).eq(
        "direction", "outgoing"
    ).execute()
    
    messages = result.data or []
    
    summary = {
        "total": len(messages),
        "sent": sum(1 for m in messages if m["status"] == "sent"),
        "delivered": sum(1 for m in messages if m["status"] == "delivered"),
        "read": sum(1 for m in messages if m["status"] == "read"),
        "failed": sum(1 for m in messages if m["status"] == "failed"),
        "pending": sum(1 for m in messages if m["status"] == "pending"),
        "failed_messages": [
            {
                "id": m["id"],
                "error_code": m.get("error_code"),
                "error_message": m.get("error_message"),
                "can_retry": (m.get("retry_count", 0) or 0) < (m.get("max_retries", 3) or 3)
            }
            for m in messages if m["status"] == "failed"
        ]
    }
    
    return summary
