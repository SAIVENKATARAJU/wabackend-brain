"""
WhatsApp Webhook Handlers

Handles webhook verification and status update callbacks from Meta.
Stores incoming messages and calls the decision endpoint.
"""

import os
import json
from typing import Any
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse

from app.agent import run_decision
from app.models import DecisionRequest, StatusEnum
from app.delivery_engine import send_text_message, DeliveryError
from app.database import (
    get_or_create_organization,
    get_or_create_contact,
    get_or_create_conversation,
    update_conversation,
    calculate_next_action_at
)

router = APIRouter(prefix="/webhook", tags=["webhook"])


# ============================================================================
# Webhook Verification (GET /webhook)
# ============================================================================

@router.get("", response_class=PlainTextResponse)
async def webhook_verify(request: Request):
    """
    GET /webhook - Verification handshake with Meta
    
    Meta sends a GET request with hub.mode, hub.verify_token, and hub.challenge
    We must verify the token and echo back the challenge to complete verification
    """
    params = dict(request.query_params)
    
    hub_mode = params.get("hub.mode")
    hub_verify_token = params.get("hub.verify_token")
    hub_challenge = params.get("hub.challenge")
    
    verify_token = os.environ.get("WEBHOOK_VERIFY_TOKEN", "")
    
    # Check if this is a subscription verification request
    if hub_mode == "subscribe" and hub_verify_token == verify_token:
        print("[Webhook] ✓ Verification successful!")
        return hub_challenge
    
    print("[Webhook] ✗ Verification failed - invalid token")
    raise HTTPException(status_code=403, detail="Forbidden")


# ============================================================================
# Status Update Handler (POST /webhook)
# ============================================================================

@router.post("")
async def webhook_status_update(request: Request) -> dict[str, str]:
    """
    POST /webhook - Receive status updates and messages from Meta
    
    - Status updates: sent, delivered, read, failed
    - Incoming messages: calls the decision endpoint and sends reply
    """
    payload = await request.json()
    
    # Print raw payload for debugging
    print(f"[Webhook] Received POST: {json.dumps(payload, indent=2)}")
    
    # Navigate: entry[0].changes[0].value
    entries = payload.get("entry", [])
    for entry in entries:
        changes = entry.get("changes", [])
        for change in changes:
            value = change.get("value", {})
            
            # Handle status updates (log only for now)
            statuses = value.get("statuses", [])
            for status in statuses:
                msg_id = status.get("id", "unknown")
                status_text = status.get("status", "unknown")
                print(f"[Update] Message ID: {msg_id} is now {status_text}")
            
            # Handle incoming messages - THIS IS THE KEY PART
            messages = value.get("messages", [])
            for message in messages:
                await process_incoming_message(message, value.get("metadata", {}))
    
    return {"status": "ok"}


async def process_incoming_message(message: dict[str, Any], metadata: dict[str, Any]) -> None:
    """
    Process an incoming WhatsApp message:
    1. Get or create organization, contact, and conversation in database
    2. Call the decision endpoint
    3. Update conversation and send a reply based on the decision
    """
    msg_from = message.get("from", "unknown")
    msg_type = message.get("type", "unknown")
    msg_id = message.get("id", "unknown")
    timestamp = message.get("timestamp", "")
    
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
    
    print(f"[Incoming] From: {msg_from} | Type: {msg_type} | ID: {msg_id}")
    if text_body:
        print(f"[Incoming] Message: {text_body}")
    
    # Skip if no text content
    if not text_body:
        print(f"[Skip] No text content in {msg_type} message")
        return
    
    # Get or create database records
    try:
        from app.supabase_client import get_client
        client = get_client()
        
        # Resolve User ID - critical for correct conversation mapping
        # 1. Try to find a user from preferences (assuming single user or main user)
        # 2. Fallback to hardcoded known user ID if needed
        
        user_id = "523def32-86a2-4bd2-9977-a3dc394e958b" # Default/Fallback
        
        try:
            # Try to get the first user who has set up preferences
            prefs = client.table("user_preferences").select("user_id").limit(1).execute()
            if prefs.data:
                user_id = prefs.data[0]["user_id"]
        except Exception as e:
            print(f"[DB] Error fetching user_id from prefs: {e}")
            
        # Use simple Org ID string for now if needed by downstream, but pass USER_ID to contacts/convs
        org_id = "whatsapp_default" 
        
        contact = await get_or_create_contact(
            org_id=user_id, # Pass USER_ID here, as database.py expects user_id
            phone_number=msg_from,
            display_name=None 
        )
        conversation = await get_or_create_conversation(
            org_id=user_id, # Pass USER_ID here
            contact_id=contact["id"]
        )
        
        print(f"[DB] User: {user_id[:8]}... | Contact: {contact['id'][:8]}... | Conv: {conversation['id'][:8]}...")
        
        # Store message
        try:
            from app.supabase_client import get_client
            client = get_client()
            msg_result = client.table("messages").insert({
                "user_id": user_id, 
                "contact_id": contact["id"],
                "conversation_id": conversation["id"],
                "direction": "incoming",
                "channel": "whatsapp",
                "content": text_body,
                "whatsapp_message_id": msg_id,
                "status": "delivered",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "metadata": metadata or {}
            }).execute()
            print(f"[DB] Stored incoming message: {msg_id}")
        except Exception as e:
            print(f"[DB] Error storing message: {e}")
        
    except Exception as e:
        print(f"[DB] Error creating records: {e}")
        return
    
    # Map DB status to enum - handle unknown statuses gracefully
    db_status = conversation.get("status", "pending")
    status_mapping = {
        "pending": StatusEnum.PENDING,
        "needs_response": StatusEnum.PENDING,  # Legacy/UI status
        "active": StatusEnum.PENDING,          # Legacy status
        "promised": StatusEnum.PROMISED,
        "escalated": StatusEnum.ESCALATED,
        "closed": StatusEnum.CLOSED,
        "resolved": StatusEnum.CLOSED,         # Treat resolved as closed
        "approved": StatusEnum.PENDING,        # Map approved to pending
        "snoozed": StatusEnum.PENDING,         # Map snoozed to pending
    }
    current_status = status_mapping.get(db_status, StatusEnum.PENDING)
    print(f"[AI] Processing message for conversation {conversation['id'][:8]}... (status: {db_status} -> {current_status.value})")
    
        # Call the decision endpoint
    try:
        decision_request = DecisionRequest(
            org_id=org_id, # Use correct ID
            conversation_id=conversation["id"],
            contact_id=contact["id"],
            incoming_text=text_body,
            last_status=current_status
        )
        
        print(f"[Decision] Calling decision API for {msg_from}...")
        decision_response = await run_decision(decision_request)
        
        print(f"[Decision] Result: action={decision_response.action}, confidence={decision_response.confidence}, new_status={decision_response.new_status}")
        
        # Build reply message based on decision
        reply_text = build_reply_message(decision_response)
        
        # Update conversation in database
        await update_conversation(
            conversation_id=conversation["id"],
            status=decision_response.new_status.value,
            last_incoming_text=text_body,
            last_outgoing_text=reply_text if reply_text else None,
            next_action_at=calculate_next_action_at(decision_response.after_hours),
            last_followup_at=datetime.now(timezone.utc)
        )
        print(f"[DB] Updated conversation {conversation['id'][:8]}... status to {decision_response.new_status.value}")
        
        # If closing conversation, cancel all pending/approved nudges
        from app.models import ActionEnum
        from app.supabase_client import get_client
        if decision_response.action == ActionEnum.CLOSE:
            client = get_client()
            client.table("nudges").update({
                "status": "cancelled"
            }).eq("conversation_id", conversation["id"]).in_("status", ["pending", "approved"]).execute()
            print(f"[DB] Cancelled all pending nudges for closed conversation {conversation['id'][:8]}...")
        
        # Send the reply
        if reply_text:
            try:
                result = await send_text_message(msg_from, reply_text)
                print(f"[Reply] Sent message {result.message_id} to {msg_from}. Content: {reply_text[:50]}...")
            except DeliveryError as e:
                print(f"[Reply] Failed to send: {e}")
                
    except Exception as e:
        print(f"[Decision] Error in processing loop: {e}")
        import traceback
        traceback.print_exc()


def build_reply_message(decision) -> str:
    """Build a reply message based on the decision response."""
    from app.models import ActionEnum
    
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
