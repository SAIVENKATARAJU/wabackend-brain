"""Decision endpoint router."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.agent import run_decision
from app.config import settings
from app.models import DecisionRequest, DecisionResponse

logger = logging.getLogger(__name__)

router = APIRouter()

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_api_key(
    api_key_header: str = Security(api_key_header),
) -> str:
    """Validate the API key from the header."""
    if not settings.APP_API_KEY:
        return ""
    
    if api_key_header == settings.APP_API_KEY:
        return api_key_header
    
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Could not validate API Key",
    )


@router.post("/v1/decide", response_model=DecisionResponse)
async def decide(
    request: DecisionRequest,
    api_key: str = Depends(get_api_key)
) -> DecisionResponse:
    """
    Process incoming text and return a decision.
    
    Uses LangGraph ReAct agent with automatic tool execution.
    Returns fallback response if agent fails for any reason.
    """
    logger.info(f"Processing decision for org={request.org_id}, conv={request.conversation_id}")
    return await run_decision(request)
