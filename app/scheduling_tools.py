"""
Scheduling Agent Tools

LangChain tools used by the scheduling agent to resolve contacts,
create nudges, and handle timing for natural-language nudge scheduling.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from langchain_core.tools import tool

from app.supabase_client import get_client

logger = logging.getLogger(__name__)


@tool
def resolve_contact(query: str, user_id: str) -> str:
    """
    Fuzzy-match a contact by name, email, phone, or company.

    Args:
        query: The search string (partial name, email, etc.)
        user_id: The authenticated user's ID.

    Returns:
        JSON-formatted list of matching contacts with id, name, email, phone_number, company.
        If exactly one match, returns it directly. If multiple, returns all (max 5).
    """
    import json

    client = get_client()
    search = f"%{query}%"

    # Search across name, email, phone_number, and company with ilike
    result = client.table("contacts") \
        .select("id, name, email, phone_number, company") \
        .eq("user_id", user_id) \
        .or_(
            f"name.ilike.{search},"
            f"email.ilike.{search},"
            f"phone_number.ilike.{search},"
            f"company.ilike.{search}"
        ) \
        .limit(5) \
        .execute()

    matches = result.data or []

    if len(matches) == 0:
        return json.dumps({"found": 0, "message": f"No contacts found matching '{query}'."})
    elif len(matches) == 1:
        c = matches[0]
        return json.dumps({
            "found": 1,
            "contact": {
                "id": c["id"],
                "name": c.get("name", ""),
                "email": c.get("email", ""),
                "phone_number": c.get("phone_number", ""),
                "company": c.get("company", "")
            }
        })
    else:
        return json.dumps({
            "found": len(matches),
            "message": f"Found {len(matches)} contacts matching '{query}'. Ask the user which one they mean.",
            "contacts": [
                {
                    "id": c["id"],
                    "name": c.get("name", ""),
                    "email": c.get("email", ""),
                    "phone_number": c.get("phone_number", ""),
                    "company": c.get("company", "")
                }
                for c in matches
            ]
        })


@tool
def create_scheduled_nudge(
    user_id: str,
    contact_id: str,
    channel: str = "whatsapp",
    tone: str = "warm",
    content: str = "",
    subject: str = "Follow-up",
    scheduled_at: str = "",
    recurrence_hours: int = 24,
    recurrence_minutes: int = 0,
    max_follow_ups: int = 2
) -> str:
    """
    Create a scheduled nudge with a new conversation.

    Args:
        user_id: The authenticated user's ID.
        contact_id: The target contact's ID.
        channel: Communication channel - "whatsapp" or "email".
        tone: Message tone - "warm", "professional", or "urgent".
        content: The message content for the nudge.
        subject: Subject/topic of the follow-up conversation.
        scheduled_at: ISO-8601 datetime for when to send. If empty, defaults to 24h from now.
        recurrence_hours: Hours between recurring follow-ups.
        recurrence_minutes: Minutes between recurring follow-ups (for testing, overrides hours if >0).
        max_follow_ups: Maximum number of follow-up attempts.

    Returns:
        JSON string with created nudge details or error message.
    """
    import json

    client = get_client()

    try:
        # Determine schedule time
        if scheduled_at:
            schedule_time = scheduled_at
        else:
            schedule_time = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()

        # 1. Create Conversation
        conversation_data = {
            "user_id": user_id,
            "contact_id": contact_id,
            "subject": subject,
            "status": "pending",
            "channel": channel,
            "thread_id": str(uuid.uuid4()),
            "last_message_at": datetime.now(timezone.utc).isoformat(),
        }
        conv_result = client.table("conversations").insert(conversation_data).execute()
        conversation_id = conv_result.data[0]["id"]

        # 2. Create Nudge
        default_content = f"Hi! Just following up on our conversation about \"{subject}\". Let me know if you need anything!"
        final_content = content or default_content

        nudge_data = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "contact_id": contact_id,
            "channel": channel,
            "status": "pending",
            "tone": tone,
            "draft_content": final_content,
            "scheduled_at": schedule_time,
            "max_escalations": max_follow_ups,
            "recurrence_hours": recurrence_hours,
            "recurrence_minutes": recurrence_minutes if recurrence_minutes > 0 else None,
        }

        nudge_result = client.table("nudges").insert(nudge_data).execute()
        nudge = nudge_result.data[0]

        # Fetch contact name for display
        contact_result = client.table("contacts") \
            .select("name, email, phone_number") \
            .eq("id", contact_id) \
            .single() \
            .execute()
        contact = contact_result.data or {}

        return json.dumps({
            "success": True,
            "nudge": {
                "id": nudge["id"],
                "contact_name": contact.get("name", "Unknown"),
                "contact_phone": contact.get("phone_number", ""),
                "channel": channel,
                "tone": tone,
                "content": final_content,
                "scheduled_at": schedule_time,
                "subject": subject,
                "max_follow_ups": max_follow_ups,
                "recurrence_hours": recurrence_hours,
                "recurrence_minutes": recurrence_minutes,
                "status": "pending"
            }
        })

    except Exception as e:
        logger.error(f"[SchedulingTools] Failed to create nudge: {e}")
        return json.dumps({"success": False, "error": str(e)})


@tool
def list_user_contacts(user_id: str) -> str:
    """
    List all contacts for a user.

    Args:
        user_id: The authenticated user's ID.

    Returns:
        JSON-formatted list of contacts with id, name, email, phone_number, company.
    """
    import json

    client = get_client()

    result = client.table("contacts") \
        .select("id, name, email, phone_number, company") \
        .eq("user_id", user_id) \
        .order("name") \
        .limit(50) \
        .execute()

    contacts = result.data or []

    if not contacts:
        return json.dumps({"count": 0, "message": "No contacts found. The user needs to add contacts first."})

    return json.dumps({
        "count": len(contacts),
        "contacts": [
            {
                "id": c["id"],
                "name": c.get("name", ""),
                "email": c.get("email", ""),
                "phone_number": c.get("phone_number", ""),
                "company": c.get("company", "")
            }
            for c in contacts
        ]
    })


@tool
def get_current_time() -> str:
    """
    Get the current server time in UTC as ISO-8601 string.
    Use this to calculate relative times like 'tomorrow', 'in 2 hours', 'next Monday'.

    Returns:
        Current UTC time in ISO-8601 format, plus day-of-week for reference.
    """
    import json

    now = datetime.now(timezone.utc)
    return json.dumps({
        "utc_now": now.isoformat(),
        "day_of_week": now.strftime("%A"),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "note": "All scheduling should be done in UTC. Convert user's local time if needed."
    })
