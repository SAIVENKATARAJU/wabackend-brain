"""
WhatsApp Delivery Engine - Python Port

This module provides functionality to send WhatsApp messages (templates and text)
via the WhatsApp Cloud API. It's a Python equivalent of the Rust delivery engine.
"""

import httpx
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Any

from app.config import settings


# ============================================================================
# Error Types
# ============================================================================

class DeliveryErrorType(Enum):
    """Types of delivery errors that can occur."""
    MISSING_ENV_VAR = "missing_env_var"
    NETWORK_ERROR = "network_error"
    API_ERROR = "api_error"


class DeliveryError(Exception):
    """Custom exception for delivery engine errors."""
    
    def __init__(
        self,
        error_type: DeliveryErrorType,
        message: str,
        status_code: Optional[int] = None
    ):
        self.error_type = error_type
        self.message = message
        self.status_code = status_code
        super().__init__(self._format_message())
    
    def _format_message(self) -> str:
        if self.error_type == DeliveryErrorType.MISSING_ENV_VAR:
            return f"Missing environment variable: {self.message}"
        elif self.error_type == DeliveryErrorType.NETWORK_ERROR:
            return f"Network error: {self.message}"
        elif self.error_type == DeliveryErrorType.API_ERROR:
            return f"API error (HTTP {self.status_code}): {self.message}"
        return self.message


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class SendResult:
    """Result of a successful message send operation."""
    message_id: str
    recipient_wa_id: Optional[str]
    status: str


@dataclass
class WhatsAppApiError:
    """Error response from WhatsApp API."""
    message: Optional[str]
    error_type: Optional[str]
    code: Optional[int]
    fbtrace_id: Optional[str]


# TODO: Move these to per-user config in `integrations.metadata` and fetch from DB
# These should be configurable from Settings > WhatsApp Business in the UI
DEFAULT_TEMPLATE_NAME = "ai_followup"           # Approved Meta template name
DEFAULT_TEMPLATE_PARAM_NAME = "followup_message"  # Named variable in the template
DEFAULT_TEMPLATE_LANGUAGE = "en"                  # Template language code
FALLBACK_TEMPLATE_NAME = "hello_world"            # Fallback if primary template fails


def _build_template_payload(phone_number: str, template_name: str, parameters: Optional[list] = None, language: str = DEFAULT_TEMPLATE_LANGUAGE) -> dict[str, Any]:
    """Build the payload for a template message."""
    # TODO: Accept language from user's integration config instead of default
    template_data: dict[str, Any] = {
        "name": template_name,
        "language": {
            "code": language
        }
    }
    
    if parameters:
        template_data["components"] = [{
            "type": "body",
            "parameters": parameters
        }]
        
    return {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "template",
        "template": template_data
    }


def _build_text_payload(phone_number: str, text_body: str) -> dict[str, Any]:
    """Build the payload for a text message."""
    return {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "text",
        "text": {
            "body": text_body
        }
    }


# ============================================================================
# Core Logic: send_whatsapp_message Function
# ============================================================================

async def send_whatsapp_message(
    phone_number: str,
    msg_type: str,
    content: str,
    client: Optional[httpx.AsyncClient] = None,
    access_token: Optional[str] = None,
    phone_number_id: Optional[str] = None,
    template_parameters: Optional[list] = None
) -> SendResult:
    """
    Sends a WhatsApp message (template or text) to the specified recipient.
    
    Args:
        phone_number: The recipient's phone number (with country code)
        msg_type: "template" or "text"
        content: Template name (for templates) or message body (for text)
        client: Optional httpx.AsyncClient (will create one if not provided)
        access_token: Optional access token (uses env var if not provided)
        phone_number_id: Optional phone number ID (uses env var if not provided)
    
    Returns:
        SendResult with message_id, recipient_wa_id, and status
    
    Raises:
        DeliveryError: If credentials are missing, network fails, or API returns error
    """
    # Use provided credentials or fall back to environment variables
    token = access_token or settings.WHATSAPP_ACCESS_TOKEN
    if not token or token.strip() == "":
        raise DeliveryError(
            DeliveryErrorType.MISSING_ENV_VAR,
            "WHATSAPP_ACCESS_TOKEN (not provided and not set in environment)"
        )
    
    phone_id = phone_number_id or settings.WHATSAPP_PHONE_NUMBER_ID
    if not phone_id:
        raise DeliveryError(
            DeliveryErrorType.MISSING_ENV_VAR,
            "WHATSAPP_PHONE_NUMBER_ID (not provided and not set in environment)"
        )
    
    api_version = settings.WHATSAPP_API_VERSION
    
    # Build URL
    url = f"https://graph.facebook.com/{api_version}/{phone_id}/messages"
    
    # Build payload based on message type
    if msg_type == "template":
        payload = _build_template_payload(phone_number, content, template_parameters)
    else:
        payload = _build_text_payload(phone_number, content)
    
    # Headers
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Debug logging
    print(f"[DEBUG] Sending WhatsApp message:")
    print(f"[DEBUG] Template: {content if msg_type == 'template' else 'N/A'}")
    print(f"[DEBUG] Payload: {payload}")
    
    # Send request
    should_close_client = client is None
    if client is None:
        client = httpx.AsyncClient()
    
    try:
        response = await client.post(url, json=payload, headers=headers)
    except httpx.RequestError as e:
        raise DeliveryError(
            DeliveryErrorType.NETWORK_ERROR,
            str(e)
        )
    finally:
        if should_close_client:
            await client.aclose()
    
    # Check response
    if not response.is_success:
        raise DeliveryError(
            DeliveryErrorType.API_ERROR,
            response.text,
            status_code=response.status_code
        )
    
    # Parse response
    try:
        response_data = response.json()
    except Exception as e:
        raise DeliveryError(
            DeliveryErrorType.NETWORK_ERROR,
            f"Failed to parse response: {e}"
        )
    
    # Extract message ID
    messages = response_data.get("messages", [])
    message_id = messages[0].get("id", "unknown") if messages else "unknown"
    
    # Extract recipient WhatsApp ID
    contacts = response_data.get("contacts", [])
    recipient_wa_id = contacts[0].get("wa_id") if contacts else None
    
    return SendResult(
        message_id=message_id,
        recipient_wa_id=recipient_wa_id,
        status="queued"
    )


async def send_template_message(
    phone_number: str,
    template_name: str = "hello_world",
    client: Optional[httpx.AsyncClient] = None
) -> SendResult:
    """
    Convenience function to send a template message.
    
    Args:
        phone_number: The recipient's phone number (with country code)
        template_name: Name of the approved template (default: "hello_world")
        client: Optional httpx.AsyncClient
    
    Returns:
        SendResult with message_id, recipient_wa_id, and status
    """
    return await send_whatsapp_message(phone_number, "template", template_name, client)


async def send_text_message(
    phone_number: str,
    text: str,
    client: Optional[httpx.AsyncClient] = None
) -> SendResult:
    """
    Convenience function to send a text message.
    
    Note: Free-form text messages only work if the user has messaged you 
    in the last 24 hours. To START a conversation, you MUST use a template.
    
    Args:
        phone_number: The recipient's phone number (with country code)
        text: The message body
        client: Optional httpx.AsyncClient
    
    Returns:
        SendResult with message_id, recipient_wa_id, and status
    """
    return await send_whatsapp_message(phone_number, "text", text, client)


async def send_smart_nudge(
    client_supabase,
    nudge: dict,
    contact_phone: str,
    access_token: str,
    phone_number_id: str
) -> SendResult:
    """
    High-level function to send a nudge selectively using text or template.
    Checks the 24-hour window for the conversation.
    
    Template Config (hardcoded for now):
        - Template: DEFAULT_TEMPLATE_NAME ("ai_followup")
        - Parameter: DEFAULT_TEMPLATE_PARAM_NAME ("followup_message")
        - Language: DEFAULT_TEMPLATE_LANGUAGE ("en")
        - Fallback: FALLBACK_TEMPLATE_NAME ("hello_world")
    
    TODO: Fetch template config from user's integration settings:
        integration = client_supabase.table("integrations").select("metadata")
            .eq("user_id", nudge["user_id"]).eq("provider", "whatsapp").single().execute()
        template_name = integration.data["metadata"].get("template_name", DEFAULT_TEMPLATE_NAME)
        param_name = integration.data["metadata"].get("template_param_name", DEFAULT_TEMPLATE_PARAM_NAME)
    """
    from datetime import datetime, timezone
    
    content = nudge.get("approved_content") or nudge.get("draft_content") or "Hello!"
    conversation_id = nudge.get("conversation_id")
    
    # TODO: Fetch these from user's integration metadata instead of using hardcoded defaults
    template_name = DEFAULT_TEMPLATE_NAME
    param_name = DEFAULT_TEMPLATE_PARAM_NAME
    template_language = DEFAULT_TEMPLATE_LANGUAGE
    fallback_template = FALLBACK_TEMPLATE_NAME
    
    can_send_text = False
    try:
        if conversation_id:
            # Check last incoming message time
            last_msg = client_supabase.table("messages").select("created_at").eq(
                "conversation_id", conversation_id
            ).eq("direction", "incoming").order("created_at", desc=True).limit(1).execute()
            
            if last_msg.data:
                last_msg_time = datetime.fromisoformat(last_msg.data[0]["created_at"].replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                hours_since = (now - last_msg_time).total_seconds() / 3600
                can_send_text = hours_since < 24
    except Exception as e:
        print(f"Error checking message window: {e}")
        can_send_text = False
        
    if can_send_text:
        # Within 24-hour window: use simple text message (no template needed)
        return await send_whatsapp_message(
            phone_number=contact_phone,
            msg_type="text",
            content=content,
            access_token=access_token,
            phone_number_id=phone_number_id
        )
    else:
        # Outside 24-hour window: must use approved template
        try:
            # Validate content is not empty
            if not content or content.strip() == "":
                print(f"[WARNING] Content is empty, using default message")
                content = "Hi! This is a follow-up message. Let me know if you have any questions."
            
            # TODO: Build params dynamically based on user's template config
            template_params = [{
                "type": "text",
                "parameter_name": param_name,  # Must match the named variable in the Meta template
                "text": content
            }]
            
            print(f"[DEBUG] Sending template '{template_name}' with param '{param_name}'")
            
            return await send_whatsapp_message(
                phone_number=contact_phone,
                msg_type="template",
                content=template_name,
                access_token=access_token,
                phone_number_id=phone_number_id,
                template_parameters=template_params
            )
        except DeliveryError as e:
            # Template not found/approved - fall back to hello_world (no params)
            if e.status_code == 404 or "132001" in str(e):
                print(f"Template '{template_name}' not found, falling back to '{fallback_template}': {e}")
                return await send_whatsapp_message(
                    phone_number=contact_phone,
                    msg_type="template",
                    content=fallback_template,
                    access_token=access_token,
                    phone_number_id=phone_number_id
                )
            raise  # Re-raise other errors


# ============================================================================
# CLI Entry Point (for standalone testing)
# ============================================================================

if __name__ == "__main__":
    import asyncio
    import sys
    
    async def main():
        args = sys.argv[1:]
        
        if not args:
            print("Usage:")
            print("  python -m app.delivery_engine <phone_number>                    # Send hello_world template")
            print("  python -m app.delivery_engine <phone_number> <template_name>    # Send custom template")
            print("  python -m app.delivery_engine <phone_number> text \"your message\" # Send text message")
            sys.exit(0)
        
        phone_number = args[0]
        
        # Determine message type and content
        if len(args) >= 3 and args[1] == "text":
            msg_type = "text"
            content = args[2]
        elif len(args) >= 2 and args[1] != "text":
            msg_type = "template"
            content = args[1]
        else:
            msg_type = "template"
            content = "hello_world"
        
        print(f"\n[Sender] Sending {msg_type} message:")
        print(f"  To: {phone_number}")
        print(f"  Content: {content}\n")
        
        try:
            result = await send_whatsapp_message(phone_number, msg_type, content)
            print("\n========================================")
            print("MESSAGE QUEUED")
            print("========================================")
            print(f"✓ Message ID: {result.message_id}")
            print(f"  Status: {result.status}")
            if result.recipient_wa_id:
                print(f"  Recipient WA ID: {result.recipient_wa_id}")
            print("\nWatch the server logs for status updates!")
            print("========================================")
        except DeliveryError as e:
            print(f"\n✗ Failed to send message: {e}")
            if e.error_type == DeliveryErrorType.API_ERROR and e.status_code == 400 and msg_type == "text":
                print("\n[TIP] Free-form text messages only work if the user has messaged you in the last 24 hours.")
                print("      To START a conversation, you MUST use a template.")
            sys.exit(1)
    
    asyncio.run(main())
