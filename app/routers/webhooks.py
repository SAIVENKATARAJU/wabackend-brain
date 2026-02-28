"""
WhatsApp Webhook Handlers - Adapted for User-Based Context

Handles webhook verification and incoming messages from Meta.
Stores messages in the messages table and calls the AI decision agent.
"""

import os
import re
import json
from typing import Any, Optional
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse

from app.supabase_client import get_client
from app.config import settings
from app.models import DecisionRequest, StatusEnum, ActionEnum
from app.delivery_engine import send_text_message, DeliveryError
from app.database import update_conversation, calculate_next_action_at


def sanitize_phone_number(phone: str) -> str:
    """
    Sanitize phone number to prevent SQL injection.
    Only allows digits and optional leading +.
    """
    if not phone:
        return ""
    # Remove all non-digit characters except leading +
    sanitized = re.sub(r"[^\d+]", "", phone)
    # Ensure + is only at the beginning
    if "+" in sanitized:
        sanitized = "+" + sanitized.replace("+", "")
    # Limit length (E.164 max is 15 digits + country code)
    return sanitized[:20]

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
legacy_router = APIRouter(tags=["webhooks_legacy"])

@legacy_router.post("/webhook")
async def legacy_webhook_receive(request: Request):
    """Legacy endpoint for /webhook (singular) to support existing configurations"""
    return await webhook_receive(request)

@legacy_router.get("/webhook")
async def legacy_webhook_verify(request: Request):
    """Legacy endpoint for /webhook (singular) verification"""
    return await webhook_verify(request)


# ============================================================================
# Webhook Verification (GET /webhooks/whatsapp)
# ============================================================================

@router.get("/whatsapp", response_class=PlainTextResponse)
async def webhook_verify(request: Request):
    """
    GET /webhooks/whatsapp - Verification handshake with Meta
    
    Meta sends a GET request with hub.mode, hub.verify_token, and hub.challenge
    We must verify the token and echo back the challenge to complete verification
    """
    params = dict(request.query_params)
    
    hub_mode = params.get("hub.mode")
    hub_verify_token = params.get("hub.verify_token")
    hub_challenge = params.get("hub.challenge")
    
    verify_token = settings.WEBHOOK_VERIFY_TOKEN or ""
    
    if hub_mode == "subscribe" and hub_verify_token == verify_token:
        print("[Webhook] ✓ Verification successful!")
        return hub_challenge
    
    print("[Webhook] ✗ Verification failed - invalid token")
    raise HTTPException(status_code=403, detail="Forbidden")


# ============================================================================
# Incoming Message Handler (POST /webhooks/whatsapp)
# ============================================================================

@router.post("/whatsapp")
async def webhook_receive(request: Request) -> dict[str, str]:
    """
    POST /webhooks/whatsapp - Receive messages and status updates from Meta
    
    - Status updates: sent, delivered, read, failed
    - Incoming messages: stored in messages table, AI agent called
    """
    payload = await request.json()
    
    print(f"[Webhook] Received POST: {json.dumps(payload, indent=2)}")
    
    entries = payload.get("entry", [])
    for entry in entries:
        changes = entry.get("changes", [])
        for change in changes:
            value = change.get("value", {})
            metadata = value.get("metadata", {})
            phone_number_id = metadata.get("phone_number_id")
            
            # Handle status updates
            statuses = value.get("statuses", [])
            for status in statuses:
                await handle_status_update(status)
            
            # Handle incoming messages
            messages = value.get("messages", [])
            for message in messages:
                await handle_incoming_message(message, phone_number_id)
    
    return {"status": "ok"}


async def handle_status_update(status: dict[str, Any]) -> None:
    """
    Update message status in database based on WhatsApp callback.
    
    Meta sends these status values:
    - sent: Message accepted by WhatsApp servers
    - delivered: Message delivered to recipient's device
    - read: Message read by recipient
    - failed: Message delivery failed (includes error details)
    """
    client = get_client()
    
    msg_id = status.get("id")
    status_text = status.get("status")  # sent, delivered, read, failed
    timestamp = status.get("timestamp")  # Unix timestamp from Meta
    
    print(f"[Status] Message {msg_id}: {status_text}")
    
    if not msg_id or not status_text:
        return
    
    # Build update payload with status-specific timestamps
    now = datetime.now(timezone.utc).isoformat()
    update_data: dict[str, Any] = {"status": status_text}
    
    if status_text == "sent":
        update_data["sent_at"] = now
    elif status_text == "delivered":
        update_data["delivered_at"] = now
    elif status_text == "read":
        update_data["read_at"] = now
    elif status_text == "failed":
        update_data["failed_at"] = now
        # Extract error details from Meta's callback
        errors = status.get("errors", [])
        if errors:
            error = errors[0]  # Meta typically sends one error
            update_data["error_code"] = str(error.get("code", "unknown"))
            update_data["error_message"] = error.get("title", "") or error.get("message", "Unknown error")
            print(f"[Status] Error details: code={update_data['error_code']}, message={update_data['error_message']}")
    
    # Update message in database
    try:
        result = client.table("messages").update(
            update_data
        ).eq("whatsapp_message_id", msg_id).execute()
        
        updated_msg = result.data[0] if result.data else None
        
        if updated_msg:
            print(f"[Status] Updated message {msg_id} -> {status_text}")
            
            # Sync nudge status if this message is linked to a conversation
            conversation_id = updated_msg.get("conversation_id")
            if conversation_id and status_text == "failed":
                # If delivery failed, update the associated nudge to 'failed' too
                try:
                    client.table("nudges").update({
                        "status": "failed"
                    }).eq("conversation_id", conversation_id).eq("status", "sent").execute()
                    print(f"[Status] Synced nudge status to failed for conversation {conversation_id[:8]}...")
                except Exception as e:
                    print(f"[Status] Failed to sync nudge status: {e}")
            
            elif conversation_id and status_text == "delivered":
                # Update conversation status to reflect delivery
                try:
                    client.table("conversations").update({
                        "status": "awaiting"
                    }).eq("id", conversation_id).in_("status", ["pending", "approved"]).execute()
                except Exception as e:
                    print(f"[Status] Failed to update conversation: {e}")
        else:
            print(f"[Status] No message found with whatsapp_message_id: {msg_id}")
            
    except Exception as e:
        print(f"[Status] Failed to update: {e}")
        import traceback
        traceback.print_exc()


async def handle_incoming_message(message: dict[str, Any], phone_number_id: str) -> None:
    """
    Process an incoming WhatsApp message:
    1. Find user by phone_number_id from integrations table
    2. Find or create contact by sender phone number
    3. Find or create conversation
    4. Store message in messages table
    5. Call AI agent for decision
    """
    client = get_client()
    
    msg_from = message.get("from", "")
    msg_type = message.get("type", "")
    msg_id = message.get("id", "")
    
    # Extract text content
    text_body = ""
    if msg_type == "text":
        text_body = message.get("text", {}).get("body", "")
    elif msg_type == "button":
        text_body = message.get("button", {}).get("text", "")
    elif msg_type == "interactive":
        interactive = message.get("interactive", {})
        if "button_reply" in interactive:
            text_body = interactive["button_reply"].get("title", "")
        elif "list_reply" in interactive:
            text_body = interactive["list_reply"].get("title", "")
    
    print(f"[Incoming] From: {msg_from} | Type: {msg_type}")
    if text_body:
        print(f"[Incoming] Message: {text_body}")
    
    if not text_body:
        print(f"[Skip] No text content in {msg_type} message")
        return
    
    # 1. Find user by phone_number_id
    user_id = await find_user_by_phone_number_id(phone_number_id)
    if not user_id:
        print(f"[Error] No user found for phone_number_id: {phone_number_id}")
        return
    
    # 2. Find or create contact
    contact = await get_or_create_contact(user_id, msg_from)
    if not contact:
        print(f"[Error] Failed to get/create contact for {msg_from}")
        return
    
    # 3. Find or create conversation
    conversation = await get_or_create_conversation(user_id, contact["id"])
    if not conversation:
        print(f"[Error] Failed to get/create conversation")
        return
    
    # 4. Store incoming message
    try:
        client.table("messages").insert({
            "user_id": user_id,
            "conversation_id": conversation["id"],
            "contact_id": contact["id"],
            "direction": "incoming",
            "channel": "whatsapp",
            "content": text_body,
            "whatsapp_message_id": msg_id,
            "status": "delivered"  # Use 'delivered' instead of 'received' - valid statuses: pending, sent, delivered, read, failed
        }).execute()
        print(f"[DB] Stored incoming message")
    except Exception as e:
        print(f"[DB] Failed to store message: {e}")
    
    # 5. Update conversation last_message_at
    try:
        client.table("conversations").update({
            "last_message_at": datetime.now(timezone.utc).isoformat(),
            "last_reply_at": datetime.now(timezone.utc).isoformat(),
            "status": "needs_response"  # Update status to indicate user replied
        }).eq("id", conversation["id"]).execute()
    except Exception as e:
        print(f"[DB] Failed to update conversation: {e}")
    
    # 6. Call AI agent for decision (async, non-blocking for now)
    try:
        await process_with_ai_agent(user_id, conversation["id"], contact["id"], text_body)
    except Exception as e:
        print(f"[AI] Agent failed: {e}")


async def find_user_by_phone_number_id(phone_number_id: str) -> Optional[str]:
    """Find user_id by matching phone_number_id in integrations table metadata."""
    if not phone_number_id:
        return None
    
    client = get_client()
    
    try:
        # Search integrations where metadata contains this phone_number_id
        result = client.table("integrations").select("user_id, metadata").eq("provider", "whatsapp").execute()
        
        for integration in result.data or []:
            metadata = integration.get("metadata") or {}
            if metadata.get("phone_number_id") == phone_number_id:
                return integration["user_id"]
        
        print(f"[Lookup] No integration found for phone_number_id: {phone_number_id}")
        return None
        
    except Exception as e:
        print(f"[Lookup] Error: {e}")
        return None


async def get_or_create_contact(user_id: str, phone_number: str) -> Optional[dict]:
    """Get or create a contact by user_id and phone_number."""
    client = get_client()
    
    # Sanitize phone number to prevent SQL injection
    safe_phone = sanitize_phone_number(phone_number)
    if not safe_phone:
        print(f"[Contact] Invalid phone number: {phone_number}")
        return None
    
    # Normalize phone number (WhatsApp sends without +, we usually store with +)
    search_number = safe_phone
    if not search_number.startswith("+"):
        search_number = "+" + safe_phone
    
    try:
        # Try to find existing contact with normalized or raw number
        # Use .in_() instead of .or_() with string interpolation for safety
        result = (
            client.table("contacts")
            .select("*")
            .eq("user_id", user_id)
            .in_("phone_number", [search_number, safe_phone])
            .execute()
        )
        
        if result.data:
            return result.data[0]
        
        # Create new contact
        # Important: Use None instead of "" for email to avoid unique constraint conflicts 
        # (PostgreSQL unique indexes allow multiple NULLs, but only one empty string)
        result = client.table("contacts").insert({
            "user_id": user_id,
            "phone_number": search_number,
            "name": safe_phone,  # Use sanitized phone as name
            "email": None  # Use NULL instead of empty string
        }).execute()
        
        return result.data[0] if result.data else None
        
    except Exception as e:
        print(f"[Contact] Error: {e}")
        return None


async def get_or_create_conversation(user_id: str, contact_id: str) -> Optional[dict]:
    """Get or create a conversation for a contact."""
    client = get_client()
    
    try:
        # Try to find existing active conversation
        result = (
            client.table("conversations")
            .select("*")
            .eq("user_id", user_id)
            .eq("contact_id", contact_id)
            .neq("status", "resolved")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        
        if result.data:
            return result.data[0]
        
        # Create new conversation
        result = client.table("conversations").insert({
            "user_id": user_id,
            "contact_id": contact_id,
            "thread_id": f"whatsapp_{contact_id}",
            "subject": "WhatsApp Conversation",
            "channel": "whatsapp",
            "status": "active"
        }).execute()
        
        return result.data[0] if result.data else None
        
    except Exception as e:
        print(f"[Conversation] Error: {e}")
        return None


def build_reply_message(decision) -> str:
    """Build a reply message based on the decision response."""
    if decision.action == ActionEnum.CLOSE:
        return "Thank you! Your request has been completed. Is there anything else I can help you with?"
    elif decision.action == ActionEnum.ESCALATE:
        return "I'm connecting you with a human agent who can better assist you. Please hold."
    elif decision.action == ActionEnum.RESCHEDULE:
        hours = decision.after_hours or 24
        return f"I'll follow up with you in {hours} hours. Thank you for your patience!"
    elif decision.action == ActionEnum.WAIT:
        return "Thank you for your message. We're processing your request and will get back to you soon."
    
    return ""


async def process_with_ai_agent(user_id: str, conversation_id: str, contact_id: str, text: str) -> None:
    """Call the AI decision agent to process incoming message."""
    try:
        from app.agent import run_decision
        
        # Get current status to pass to agent
        client = get_client()
        conv_resp = client.table("conversations").select("status").eq("id", conversation_id).single().execute()
        current_db_status = conv_resp.data.get("status", "pending") if conv_resp.data else "pending"
        
        # Map DB status to Enum
        status_map = {
            "pending": StatusEnum.PENDING,
            "needs_response": StatusEnum.PENDING,
            "active": StatusEnum.PENDING,
            "promised": StatusEnum.PROMISED,
            "escalated": StatusEnum.ESCALATED,
            "closed": StatusEnum.CLOSED,
            "resolved": StatusEnum.CLOSED,
            "approved": StatusEnum.PENDING,
            "snoozed": StatusEnum.PENDING
        }
        last_status = status_map.get(current_db_status, StatusEnum.PENDING)

        request = DecisionRequest(
            org_id=user_id,  # Using user_id as org_id
            conversation_id=conversation_id,
            contact_id=contact_id,
            incoming_text=text,
            last_status=last_status
        )
        
        print(f"[AI] Calling decision API for conversation {conversation_id[:8]}...")
        decision = await run_decision(request)
        print(f"[AI] Decision: action={decision.action}, status={decision.new_status}, confidence={decision.confidence}")
        
        # 1. Update conversation status
        reply_text = build_reply_message(decision)
        
        await update_conversation(
            conversation_id=conversation_id,
            status=decision.new_status.value,
            last_incoming_text=text,
            last_outgoing_text=reply_text if reply_text else None,
            next_action_at=calculate_next_action_at(decision.after_hours),
            last_followup_at=datetime.now(timezone.utc)
        )
        print(f"[DB] Updated conversation status to {decision.new_status.value}")

        # 2. If closing, cancel nudges
        if decision.action == ActionEnum.CLOSE:
            client.table("nudges").update({
                "status": "cancelled"
            }).eq("conversation_id", conversation_id).in_("status", ["pending", "approved"]).execute()
            print(f"[DB] Cancelled all pending nudges for closed conversation")

        # 3. Send reply (if any)
        if reply_text:
            # We need the contact phone number to send reply
            # Fetch contact to get phone number
            contact_resp = client.table("contacts").select("phone_number").eq("id", contact_id).single().execute()
            if contact_resp.data:
                to_phone = contact_resp.data["phone_number"]
                try:
                    result = await send_text_message(to_phone, reply_text)
                    print(f"[Reply] Sent message {result.message_id} to {to_phone}")
                except DeliveryError as e:
                    print(f"[Reply] Failed to send: {e}")
            else:
                print(f"[Reply] Could not find contact phone number for {contact_id}")

    except Exception as e:
        print(f"[AI] Error: {e}")
        import traceback
        traceback.print_exc()


# Gmail webhook (placeholder)
@router.post("/gmail")
async def gmail_webhook(request: Request):
    """Handle Gmail push notifications."""
    payload = await request.json()
    print(f"Received Gmail webhook: {payload}")
    return {"status": "received"}
