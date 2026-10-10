from __future__ import annotations

import os

from dotenv import dotenv_values

from app.core.config import ROOT_DIR, Settings
from app.domain.agent.chat_errors import llm_disabled, llm_not_configured
from app.services.agent.llm.contracts import LLMProvider
from app.services.agent.llm.openai_compatible import OpenAICompatibleProvider


def build_llm_provider(settings: Settings) -> LLMProvider:
    config = settings.agent_config
    if config is None or not config.llm_enabled:
        raise llm_disabled()
    key_name = config.llm.api_key_env
    api_key = os.environ.get(key_name)
    if not api_key:
        value = dotenv_values(ROOT_DIR / ".env").get(key_name)
        api_key = value if isinstance(value, str) else None
    if not api_key:
        raise llm_not_configured()
    return OpenAICompatibleProvider(config.llm, api_key)
