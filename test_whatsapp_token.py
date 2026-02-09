#!/usr/bin/env python3
"""
Test script to update WhatsApp access token and verify message delivery
"""

import asyncio
import sys
from app.supabase_client import get_client
from app.delivery_engine import send_whatsapp_message

# New access token
NEW_TOKEN = "EAAbs1GGw5LEBQpD0vPUinHOo0tLJLYZCwG0NOfzlZCnv8xgpQZAvvNPTNKwKFECqBnKc6nzbNpnADQV84bbKFkZCfK8VrpMAD2ZArC0AnLQkVSRhZC6MNwijN1w1JDWMzY8bY8LHIhcNVynZAmW21IWD3NOxyCqIQzl6oqjZAWe4YcobewqEtqAiuStf6ZBdB9ge6CI3OqibLZCWHC7bJ8PSXk1epRKpKZA8LA8qWtHDK2jK09eJZCUSPakZC5a4YDzKWDo7wdx5PF6vq1u9iJKSjSWZAsoRPq"

# User info
USER_ID = "523def32-86a2-4bd2-9977-a3dc394e958b"
TEST_PHONE = "+919502348056"
PHONE_NUMBER_ID = "944473658753849"

async def main():
    print("=" * 60)
    print("WhatsApp Token Update & Test Script")
    print("=" * 60)
    
    # Step 1: Update token in Supabase
    print("\n[1/3] Updating access token in Supabase...")
    client = get_client()
    
    try:
        result = client.table("integrations").update({
            "access_token": NEW_TOKEN,
            "updated_at": "now()"
        }).eq("user_id", USER_ID).eq("provider", "whatsapp").execute()
        
        if result.data:
            print("✅ Token updated successfully in database")
        else:
            print("❌ Failed to update token - no matching record found")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Database update failed: {e}")
        sys.exit(1)
    
    # Step 2: Test message delivery using TEMPLATE (not text)
    print("\n[2/3] Testing message delivery with hello_world template...")
    
    try:
        result = await send_whatsapp_message(
            phone_number=TEST_PHONE,
            msg_type="template",  # Use template, not text!
            content="hello_world",  # This is the template name
            access_token=NEW_TOKEN,
            phone_number_id=PHONE_NUMBER_ID
        )
        
        print("✅ Message sent successfully!")
        print(f"   Message ID: {result.message_id}")
        print(f"   Status: {result.status}")
        if result.recipient_wa_id:
            print(f"   Recipient WhatsApp ID: {result.recipient_wa_id}")
        
    except Exception as e:
        print(f"❌ Message delivery failed: {e}")
        print("\nPossible reasons:")
        print("  - Token is still expired (generate a fresh one)")
        print("  - 24-hour messaging window closed (need template message)")
        print("  - Phone number not added to test recipients in Meta")
        sys.exit(1)
    
    # Step 3: Verify in database
    print("\n[3/3] Verifying token in database...")
    verify = client.table("integrations").select("access_token, updated_at").eq("user_id", USER_ID).eq("provider", "whatsapp").single().execute()
    
    if verify.data:
        token_preview = verify.data["access_token"][:30] + "..."
        print(f"✅ Verified token in DB: {token_preview}")
        print(f"   Updated at: {verify.data['updated_at']}")
    
    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED!")
    print("=" * 60)
    print(f"\nCheck WhatsApp on {TEST_PHONE} for the test message.")
    print("If you don't see it, check:")
    print("  1. Message Requests folder")
    print("  2. Meta Business Suite dashboard for delivery status")
    print("  3. That the phone is added to test recipients")

if __name__ == "__main__":
    asyncio.run(main())
