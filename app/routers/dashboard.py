from fastapi import APIRouter, Depends
from typing import Dict, Any, List
from datetime import datetime, timedelta
from app.supabase_client import get_client
from app.routers.auth import get_current_user

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"]
)

@router.get("/stats")
async def get_dashboard_stats(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, int]:
    """
    Get aggregated statistics for the dashboard.
    """
    client = get_client()
    user_id = user.id
    
    # 1. Awaiting Reply (Conversations with status 'awaiting')
    # Note: Adjust status value based on actual values used in app ('awaiting', 'awaiting_reply', etc.)
    awaiting = client.table("conversations").select("*", count="exact").eq("user_id", user_id).eq("status", "awaiting").execute()
    
    # 2. Due Today (Nudges pending and scheduled for today)
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    today_end = datetime.utcnow().replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()
    
    due_today = client.table("nudges").select("*", count="exact")\
        .eq("user_id", user_id)\
        .eq("status", "pending")\
        .gte("scheduled_at", today_start)\
        .lte("scheduled_at", today_end)\
        .execute()
        
    # 3. Sent This Week (Nudges sent in last 7 days)
    week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
    sent_week = client.table("nudges").select("*", count="exact")\
        .eq("user_id", user_id)\
        .eq("status", "sent")\
        .gte("sent_at", week_ago)\
        .execute()

    # 4. Needs Attention (Conversations with status 'needs_response' or 'manual')
    needs_attention = client.table("conversations").select("*", count="exact")\
        .eq("user_id", user_id)\
        .in_("status", ["needs_response", "manual_intervention"])\
        .execute()

    return {
        "awaiting_reply": awaiting.count or 0,
        "due_today": due_today.count or 0,
        "sent_this_week": sent_week.count or 0,
        "needs_attention": needs_attention.count or 0
    }

@router.get("/activity")
async def get_recent_activity(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Get recent activity feed (sent nudges and incoming replies).
    """
    client = get_client()
    user_id = user.id
    
    # Fetch recent sent nudges
    sent_nudges = client.table("nudges")\
        .select("id, contact:contacts(name), sent_at")\
        .eq("user_id", user_id)\
        .eq("status", "sent")\
        .order("sent_at", desc=True)\
        .limit(5)\
        .execute()
        
    activities = []
    
    for nudge in sent_nudges.data:
        contact_name = nudge.get("contact", {}).get("name", "Unknown")
        activities.append({
            "id": nudge["id"],
            "type": "nudge_sent",
            "description": f"Nudge sent to {contact_name}",
            "timestamp": nudge["sent_at"]
        })
        
    # TODO: Fetch recent replies from messages table if available, or conversation updates
    # For now, just return sent nudges
    
    # Sort by timestamp desc
    activities.sort(key=lambda x: x["timestamp"], reverse=True)
    
    return {
        "recent_activities": activities
    }
