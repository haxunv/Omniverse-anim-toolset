# -*- coding: utf-8 -*-
"""
AI Camera Module
================

AI-powered camera shot generation using LLM.

支持的后端:
    - OllamaClient: 本地运行，需安装 Ollama
    - SiliconFlowClient: 硅基流动，国内免费 API
    - GroqClient: Groq，极速免费 API
    - DeepSeekClient: DeepSeek 官方 API
    - AutoClient: 自动选择可用后端

推荐使用:
    from omni.anim.drama.toolset.ai import AutoClient
    client = AutoClient()  # 自动选择
    result = client.generate_shot_params("环绕镜头")
"""

from .llm_client import (
    LLMClient,
    OllamaClient,
    OpenAIClient,
    OpenRouterClient,
    SiliconFlowClient,
    GroqClient,
    DeepSeekClient,
    AutoClient,
)

__all__ = [
    "LLMClient",
    "OllamaClient",
    "OpenAIClient",
    "OpenRouterClient",
    "SiliconFlowClient",
    "GroqClient",
    "DeepSeekClient",
    "AutoClient",
]

