"""Main entry point for the wabackend-brain API."""
import logging
# Configure Logfire
import logfire
from app.config import settings

if settings.LOG_FIRE_TOKEN:
    logfire.configure(token=settings.LOG_FIRE_TOKEN)
else:
    logfire.configure(send_to_logfire=False)

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
# Import new routers
from app.routers import auth, dashboard, conversations, contacts, nudges, webhooks, settings, cron
# Import existing router if needed, or deprecate it
from app.router import router as decision_router # Keeping for backward compat or agent specific logic

# Configure standard logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

app = FastAPI(
    title="WA Backend Brain",
    description="Akasavani Backend API",
    version="0.2.0"
)

# Instrument FastAPI and Pydantic with Logfire
logfire.instrument_fastapi(app)
logfire.instrument_pydantic()

# Configure CORS
origins = [
    "http://localhost:3000",
    "http://localhost:8000",
    "https://akasavani.vercel.app", # Add production URL
    "*" # Allow all for dev
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(conversations.router)
app.include_router(contacts.router)
app.include_router(settings.router)
app.include_router(nudges.router)
app.include_router(webhooks.router)
app.include_router(webhooks.legacy_router) # Support /webhook (singular)
app.include_router(cron.router)  # pg_cron calls this
app.include_router(decision_router) # Legacy /v1/decide

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
