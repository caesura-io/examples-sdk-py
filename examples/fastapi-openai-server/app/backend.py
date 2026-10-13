"""Read saved conversations; creation and analysis use the CaesuraO SDK."""

from typing import Any

import httpx
from caesura_openai import CaesuraOpenAIOptions

from app.config import settings


async def fetch_conversation(conversation_id: str) -> dict[str, Any]:
    # The SDK currently exposes creation, but no conversation-read method.
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{CaesuraOpenAIOptions().base_url}/api/conversation",
            params={"conversationId": conversation_id},
            headers={"Authorization": f"Bearer {settings.caesura_api_key}"},
        )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or not isinstance(data.get("conversation"), dict):
        raise ValueError("CaesuraO did not return a conversation object")
    return data
