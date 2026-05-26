"""Compatibility shim for the legacy top-level DeepSeek adapter."""

from __future__ import annotations

from app.agents.adapters.openai import OpenAIAdapter


class DeepSeekAdapter(OpenAIAdapter):
    """Legacy DeepSeek adapter using the ModelGateway OpenAI-compatible path."""

    provider = "deepseek"
    default_model = "deepseek-v4-flash"
    api_key_setting = "deepseek_api_key"
    base_url_setting = "deepseek_base_url"
    display_name = "DeepSeek"
