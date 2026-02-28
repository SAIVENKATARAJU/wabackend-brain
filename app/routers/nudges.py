from fastapi import APIRouter, Depends, HTTPException, Body
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from app.supabase_client import get_client
from app.routers.auth import get_current_user
from pydantic import BaseModel

router = APIRouter(
    prefix="/nudges",
    tags=["nudges"]
)

class CreateNudgeRequest(BaseModel):
    contact_id: str
    subject: str
    content: str
    channel: str = "email"
    tone: str = "warm"
    scheduled_at: Optional[str] = None
    max_escalations: int = 2
    recurrence_hours: int = 24
    recurrence_minutes: Optional[int] = None  # For testing - overrides hours if set

class UpdateNudgeRequest(BaseModel):
    channel: Optional[str] = None
    tone: Optional[str] = None
    content: Optional[str] = None
    max_escalations: Optional[int] = None
    recurrence_hours: Optional[int] = None
    recurrence_minutes: Optional[int] = None  # For testing - overrides hours if set
    scheduled_at: Optional[str] = None
    status: Optional[str] = None

@router.post("/")
async def create_nudge(
    request: CreateNudgeRequest,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Create a new nudge and conversation."""
    client = get_client()
    
    # 1. Create Conversation
    import uuid
    conversation_data = {
        "user_id": user.id,
        "contact_id": request.contact_id,
        "subject": request.subject,
        "status": "pending",
        "channel": request.channel,
        "thread_id": str(uuid.uuid4()), # Generate a new thread ID for outbound conversations
        "last_message_at": datetime.utcnow().isoformat(),
        # "last_outgoing_text": request.content # Optional: set this immediately or wait for send? 
        # For a planned nudge, maybe we don't set last_outgoing_text yet until it's sent.
    }
    conv_result = client.table("conversations").insert(conversation_data).execute()
    conversation_id = conv_result.data[0]["id"]
    
    # 2. Create Nudge
    nudge_data = {
        "user_id": user.id,
        "conversation_id": conversation_id,
        "contact_id": request.contact_id,
        "channel": request.channel,
        "status": "pending",
        "tone": request.tone,
        "draft_content": request.content,
        "scheduled_at": request.scheduled_at or (datetime.utcnow() + timedelta(hours=24)).isoformat(),
        "max_escalations": request.max_escalations,
        "recurrence_hours": request.recurrence_hours,
        "recurrence_minutes": request.recurrence_minutes
    }
    
    nudge_result = client.table("nudges").insert(nudge_data).execute()
    
    return nudge_result.data[0]

@router.get("/")
async def list_nudges(
    status: Optional[str] = None, 
    conversation_id: Optional[str] = None,
    limit: int = 50, 
    offset: int = 0,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """List nudges filtered by status or conversation."""
    client = get_client()
    query = client.table("nudges").select("*, contacts(name, email), conversations(subject)").eq("user_id", user.id)
    
    if conversation_id:
        query = query.eq("conversation_id", conversation_id)
        # If conversation_id is provided, we default to showing all statuses unless specified
        if status:
            query = query.eq("status", status)
    else:
        # Default behavior: show pending nudges if no specific filter
        target_status = status or "pending"
        query = query.eq("status", target_status)
        
    result = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
    return result.data

@router.get("/{id}")
async def get_nudge(id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Get nudge details."""
    client = get_client()
    result = client.table("nudges").select("*, contacts(*), conversations(*)").eq("id", id).eq("user_id", user.id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Nudge not found")
    return result.data

@router.get("/{id}/debug")
async def debug_nudge(id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Debug endpoint to check nudge timezone info."""
    client = get_client()
    result = client.table("nudges").select("id, status, scheduled_at").eq("id", id).eq("user_id", user.id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Nudge not found")
    
    from datetime import datetime, timezone
    now_utc = datetime.now(timezone.utc)
    scheduled_at_raw = result.data.get("scheduled_at")
    
    return {
        "nudge_id": result.data.get("id"),
        "status": result.data.get("status"),
        "scheduled_at_raw": scheduled_at_raw,
        "current_utc": now_utc.isoformat(),
        "comparison": f"scheduled_at <= now_utc: {scheduled_at_raw} <= {now_utc.isoformat()}" if scheduled_at_raw else "no scheduled_at"
    }

@router.post("/{id}/approve")
async def approve_nudge(id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Approve a nudge draft."""
    client = get_client()
    
    # First, get the nudge to find its conversation_id
    nudge = client.table("nudges").select("conversation_id, draft_content").eq("id", id).eq("user_id", user.id).single().execute()
    
    if not nudge.data:
        raise HTTPException(status_code=404, detail="Nudge not found")
    
    conversation_id = nudge.data.get("conversation_id")
    draft_content = nudge.data.get("draft_content")
    
    # Update nudge status to approved
    result = client.table("nudges").update({
        "status": "approved",
        "approved_content": draft_content
    }).eq("id", id).eq("user_id", user.id).execute()
    
    # Set conversation to auto_approved so all future nudges skip approval
    if conversation_id:
        client.table("conversations").update({
            "status": "approved",
            "auto_approved": True
        }).eq("id", conversation_id).eq("user_id", user.id).execute()
    
    return result.data

@router.put("/{id}/edit")
async def edit_nudge(
    id: str, 
    content: str = Body(..., embed=True),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Edit nudge content before approval."""
    client = get_client()
    result = client.table("nudges").update({
        "draft_content": content,
        "approved_content": content 
    }).eq("id", id).eq("user_id", user.id).execute()
    return result.data

@router.put("/{id}/")
async def update_nudge(
    id: str,
    request: UpdateNudgeRequest,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Update nudge data."""
    client = get_client()
    
    update_data = {}
    if request.channel is not None: update_data["channel"] = request.channel
    if request.tone is not None: update_data["tone"] = request.tone
    if request.content is not None: 
        update_data["draft_content"] = request.content
        update_data["approved_content"] = request.content
    if request.max_escalations is not None: update_data["max_escalations"] = request.max_escalations
    if request.recurrence_hours is not None: update_data["recurrence_hours"] = request.recurrence_hours
    if request.recurrence_minutes is not None: update_data["recurrence_minutes"] = request.recurrence_minutes
    if request.scheduled_at is not None: update_data["scheduled_at"] = request.scheduled_at
    if request.status is not None: update_data["status"] = request.status

    if not update_data:
        return {"message": "No data to update"}

    result = client.table("nudges").update(update_data).eq("id", id).eq("user_id", user.id).execute()
    return result.data

@router.post("/{id}/cancel")
async def cancel_nudge(id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Cancel a pending nudge."""
    client = get_client()
    result = client.table("nudges").update({
        "status": "cancelled"
    }).eq("id", id).eq("user_id", user.id).execute()
    return result.data

@router.post("/{id}/reschedule")
async def reschedule_nudge(
    id: str,
    scheduled_at: str = Body(..., embed=True),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Reschedule a nudge to a new time."""
    client = get_client()
    result = client.table("nudges").update({
        "scheduled_at": scheduled_at,
        "status": "pending"
    }).eq("id", id).eq("user_id", user.id).execute()
    return result.data

@router.post("/{id}/send")
async def send_nudge(id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Send nudge immediately via WhatsApp."""
    client = get_client()
    
    # 1. Fetch Nudge + Contact details
    nudge_data = client.table("nudges").select("*, contacts(phone_number)").eq("id", id).eq("user_id", user.id).single().execute()
    
    if not nudge_data.data:
        raise HTTPException(status_code=404, detail="Nudge not found")
    
    nudge = nudge_data.data
    contact_phone = nudge["contacts"]["phone_number"]
    content = nudge.get("approved_content") or nudge.get("draft_content") or "Hello!"

    # 2. Fetch user's WhatsApp integration credentials from database
    integration_data = client.table("integrations").select("*").eq("user_id", user.id).eq("provider", "whatsapp").single().execute()
    
    if not integration_data.data:
        raise HTTPException(status_code=400, detail="WhatsApp integration not configured. Please configure it in Settings.")
    
    integration = integration_data.data
    access_token = integration.get("access_token")
    metadata = integration.get("metadata") or {}
    phone_number_id = metadata.get("phone_number_id")
    
    if not access_token or not phone_number_id:
        raise HTTPException(status_code=400, detail="WhatsApp integration missing access token or phone number ID. Please reconfigure in Settings.")

    # 3. Send via Delivery Engine
    from app.delivery_engine import send_smart_nudge, DeliveryError
    
    try:
        # Use smart nudge logic (Hybrid flow: text vs template)
        result = await send_smart_nudge(
            client_supabase=client,
            nudge=nudge,
            contact_phone=contact_phone,
            access_token=access_token,
            phone_number_id=phone_number_id
        )
        
        # 4. Store outgoing message in messages table with delivery tracking
        try:
            client.table("messages").insert({
                "user_id": user.id,
                "conversation_id": nudge.get("conversation_id"),
                "contact_id": nudge.get("contact_id"),
                "direction": "outgoing",
                "channel": "whatsapp",
                "content": content,
                "whatsapp_message_id": result.message_id if result else None,
                "status": "sent",
                "sent_at": datetime.utcnow().isoformat()
            }).execute()
        except Exception as msg_err:
            print(f"Failed to store message: {msg_err}")
        
        # 5. Update Nudge Status & Log
        update_result = client.table("nudges").update({
            "status": "sent",
            "sent_at": datetime.utcnow().isoformat(),
            "channel": "whatsapp"
        }).eq("id", id).eq("user_id", user.id).execute()
        
        # 6. Log to Conversation (Last Message Time & Status)
        if nudge.get("conversation_id"):
             client.table("conversations").update({
                "last_message_at": datetime.utcnow().isoformat(),
                "status": "awaiting"  # Update status to Awaiting Reply
            }).eq("id", nudge["conversation_id"]).execute()

        return update_result.data
        
    except DeliveryError as e:
        print(f"Delivery Failed: {e}")
        
        # Store the failed message so it appears in UI with error details
        try:
            client.table("messages").insert({
                "user_id": user.id,
                "conversation_id": nudge.get("conversation_id"),
                "contact_id": nudge.get("contact_id"),
                "direction": "outgoing",
                "channel": "whatsapp",
                "content": content,
                "status": "failed",
                "failed_at": datetime.utcnow().isoformat(),
                "error_code": str(e.status_code) if e.status_code else "unknown",
                "error_message": str(e.message)
            }).execute()
        except Exception as msg_err:
            print(f"Failed to store failed message: {msg_err}")
        
        # Update nudge status to failed
        client.table("nudges").update({
            "status": "failed"
        }).eq("id", id).execute()
        
        raise HTTPException(
            status_code=500, 
            detail={
                "message": f"Failed to send message: {str(e)}",
                "error_code": str(e.status_code) if e.status_code else None,
                "error_type": e.error_type.value if e.error_type else None,
                "can_retry": True
            }
        )
    except Exception as e:
        print(f"Delivery Failed (unexpected): {e}")
        
        # Store the failed message even for unexpected errors
        try:
            client.table("messages").insert({
                "user_id": user.id,
                "conversation_id": nudge.get("conversation_id"),
                "contact_id": nudge.get("contact_id"),
                "direction": "outgoing",
                "channel": "whatsapp",
                "content": content,
                "status": "failed",
                "failed_at": datetime.utcnow().isoformat(),
                "error_message": str(e)
            }).execute()
        except Exception as msg_err:
            print(f"Failed to store failed message: {msg_err}")
        
        client.table("nudges").update({
            "status": "failed"
        }).eq("id", id).execute()
        
        raise HTTPException(status_code=500, detail=f"Failed to send message: {str(e)}")

@router.post("/ai/regenerate")
async def regenerate_nudge_draft(
    nudge_id: str = Body(..., embed=True), 
    tone: Optional[str] = Body(None, embed=True),
    instructions: Optional[str] = Body(None, embed=True),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Regenerate nudge draft content using AI."""
    # TODO: Integration with Agent
    return {
        "content": f"This is a regenerated draft for nudge {nudge_id} with tone {tone}. (AI Integration Pending)"
    }
