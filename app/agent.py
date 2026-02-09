"""LangGraph Decision Agent."""
import logging
from datetime import datetime
from typing import Annotated, Literal, List, Dict, Any, Optional
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, BaseMessage
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from app.config import settings
from app.models import DecisionRequest, DecisionResponse, ActionEnum, StatusEnum, FALLBACK_RESPONSE
from app.tools import schedule_nudge, update_crm, search_context

logger = logging.getLogger(__name__)

# --- State ---
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    thread_id: Optional[str]
    contact_info: Optional[Dict[str, Any]]
    final_output: Optional[DecisionResponse]

# --- LLM Setup ---
def get_llm():
    """Get LLM instance based on provider name."""
    provider = settings.LLM_PROVIDER
    if provider == "openai":
        return ChatOpenAI(model=settings.OPENAI_MODEL, api_key=settings.OPENAI_API_KEY)
    elif provider == "azure_openai":
        return AzureChatOpenAI(
            azure_deployment=settings.AZURE_OPENAI_DEPLOYMENT,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
        )
    elif provider == "gemini":
        return ChatGoogleGenerativeAI(model=settings.GEMINI_MODEL, google_api_key=settings.GEMINI_API_KEY)
    else:
        raise ValueError(f"Unknown provider: {provider}")

# --- Nodes ---

class DecisionOutputPydantic(BaseModel):
    """Structured output for the decision."""
    action: Literal["wait", "reschedule", "close", "escalate"]
    after_hours: Optional[int] = Field(description="Hours to wait before next check. Required if action is reschedule or wait.")
    new_status: Literal["pending", "promised", "escalated", "closed"]
    reasoning: str = Field(description="Brief explanation of the decision.")
    confidence: float

async def reason_node(state: AgentState):
    """Reason about the next step."""
    llm = get_llm()
    
    # Pre-check for clear rejection signals to avoid tool calling
    # This prevents the LLM from scheduling a nudge before deciding to close
    import re
    last_msg = state["messages"][-1]
    if isinstance(last_msg, HumanMessage):
        text = last_msg.content.lower()
        if "incoming message:" in text:
            text = text.split("incoming message:", 1)[1].strip()
            
        rejection_patterns = [
            r"not interested", r"i am not interested", r"i'm not interested",
            r"stop", r"unsubscribe", r"remove me", r"don't contact", 
            r"do not contact", r"not looking", r"fail", r"no thanks",
            r"goodbye", r"out of the deal"
        ]
        
        if any(re.search(p, text) for p in rejection_patterns):
            logger.info(f"[Agent] Detected rejection in message: '{text}'. Skipping tools.")
            # Don't bind tools, just return a direct response that forces CLOSE
            return {"messages": [AIMessage(content="User rejected. Action: CLOSE. Status: CLOSED.")]}

    # Bind tools to the LLM (for non-rejection cases)
    tools = [schedule_nudge, update_crm, search_context]
    llm_with_tools = llm.bind_tools(tools)
    
    # We force the LLM to either call a tool OR provide the final decision structure
    # But for simplicity in ReAct, we let it use tools freely, and then conclude.
    # To conclude, we can ask for a structured output or use a specific tool "submit_decision".
    # For this MVP, let's use a dual-pass approach:
    # 1. ReAct loop for gathering info/actions
    # 2. Final structured extraction for the API response.
    
    response = await llm_with_tools.ainvoke(state["messages"])
    return {"messages": [response]}

async def finalize_decision_node(state: AgentState):
    """Extract final structural decision after reasoning loop completes."""
    llm = get_llm()
    structured_llm = llm.with_structured_output(DecisionOutputPydantic)
    
    # Add a prompt to force conclusion
    messages = state["messages"] + [HumanMessage(content="Based on the above, provide the final structured decision.")]
    
    result = await structured_llm.ainvoke(messages)
    
    # Map to DecisionResponse
    final_decision = DecisionResponse(
        action=ActionEnum(result.action),
        after_hours=result.after_hours,
        new_status=StatusEnum(result.new_status),
        confidence=result.confidence
    )
    return {"final_output": final_decision}

# --- Graph ---
def create_graph():
    graph = StateGraph(AgentState)
    
    # Nodes
    graph.add_node("reason", reason_node)
    graph.add_node("tools", ToolNode([schedule_nudge, update_crm, search_context]))
    graph.add_node("finalize", finalize_decision_node)
    
    # Edges
    graph.add_edge(START, "reason")
    
    # Conditional edge: If tool call, go to tools, else go to finalize
    graph.add_conditional_edges(
        "reason",
        tools_condition,
        {"tools": "tools", "__end__": "finalize"}
    )
    
    graph.add_edge("tools", "reason") # Loop back to reason after tool use
    graph.add_edge("finalize", END)
    
    return graph.compile()

# --- Entry Points ---

async def run_decision(request: DecisionRequest) -> DecisionResponse:
    """Run the agent to make a decision on an incoming message."""
    try:
        graph = create_graph()
        
        system_msg = SystemMessage(content=f"""You are Akasavani, an AI Follow-up Assistant.
        Org: {request.org_id}, Contact: {request.contact_id}, Thread: {request.conversation_id}
        Current Status: {request.last_status.value}
        
        Analyze the incoming message and decide the next action.
        You can use tools to search context or schedule actions.
        
        CRITICAL RULES:
        1. REJECTION DETECTION: If the user indicates they are NOT interested, declining, or opting out (e.g., "I'm out", "not interested", "stop", "no thanks", "goodbye", "unsubscribe", "out of the deal"), you MUST:
           - Set action to "close"
           - Set new_status to "closed"
           - Do NOT call schedule_nudge - there's no point in following up with someone who said no
        
        2. When using schedule_nudge (only for engaged conversations), you MUST provide:
           - suggested_content: A warm, contextual follow-up message
           - For quick testing, use check_after_minutes (e.g., 2 minutes) instead of hours
        
        Finally, you must output a structured decision.
        """)
        
        user_msg = HumanMessage(content=f"Incoming Message: {request.incoming_text}")
        
        result = await graph.ainvoke({
            "messages": [system_msg, user_msg],
            "thread_id": request.conversation_id,
            "contact_info": {"id": request.contact_id} # Mock
        })
        
        return result["final_output"]
        
    except Exception as e:
        logger.error(f"Agent failed: {e}")
        return FALLBACK_RESPONSE

async def regenerate_draft(nudge_id: str, tone: Optional[str] = None):
    """Regenerate a draft for a nudge."""
    llm = get_llm()
    # logical implementation would fetch nudge context here
    prompt = f"Draft a follow-up email for nudge {nudge_id}. Tone: {tone or 'neutral'}."
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    return response.content
