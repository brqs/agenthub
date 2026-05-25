"""DeepSeekAdapter - DeepSeek OpenAI-compatible streaming."""

from __future__ import annotations

from app.agents.adapters.openai import OpenAIAdapter


class DeepSeekAdapter(OpenAIAdapter):
    """Adapter for DeepSeek models through its OpenAI-compatible API."""

    provider = "deepseek"
    default_model = "deepseek-v4-flash"
    api_key_setting = "deepseek_api_key"
    base_url_setting = "deepseek_base_url"
    display_name = "DeepSeek"
