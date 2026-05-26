"""DeepSeek raw model backend for ModelGateway."""

from __future__ import annotations

from app.agents.model_gateway.openai import OpenAIBackend


class DeepSeekBackend(OpenAIBackend):
    """DeepSeek backend using the OpenAI-compatible streaming path."""

    provider = "deepseek"
    default_model = "deepseek-v4-flash"
    api_key_setting = "deepseek_api_key"
    base_url_setting = "deepseek_base_url"
    display_name = "DeepSeek"
