from langchain_core.tools import tool
from typing import Optional
from datetime import datetime, timedelta
from app.supabase_client import get_client

@tool
def schedule_nudge(
    thread_id: str,
    check_after_hours: int = 0,
    check_after_minutes: int = 0,
    action_if_no_reply: str = "nudge",
    suggested_content: str = ""
):
    """
    Schedule a follow-up nudge for a thread.
    
    Args:
        thread_id: The ID of the conversation thread.
        check_after_hours: Number of hours to wait before checking/nudging.
        check_after_minutes: Number of minutes to wait (for testing). Added to hours.
        action_if_no_reply: Action to take if no reply (nudge, escalate, close).
        suggested_content: AI-generated draft content for the follow-up message.
    """
    from datetime import timezone
    client = get_client()
    schedule_time = datetime.now(timezone.utc) + timedelta(hours=check_after_hours, minutes=check_after_minutes)
    
    # Get conversation to find user_id/contact_id and auto_approved status
    conv = client.table("conversations").select("user_id, contact_id, auto_approved").eq("id", thread_id).single().execute()
    if not conv.data:
        return "Conversation not found"
        
    user_id = conv.data["user_id"]
    contact_id = conv.data["contact_id"]
    is_auto_approved = conv.data.get("auto_approved", False)
    
    # Cancel any existing pending/approved nudges for this conversation
    # This prevents duplicate nudges when a new message comes in
    client.table("nudges").update({
        "status": "cancelled"
    }).eq("conversation_id", thread_id).in_("status", ["pending", "approved"]).execute()
    
    # Determine initial status based on conversation's auto_approved setting
    initial_status = "approved" if is_auto_approved else "pending"
    
    # Create nudge with AI-generated content
    default_content = f"Hi! Just following up on our conversation. Let me know if you need anything!"
    content = suggested_content or default_content
    
    nudge = client.table("nudges").insert({
        "user_id": user_id,
        "conversation_id": thread_id,
        "contact_id": contact_id,
        "scheduled_at": schedule_time.isoformat(),
        "status": initial_status,
        "channel": "whatsapp",
        "draft_content": content,
        "approved_content": content if is_auto_approved else None,
        "tone": "warm"
    }).execute()
    
    status_msg = "auto-approved" if is_auto_approved else "pending approval"
    return f"Nudge scheduled for {schedule_time} ({status_msg}) with content: '{content}'"

@tool
def update_crm(
    contact_email: str,
    notes: str
):
    """
    Log notes to the CRM for a contact.
    """
    # Mock CRM update
    return f"Logged notes for {contact_email}: {notes}"

@tool
def search_context(
    query: str
):
    """
    Search for context across previous conversations and documents.
    """
    # Mock search
    return f"Found context for '{query}': User prefers warm tone."
