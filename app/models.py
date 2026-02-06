from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class StatusEnum(str, Enum):
    """Valid conversation statuses."""
    PENDING = "pending"
    PROMISED = "promised"
    ESCALATED = "escalated"
    CLOSED = "closed"


class ActionEnum(str, Enum):
    """Valid decision actions."""
    WAIT = "wait"
    RESCHEDULE = "reschedule"
    CLOSE = "close"
    ESCALATE = "escalate"


class DecisionRequest(BaseModel):
    """Input model for the decision endpoint."""
    org_id: str = Field(..., description="Organization identifier")
    conversation_id: str = Field(..., description="Conversation identifier")
    contact_id: str = Field(..., description="Contact identifier")
    incoming_text: str = Field(..., description="Raw user reply text")
    last_status: StatusEnum = Field(..., description="Current conversation status")

    model_config = {"extra": "forbid"}


class DecisionResponse(BaseModel):
    """Output model for the decision endpoint."""
    action: ActionEnum = Field(..., description="Recommended action")
    after_hours: Optional[int] = Field(..., description="Hours to wait before next action, null if action is close")
    new_status: StatusEnum = Field(..., description="New conversation status")
    confidence: float = Field(..., ge=0, le=1, description="Confidence score between 0 and 1")

    @model_validator(mode="after")
    def validate_after_hours(self):
        """If action is close, after_hours must be null."""
        if self.action == ActionEnum.CLOSE and self.after_hours is not None:
            raise ValueError("after_hours must be null when action is 'close'")
        return self


# Fallback response when LLM fails
FALLBACK_RESPONSE = DecisionResponse(
    action=ActionEnum.WAIT,
    after_hours=24,
    new_status=StatusEnum.PENDING,
    confidence=0.3
)
