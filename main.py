"""Main entry point for the wabackend-brain API."""
import logging
import os

# Configure Logfire FIRST, before any other imports that might use it
import logfire

LOG_FIRE_TOKEN = os.environ.get("LOG_FIRE_TOKEN")
if LOG_FIRE_TOKEN:
    logfire.configure(token=LOG_FIRE_TOKEN)
else:
    # Skip logfire if no token provided (don't require auth)
    logfire.configure(send_to_logfire=False)

from fastapi import FastAPI

from app.config import settings
from app.router import router
from app.webhook import router as webhook_router

# Configure standard logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

app = FastAPI(
    title="WA Backend Brain",
    description="Decision API for conversation management",
    version="0.1.0"
)

# Instrument FastAPI and Pydantic with Logfire
logfire.instrument_fastapi(app)
logfire.instrument_pydantic()

app.include_router(router)
app.include_router(webhook_router)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
