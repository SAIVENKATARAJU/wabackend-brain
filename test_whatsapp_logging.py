
import asyncio
import httpx
import json
from app.supabase_client import get_client

NUDGE_ID = "c2eebc99-9c0b-4ef8-bb6d-6bb9bd380a13"
USER_ID = "78558f43-7e6e-46dd-beb6-bc868ad87460"
BASE_URL = "http://localhost:8001"

async def test_logging():
    print(f"--- 1. Sending WhatsApp Message for Nudge {NUDGE_ID} ---")
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        try:
            # We use the special header to bypass auth for this test user
            resp = await client.post(
                f"/nudges/{NUDGE_ID}/send",
                headers={"Authorization": f"Bearer {USER_ID}"}
            )
            print(f"Response Status: {resp.status_code}")
            try:
                print(f"Response Body: {json.dumps(resp.json(), indent=2)}")
            except:
                print(f"Response Text: {resp.text}")
                
        except Exception as e:
            print(f"Error calling API: {e}")
            return

    print("\n--- 2. Verifying Logs in Supabase ---")
    supabase = get_client()
    
    # Check Nudge Status
    nudge = supabase.table("nudges").select("status, sent_at, channel, metadata").eq("id", NUDGE_ID).single().execute()
    print("Updated Nudge Record:")
    print(json.dumps(nudge.data, indent=2))
    
    # Check Conversation Log
    # Fetch conversation_id from the nudge logic or we know it from seed
    # It was 'b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a12'
    conv_id = "b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a12"
    conv = supabase.table("conversations").select("last_outgoing_text, last_message_at").eq("id", conv_id).single().execute()
    print("\nUpdated Conversation Log:")
    print(json.dumps(conv.data, indent=2))

if __name__ == "__main__":
    asyncio.run(test_logging())
