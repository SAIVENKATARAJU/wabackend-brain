"""
Cron Router - Endpoints for pg_cron scheduled jobs

These endpoints are called by pg_cron via pg_net HTTP requests.
They handle automated processing of due nudges.
"""

import os
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Header, HTTPException
from app.config import settings
from app.supabase_client import get_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cron", tags=["cron"])

# Secret token to verify cron requests (prevents external abuse)
CRON_SECRET = settings.CRON_SECRET


@router.post("/process-nudges")
async def process_due_nudges(x_cron_secret: str = Header(None)):
    """
    Process all pending and approved nudges that are due.
    
    Called by pg_cron every minute to check for and process due nudges.
    - Approved nudges: send immediately (user already approved)
    - Pending nudges: check auto_send preference
    """
    # Verify cron secret to prevent external abuse
    if x_cron_secret != CRON_SECRET:
        raise HTTPException(status_code=403, detail="Invalid cron secret")
    
    client = get_client()
    now = datetime.now(timezone.utc).isoformat()
    processed = 0
    errors = 0
    
    logger.info(f"[Cron] Checking for due nudges. Current UTC: {now}")
    
    try:
        # Find pending OR approved nudges where scheduled_at <= now
        result = client.table("nudges")\
            .select("*, contacts(phone_number), conversations(subject)")\
            .in_("status", ["pending", "approved"])\
            .lte("scheduled_at", now)\
            .execute()
        
        due_nudges = result.data or []
        logger.info(f"[Cron] Found {len(due_nudges)} due nudges")
        
        for nudge in due_nudges:
            try:
                await process_single_nudge(nudge)
                processed += 1
            except Exception as e:
                logger.error(f"[Cron] Error processing nudge {nudge['id']}: {e}")
                errors += 1
                
    except Exception as e:
        logger.error(f"[Cron] Error fetching due nudges: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
    return {
        "status": "ok",
        "processed": processed,
        "errors": errors,
        "timestamp": now
    }


async def process_single_nudge(nudge: dict):
    """Process a single due nudge."""
    nudge_id = nudge.get("id")
    user_id = nudge.get("user_id")
    status = nudge.get("status")
    client = get_client()
    
    # If nudge is already approved, send it immediately
    if status == "approved":
        logger.info(f"[Cron] Sending approved nudge {nudge_id}")
        await auto_send_nudge(nudge)
        return
    
    # For pending nudges, check user preferences for auto_send
    try:
        prefs = client.table("user_preferences")\
            .select("auto_send")\
            .eq("user_id", user_id)\
            .single()\
            .execute()
        auto_send = prefs.data.get("auto_send", False) if prefs.data else False
    except:
        auto_send = False
    
    if auto_send:
        # Auto-send the nudge
        logger.info(f"[Cron] Auto-sending pending nudge {nudge_id}")
        await auto_send_nudge(nudge)
    else:
        # Mark as ready for approval (stays pending, user will see in dashboard)
        logger.info(f"[Cron] Nudge {nudge_id} ready for approval")
        # Update status to show it's ready
        client.table("nudges").update({
            "status": "ready"
        }).eq("id", nudge_id).execute()


async def auto_send_nudge(nudge: dict):
    """Automatically send a nudge via WhatsApp."""
    client = get_client()
    nudge_id = nudge.get("id")
    user_id = nudge.get("user_id")
    
    # Get phone number from contact
    contact_phone = nudge.get("contacts", {}).get("phone_number")
    if not contact_phone:
        logger.error(f"[Cron] No phone number for nudge {nudge_id}")
        client.table("nudges").update({"status": "failed"}).eq("id", nudge_id).execute()
        return
    
    # Get WhatsApp integration
    try:
        integration = client.table("integrations")\
            .select("access_token, metadata")\
            .eq("user_id", user_id)\
            .eq("provider", "whatsapp")\
            .single()\
            .execute()
        
        if not integration.data:
            logger.error(f"[Cron] No WhatsApp integration for user {user_id}")
            return
        
        access_token = integration.data.get("access_token")
        phone_number_id = integration.data.get("metadata", {}).get("phone_number_id")
        
        if not access_token or not phone_number_id:
            logger.error(f"[Cron] Missing WhatsApp credentials")
            return
        
        # Send via delivery engine
        from app.delivery_engine import send_smart_nudge
        
        result = await send_smart_nudge(
            client_supabase=client,
            nudge=nudge,
            contact_phone=contact_phone,
            access_token=access_token,
            phone_number_id=phone_number_id
        )
        
        # Update nudge status
        client.table("nudges").update({
            "status": "sent",
            "sent_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", nudge_id).execute()
        
        # Store message
        client.table("messages").insert({
            "user_id": user_id,
            "conversation_id": nudge.get("conversation_id"),
            "contact_id": nudge.get("contact_id"),
            "direction": "outgoing",
            "channel": "whatsapp",
            "content": nudge.get("approved_content") or nudge.get("draft_content") or "",
            "whatsapp_message_id": result.message_id if result else None,
            "status": "sent"
        }).execute()
        
        logger.info(f"[Cron] Successfully sent nudge {nudge_id}")
        
    except Exception as e:
        logger.error(f"[Cron] Failed to auto-send nudge: {e}")
        client.table("nudges").update({"status": "failed"}).eq("id", nudge_id).execute()
