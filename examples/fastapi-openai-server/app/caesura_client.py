"""Wrap AsyncOpenAI with CaesuraO analysis and guidance injection."""

from caesura_openai import (
    CaesuraOpenAIOptions,
    SpeakerNames,
    create_async_caesura,
    create_credit_meter,
    create_debug_logger,
)
from openai import AsyncOpenAI

from app.config import settings

credit_meter = create_credit_meter()

# OpenAI credentials go only to OpenAI; CaesuraO credentials go only to CaesuraO.
# Omit base_url to use the SDK default: https://api.caesurao.com.
# mode="sync" awaits analysis before the model call, even with AsyncOpenAI.
# Similarity calculation alone does not suppress guidance; a threshold enables it.
openai = create_async_caesura(
    AsyncOpenAI(api_key=settings.openai_api_key),
    CaesuraOpenAIOptions(
        api_key=settings.caesura_api_key,
        mode=settings.caesura_mode,
        persist=settings.caesura_persist,
        speaker_names=SpeakerNames(agent=settings.caesura_agent_name, customer="Customer"),
        calculate_similarities=settings.caesura_calculate_similarities,
        similarity_threshold=settings.caesura_similarity_threshold,
        on_credit_usage=credit_meter.record,
        on_event=create_debug_logger(),
    ),
)
