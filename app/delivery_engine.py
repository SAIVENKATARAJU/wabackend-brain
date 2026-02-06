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


def _build_template_payload(phone_number: str, template_name: str) -> dict[str, Any]:
    """Build the payload for a template message."""
    return {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {
                "code": "en_US"
            }
        }
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
    client: Optional[httpx.AsyncClient] = None
) -> SendResult:
    """
    Sends a WhatsApp message (template or text) to the specified recipient.
    
    Args:
        phone_number: The recipient's phone number (with country code)
        msg_type: "template" or "text"
        content: Template name (for templates) or message body (for text)
        client: Optional httpx.AsyncClient (will create one if not provided)
    
    Returns:
        SendResult with message_id, recipient_wa_id, and status
    
    Raises:
        DeliveryError: If environment variables are missing, network fails, or API returns error
    """
    # Validate environment variables
    access_token = settings.WHATSAPP_ACCESS_TOKEN
    if not access_token or access_token.strip() == "":
        raise DeliveryError(
            DeliveryErrorType.MISSING_ENV_VAR,
            "WHATSAPP_ACCESS_TOKEN"
        )
    
    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
    if not phone_number_id:
        raise DeliveryError(
            DeliveryErrorType.MISSING_ENV_VAR,
            "WHATSAPP_PHONE_NUMBER_ID"
        )
    
    api_version = settings.WHATSAPP_API_VERSION
    
    # Build URL
    url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
    
    # Build payload based on message type
    if msg_type == "template":
        payload = _build_template_payload(phone_number, content)
    else:
        payload = _build_text_payload(phone_number, content)
    
    # Headers
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
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
