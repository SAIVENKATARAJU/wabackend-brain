"""
Background Scheduler for Processing Due Nudges

Uses APScheduler to check for pending nudges that are due and process them.
This runs in-process with the FastAPI app for simplicity during development.
For production, consider pg_cron or Cloud Scheduler.
"""

import logging
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.supabase_client import get_client

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = AsyncIOScheduler()


async def process_due_nudges():
    """
    Find and process nudges that are due for sending.
    
    This checks for pending AND approved nudges where scheduled_at <= now.
    For each due nudge:
    - If status is 'approved': send immediately (user already approved)
    - If status is 'pending' and auto_send is enabled: send immediately
    - Otherwise: wait for user approval
    """
    try:
        client = get_client()
        now = datetime.now(timezone.utc).isoformat()
        
        logger.info(f"[Scheduler] Checking for due nudges. Current UTC: {now}")
        
        # Find pending OR approved nudges where scheduled_at <= now
        result = client.table("nudges")\
            .select("*, contacts(phone_number), conversations(subject)")\
            .in_("status", ["pending", "approved"])\
            .lte("scheduled_at", now)\
            .execute()
        
        due_nudges = result.data or []
        
        if due_nudges:
            logger.info(f"[Scheduler] Found {len(due_nudges)} due nudges")
            for n in due_nudges:
                logger.info(f"[Scheduler] - Nudge {n.get('id')[:8]}: status={n.get('status')}, scheduled_at={n.get('scheduled_at')}")
        else:
            # Also check what nudges exist that are NOT due yet
            all_nudges = client.table("nudges")\
                .select("id, status, scheduled_at")\
                .in_("status", ["pending", "approved"])\
                .execute()
            logger.info(f"[Scheduler] No due nudges found. {len(all_nudges.data or [])} pending/approved nudges exist:")
            for n in (all_nudges.data or [])[:3]:
                logger.info(f"[Scheduler] - Nudge {n.get('id')[:8]}: scheduled_at={n.get('scheduled_at')} (now is {now})")
        
        for nudge in due_nudges:
            await process_single_nudge(nudge)
            
    except Exception as e:
        logger.error(f"[Scheduler] Error processing due nudges: {e}")


async def process_single_nudge(nudge: dict):
    """Process a single due nudge."""
    nudge_id = nudge.get("id")
    user_id = nudge.get("user_id")
    status = nudge.get("status")
    
    try:
        client = get_client()
        
        # If nudge is already approved, send it immediately
        if status == "approved":
            logger.info(f"[Scheduler] Sending approved nudge {nudge_id}")
            await auto_send_nudge(nudge)
            return
        
        # For pending nudges, check user preferences for auto_send
        prefs = client.table("user_preferences")\
            .select("auto_send")\
            .eq("user_id", user_id)\
            .single()\
            .execute()
        
        auto_send = prefs.data.get("auto_send", False) if prefs.data else False
        
        if auto_send:
            # Auto-send the nudge
            logger.info(f"[Scheduler] Auto-sending pending nudge {nudge_id}")
            await auto_send_nudge(nudge)
        else:
            # Mark as ready for approval (user will see it in dashboard)
            logger.info(f"[Scheduler] Nudge {nudge_id} ready for approval")
            # Could send push notification here in the future
            
    except Exception as e:
        logger.error(f"[Scheduler] Error processing nudge {nudge_id}: {e}")


async def auto_send_nudge(nudge: dict):
    """Automatically send a nudge via WhatsApp."""
    try:
        client = get_client()
        nudge_id = nudge.get("id")
        user_id = nudge.get("user_id")
        
        # Get phone number from contact
        contact_phone = nudge.get("contacts", {}).get("phone_number")
        if not contact_phone:
            logger.error(f"[Scheduler] No phone number for nudge {nudge_id}")
            return
        
        # Get WhatsApp integration
        integration = client.table("integrations")\
            .select("access_token, metadata")\
            .eq("user_id", user_id)\
            .eq("provider", "whatsapp")\
            .single()\
            .execute()
        
        if not integration.data:
            logger.error(f"[Scheduler] No WhatsApp integration for user {user_id}")
            return
        
        access_token = integration.data.get("access_token")
        phone_number_id = integration.data.get("metadata", {}).get("phone_number_id")
        
        if not access_token or not phone_number_id:
            logger.error(f"[Scheduler] Missing WhatsApp credentials for user {user_id}")
            return
        
        # Send via delivery engine using smart nudge logic
        from app.delivery_engine import send_smart_nudge
        
        result = await send_smart_nudge(
            client_supabase=client,
            nudge=nudge,
            contact_phone=contact_phone,
            access_token=access_token,
            phone_number_id=phone_number_id
        )
        
        content = nudge.get("approved_content") or nudge.get("draft_content") or "Hello!"
        
        # Update nudge status
        client.table("nudges").update({
            "status": "sent",
            "sent_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", nudge_id).execute()
        
        # Store message in messages table
        client.table("messages").insert({
            "user_id": user_id,
            "conversation_id": nudge.get("conversation_id"),
            "contact_id": nudge.get("contact_id"),
            "direction": "outgoing",
            "channel": "whatsapp",
            "content": content,
            "whatsapp_message_id": result.message_id if result else None,
            "status": "sent"
        }).execute()
        
        logger.info(f"[Scheduler] Successfully sent nudge {nudge_id}")
        
    except Exception as e:
        logger.error(f"[Scheduler] Failed to auto-send nudge: {e}")


def start_scheduler():
    """Start the background scheduler."""
    # Check every minute for due nudges
    scheduler.add_job(
        process_due_nudges,
        trigger=IntervalTrigger(minutes=1),
        id="process_due_nudges",
        name="Process Due Nudges",
        replace_existing=True
    )
    scheduler.start()
    logger.info("[Scheduler] Started - checking for due nudges every minute")


def stop_scheduler():
    """Stop the background scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("[Scheduler] Stopped")
