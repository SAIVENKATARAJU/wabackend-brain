"""
WhatsApp Webhook Handlers

Handles webhook verification and status update callbacks from Meta.
"""

import os
from typing import Any

from fastapi import APIRouter, Query, Request, HTTPException
from fastapi.responses import PlainTextResponse

router = APIRouter(prefix="/webhook", tags=["webhook"])


# ============================================================================
# Webhook Verification (GET /webhook)
# ============================================================================

@router.get("", response_class=PlainTextResponse)
async def webhook_verify(
    request: Request,
):
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
    POST /webhook - Receive status updates from Meta
    
    Meta sends status updates when messages are sent, delivered, read, or failed
    """
    import json
    
    payload = await request.json()
    
    # Print raw payload for debugging
    print(f"[Webhook] Received POST: {json.dumps(payload, indent=2)}")
    
    # Navigate: entry[0].changes[0].value.statuses[0]
    entries = payload.get("entry", [])
    for entry in entries:
        changes = entry.get("changes", [])
        for change in changes:
            value = change.get("value", {})
            
            # Handle status updates
            statuses = value.get("statuses", [])
            for status in statuses:
                msg_id = status.get("id", "unknown")
                status_text = status.get("status", "unknown")
                timestamp = status.get("timestamp", "")
                
                print(f"[Update] Message ID: {msg_id} is now {status_text}")
                
                # You can add database logging here
                # await log_status_update(msg_id, status_text, timestamp)
            
            # Handle incoming messages (optional)
            messages = value.get("messages", [])
            for message in messages:
                msg_from = message.get("from", "unknown")
                msg_type = message.get("type", "unknown")
                msg_id = message.get("id", "unknown")
                
                # Extract text if it's a text message
                text_body = ""
                if msg_type == "text":
                    text_body = message.get("text", {}).get("body", "")
                
                print(f"[Incoming] From: {msg_from} | Type: {msg_type} | ID: {msg_id}")
                if text_body:
                    print(f"[Incoming] Message: {text_body}")
    
    return {"status": "ok"}
