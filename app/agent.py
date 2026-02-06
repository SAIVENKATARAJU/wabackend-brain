"""LangGraph Decision Agent with Pydantic structured output."""
import logging
from datetime import datetime
from typing import Annotated, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from app.config import settings
from app.models import (
    ActionEnum,
    DecisionRequest,
    DecisionResponse,
    FALLBACK_RESPONSE,
    StatusEnum,
)

logger = logging.getLogger(__name__)


# Pydantic model for LLM structured output
class DecisionOutput(BaseModel):
    """Structured output from the LLM decision."""
    action: Literal["wait", "reschedule", "close", "escalate"] = Field(
        description="The action to take"
    )
    after_hours: int | None = Field(
        description="Hours to wait before next action. Null if action is 'close'."
    )
    new_status: Literal["pending", "promised", "escalated", "closed"] = Field(
        description="The new conversation status"
    )
    confidence: float = Field(
        description="Confidence score between 0 and 1",
        ge=0,
        le=1
    )


# LangGraph state
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    decision: DecisionOutput | None


def get_llm(provider: str):
    """Get LLM instance based on provider name."""
    logger.info(f"Initializing LLM provider: {provider}")
    
    if provider == "openai":
        return ChatOpenAI(
            model=settings.OPENAI_MODEL,
            api_key=settings.OPENAI_API_KEY,
        )
    elif provider == "azure_openai":
        return AzureChatOpenAI(
            azure_deployment=settings.AZURE_OPENAI_DEPLOYMENT,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
        )
    elif provider == "gemini":
        return ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
        )
    else:
        raise ValueError(f"Unknown provider: {provider}")


SYSTEM_PROMPT = """You are a decision engine for a conversation management system. 
Based on the user's reply and current status, determine the next action.

Guidelines:
- If user promises to pay/act at a specific time → action="reschedule", calculate after_hours from now, status="promised"
- If user asks for help or shows frustration → action="escalate", status="escalated"
- If user confirms completion/resolution → action="close", after_hours=null, status="closed"
- If message is unclear or needs more info → action="wait", after_hours=24, status="pending"

DATE CALCULATION:
- You are given the current date and time
- Calculate after_hours as the number of hours from NOW to the promised date/time
- Examples:
  - "tomorrow" = 24 hours
  - "next week" = 168 hours (7 days)
  - "10 days" = 240 hours
  - "in 3 days" = 72 hours"""


def create_decision_graph():
    """Create the LangGraph decision graph."""
    
    # Get LLM with structured output
    llm = get_llm(settings.LLM_PROVIDER)
    structured_llm = llm.with_structured_output(DecisionOutput)
    
    # Define the decision node
    async def decide_node(state: AgentState) -> AgentState:
        """Node that makes the decision using structured output."""
        logger.info("Running decision node")
        
        # Call LLM with structured output
        result = await structured_llm.ainvoke(state["messages"])
        
        logger.info(f"Decision result: {result}")
        return {"decision": result}
    
    # Build the graph
    graph = StateGraph(AgentState)
    
    # Add nodes
    graph.add_node("decide", decide_node)
    
    # Add edges
    graph.add_edge(START, "decide")
    graph.add_edge("decide", END)
    
    return graph.compile()


async def run_decision(request: DecisionRequest) -> DecisionResponse:
    """
    Run the LangGraph decision agent with Pydantic structured output.
    
    Returns fallback response on any error.
    """
    try:
        # Build messages with current datetime
        now = datetime.now()
        current_datetime = now.strftime("%Y-%m-%d %H:%M:%S")
        current_date = now.strftime("%Y-%m-%d")
        
        user_message = f"""Current Date and Time: {current_datetime}
Today is: {current_date}

Organization: {request.org_id}
Conversation: {request.conversation_id}
Contact: {request.contact_id}
Current Status: {request.last_status.value}

User's reply: "{request.incoming_text}"

Analyze this reply and determine the next action. Calculate after_hours from the current time."""

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_message),
        ]
        
        # Create and run the graph
        logger.info(f"Running LangGraph decision with provider: {settings.LLM_PROVIDER}")
        graph = create_decision_graph()
        
        result = await graph.ainvoke({"messages": messages, "decision": None})
        
        decision: DecisionOutput = result["decision"]
        
        if decision is None:
            logger.warning("No decision from graph")
            return FALLBACK_RESPONSE
        
        return DecisionResponse(
            action=ActionEnum(decision.action),
            after_hours=decision.after_hours,
            new_status=StatusEnum(decision.new_status),
            confidence=decision.confidence
        )
        
    except Exception as e:
        logger.error(f"LangGraph decision failed: {e}")
        return FALLBACK_RESPONSE
