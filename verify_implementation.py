import httpx
import asyncio
import os

BASE_URL = "http://localhost:8001"
TOKEN = "MOCK_TOKEN_IF_NEEDED" # In real scenario, use Supabase client to get token

async def verify():
    print(f"Verifying backend at {BASE_URL}...")
    
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        # 1. Health Check
        try:
            resp = await client.get("/health")
            print(f"Health Check: {resp.status_code} - {resp.json()}")
        except Exception as e:
            print(f"Health Check Failed: {e}")
            return

        # 2. Dashboard Stats (BFF)
        # Assuming open endpoint or handled by mock auth
        # If strict auth, this might fail unless we mocked auth dependency
        try:
            # We implemented get_current_user that checks Supabase.
            # Without valid token, this will fail.
            # But the user can verify manually via swagger at /docs
            resp = await client.get("/dashboard/stats")
            if resp.status_code == 401:
                print("Dashboard Stats: 401 Unauthorized (Expected without token)")
                print("Run verification with valid token or disable auth for testing.")
            else:
                 print(f"Dashboard Stats: {resp.status_code} - {resp.json()}")
        except Exception as e:
            print(f"Dashboard Check Failed: {e}")

    print("\nVerification steps complete. Check /docs for full API testing.")

if __name__ == "__main__":
    asyncio.run(verify())
