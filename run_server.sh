#!/bin/bash
# Environment setup (ensure env vars are set or use .env)
# export OPENAI_API_KEY=...
# export SUPABASE_URL=...

# Run migrations (already done via my tool calls, but good to have)
# ...

# Start server
echo "Starting Akasavani Backend on port 8001..."
uv run uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
