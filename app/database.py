"""
Database Operations

CRUD operations for organizations, contacts, and conversations.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from app.supabase_client import get_client


# Default organization for WhatsApp webhook
DEFAULT_ORG_NAME = "whatsapp_default"


async def get_or_create_organization(name: str = DEFAULT_ORG_NAME) -> dict[str, Any]:
    """Get or create an organization by name."""
    client = get_client()
    
    # Try to find existing org
    result = client.table("organizations").select("*").eq("name", name).execute()
    
    if result.data:
        return result.data[0]
    
    # Create new org
    result = client.table("organizations").insert({"name": name}).execute()
    return result.data[0]


async def get_or_create_contact(
    org_id: str | UUID,
    phone_number: str,
    display_name: str | None = None
) -> dict[str, Any]:
    """Get or create a contact by org_id and phone_number."""
    client = get_client()
    
    # Try to find existing contact
    # Note: DB uses user_id, which maps to org_id in this context
    result = (
        client.table("contacts")
        .select("*")
        .eq("user_id", str(org_id))
        .eq("phone_number", phone_number)
        .execute()
    )
    
    if result.data:
        return result.data[0]
    
    # Create new contact
    result = client.table("contacts").insert({
        "user_id": str(org_id),
        "phone_number": phone_number,
        "display_name": display_name
    }).execute()
    return result.data[0]


async def get_or_create_conversation(
    org_id: str | UUID,
    contact_id: str | UUID
) -> dict[str, Any]:
    """Get or create an active conversation for a contact."""
    client = get_client()
    
    # Try to find existing non-closed conversation
    # Note: DB uses user_id, which maps to org_id in this context
    result = (
        client.table("conversations")
        .select("*")
        .eq("user_id", str(org_id))
        .eq("contact_id", str(contact_id))
        .neq("status", "closed")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    
    if result.data:
        return result.data[0]
    
    # Create new conversation
    result = client.table("conversations").insert({
        "user_id": str(org_id),
        "contact_id": str(contact_id),
        "status": "pending"
    }).execute()
    return result.data[0]


async def update_conversation(
    conversation_id: str | UUID,
    status: str | None = None,
    last_incoming_text: str | None = None,
    last_outgoing_text: str | None = None,
    next_action_at: datetime | None = None,
    last_followup_at: datetime | None = None
) -> dict[str, Any]:
    """Update a conversation with new data."""
    client = get_client()
    
    update_data: dict[str, Any] = {
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    if status is not None:
        update_data["status"] = status
    if last_incoming_text is not None:
        update_data["last_incoming_text"] = last_incoming_text
    if last_outgoing_text is not None:
        update_data["last_outgoing_text"] = last_outgoing_text
    if next_action_at is not None:
        update_data["next_action_at"] = next_action_at.isoformat()
    if last_followup_at is not None:
        update_data["last_followup_at"] = last_followup_at.isoformat()
    
    result = (
        client.table("conversations")
        .update(update_data)
        .eq("id", str(conversation_id))
        .execute()
    )
    return result.data[0] if result.data else {}


def calculate_next_action_at(after_hours: int | None) -> datetime | None:
    """Calculate next_action_at based on after_hours."""
    if after_hours is None:
        return None
    return datetime.now(timezone.utc) + timedelta(hours=after_hours)
