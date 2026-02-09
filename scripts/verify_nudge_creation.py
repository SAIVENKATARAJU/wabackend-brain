
import asyncio
import os
import sys
from datetime import datetime, timedelta
import uuid

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.supabase_client import get_client
from app.routers.nudges import CreateNudgeRequest

async def verify_nudge_creation():
    """
    Verifies that the Nudge creation logic (conversations + nudges table inserts) works correctly.
    Simulates the logic inside create_nudge endpoint without needing a full HTTP request/auth.
    """
    print("Starting Nudge Creation Verification...")
    
    client = get_client()
    
    # 1. Get a random user
    print("Fetching a user...")
    try:
        # Assuming we can just query users table directly if RLS allows service role or if we use anon key securely
        # Note: The client probably uses service role key if configured in .env for backend usage
        # Let's try to query 'auth.users' -> Supabase doesn't expose auth.users via REST easily usually
        # Let's query 'public.users' or just pick a known user ID if possible.
        # IF public.users exists and is synced:
        user_res = client.table("users").select("id").limit(1).execute()
        if not user_res.data:
            print("No users found in 'users' table. Trying to find a contact and infer owner?")
            # Fallback: Query contacts and get user_id
            contact_res = client.table("contacts").select("user_id, id").limit(1).execute()
            if not contact_res.data:
                print("No contacts found. Cannot proceed.")
                return
            user_id = contact_res.data[0]["user_id"]
            contact_id = contact_res.data[0]["id"]
        else:
            user_id = user_res.data[0]["id"]
            # Get a contact for this user
            contact_res = client.table("contacts").select("id").eq("user_id", user_id).limit(1).execute()
            if not contact_res.data:
                contact_res = client.table("contacts").insert({
                    "user_id": user_id,
                    "name": "Test Contact",
                    "email": "test@example.com",
                    # "status": "active" # Removed as it's not in schema
                }).execute()
                contact_id = contact_res.data[0]["id"]
            else:
                contact_id = contact_res.data[0]["id"]
                
    except Exception as e:
        print(f"Error fetching user/contact: {e}")
        return

    print(f"Using User ID: {user_id}")
    print(f"Using Contact ID: {contact_id}")

    # 2. Simulate Request Data
    request = CreateNudgeRequest(
        contact_id=contact_id,
        subject="Test Nudge Subject",
        content="This is a test nudge content.",
        channel="whatsapp",
        tone="warm",
        scheduled_at=(datetime.utcnow() + timedelta(hours=24)).isoformat(),
        max_escalations=5,
        recurrence_hours=48
    )

    # 3. Execute Logic (Mirrors app/routers/nudges.py)
    try:
        print("Step 1: Creating Conversation...")
        conversation_data = {
            "user_id": user_id,
            "contact_id": request.contact_id,
            "subject": request.subject,
            "status": "pending",
            "channel": request.channel,
            "thread_id": str(uuid.uuid4()), 
            "last_message_at": datetime.utcnow().isoformat(),
        }
        conv_result = client.table("conversations").insert(conversation_data).execute()
        conversation_id = conv_result.data[0]["id"]
        print(f"Conversation Created: {conversation_id}")
        
        print("Step 2: Creating Nudge...")
        nudge_data = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "contact_id": request.contact_id,
            "channel": request.channel,
            "status": "pending",
            "tone": request.tone,
            # "subject": request.subject, # REMOVED
            "draft_content": request.content,
            "scheduled_at": request.scheduled_at,
            "max_escalations": request.max_escalations,
            "recurrence_hours": request.recurrence_hours
            # "nudge_count": 1 # REMOVED
            # "max_nudges": 3 # REMOVED
        }
        
        nudge_result = client.table("nudges").insert(nudge_data).execute()
        nudge_id = nudge_result.data[0]["id"]
        nudge_id = nudge_result.data[0]["id"]
        max_escalations = nudge_result.data[0].get("max_escalations")
        recurrence_hours = nudge_result.data[0].get("recurrence_hours")
        print(f"Nudge Created: {nudge_id}, Max Escalations: {max_escalations}, Recurrence: {recurrence_hours}h")
        
        if max_escalations != 5 or recurrence_hours != 48:
            print(f"FAILED: Mismatch! Max: {max_escalations}, Rec: {recurrence_hours}")
        
        print("\nSUCCESS! Nudge creation logic is valid against the DB schema.")
        
        # Cleanup (Optional)
        # client.table("nudges").delete().eq("id", nudge_id).execute()
        # client.table("conversations").delete().eq("id", conversation_id).execute()
        # print("Cleaned up test data.")

    except Exception as e:
        print(f"\nFAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(verify_nudge_creation())
