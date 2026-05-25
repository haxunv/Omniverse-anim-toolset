# -*- coding: utf-8 -*-
"""
LLMBackend 抽象基类
===================

定义所有 LLM 后端共享的接口。

- ``chat(messages, tools, **kwargs) -> AIMessage``：同步调用 LLM
- ``test_connection() -> (bool, str)``：测试连通性
- ``estimate_cost_rmb(usage) -> float``：按后端定价估算本次调用花费

具体后端：

- ``OpenAICompatBackend``：Kimi / OpenAI / DeepSeek / SiliconFlow 等
- ``GeminiBackend``：Google Gemini 原生 API
- ``ClaudeBackend``：（Phase 3）
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..messages import AIMessage, Message
from ..tool_registry import ToolDef


# =============================================================================
# BackendConfig
# =============================================================================

@dataclass
class BackendConfig:
    """
    LLM 后端配置。

    Attributes:
        provider: 标识（siliconflow / kimi_official / openai / deepseek / custom / gemini）
        base_url: API endpoint
        api_key: API 密钥
        model: 模型名
        temperature: 采样温度
        max_tokens: 最大输出 token
        timeout: 请求超时（秒）
        price_input_per_m: 输入价格（元/M tokens，缓存未命中）
        price_output_per_m: 输出价格（元/M tokens）
        price_cached_input_per_m: 输入价格（元/M tokens，缓存命中）
        extra: 额外参数（透传给具体后端）
    """
    provider: str = "siliconflow"
    base_url: str = "https://api.siliconflow.cn/v1"
    api_key: str = ""
    model: str = "Pro/moonshotai/Kimi-K2.6"
    temperature: float = 0.3
    max_tokens: int = 4096
    timeout: int = 120
    price_input_per_m: float = 6.5
    price_output_per_m: float = 27.0
    price_cached_input_per_m: float = 1.1
    extra: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Provider 预设
# =============================================================================

PROVIDER_PRESETS: Dict[str, Dict[str, Any]] = {
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "Pro/moonshotai/Kimi-K2.6",
        "price_input_per_m": 6.5,
        "price_output_per_m": 27.0,
        "price_cached_input_per_m": 1.1,
    },
    "kimi_official": {
        "base_url": "https://api.moonshot.ai/v1",
        "model": "kimi-k2.6",
        "price_input_per_m": 6.5,
        "price_output_per_m": 27.0,
        "price_cached_input_per_m": 1.1,
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o",
        "price_input_per_m": 18.0,  # 约 $2.5/M = ¥18
        "price_output_per_m": 72.0,  # 约 $10/M = ¥72
        "price_cached_input_per_m": 9.0,
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "price_input_per_m": 2.0,
        "price_output_per_m": 8.0,
        "price_cached_input_per_m": 0.5,
    },
    "custom": {
        "base_url": "",
        "model": "",
        "price_input_per_m": 6.5,
        "price_output_per_m": 27.0,
        "price_cached_input_per_m": 1.1,
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "model": "gemini-2.0-flash",
        "price_input_per_m": 0.75,  # Flash 估算
        "price_output_per_m": 3.0,
        "price_cached_input_per_m": 0.2,
    },
}


def apply_preset(config: BackendConfig, provider: str) -> BackendConfig:
    """把预设值填充到 config（空字段才覆盖）。"""
    preset = PROVIDER_PRESETS.get(provider, {})
    if not preset:
        return config
    config.provider = provider
    if not config.base_url:
        config.base_url = preset.get("base_url", config.base_url)
    if not config.model:
        config.model = preset.get("model", config.model)
    # 价格始终覆盖为预设
    config.price_input_per_m = preset.get("price_input_per_m", config.price_input_per_m)
    config.price_output_per_m = preset.get("price_output_per_m", config.price_output_per_m)
    config.price_cached_input_per_m = preset.get("price_cached_input_per_m", config.price_cached_input_per_m)
    return config


# =============================================================================
# LLMBackend
# =============================================================================

class LLMBackend(abc.ABC):
    """所有 LLM 后端的抽象基类。"""

    def __init__(self, config: BackendConfig) -> None:
        self._config = config

    @property
    def config(self) -> BackendConfig:
        return self._config

    @property
    def is_configured(self) -> bool:
        return bool(self._config.api_key)

    # ---------- 子类必须实现 ----------

    @abc.abstractmethod
    def chat(
        self,
        messages: List[Message],
        tools: Optional[List[ToolDef]] = None,
        **kwargs: Any,
    ) -> AIMessage:
        """
        同步调用 LLM 一轮。

        Args:
            messages: 历史消息（按顺序）
            tools: 可用工具列表（None = 不启用 tool use）
            **kwargs: 透传给后端（temperature、max_tokens 等可覆盖）

        Returns:
            AIMessage: LLM 回复。若有 tool_calls，调用方负责执行后回写 ToolMessage 再次调用。
        """
        raise NotImplementedError

    @abc.abstractmethod
    def test_connection(self) -> Tuple[bool, str]:
        """测试连通性，返回 (success, message)。"""
        raise NotImplementedError

    # ---------- 可选覆盖 ----------

    def estimate_cost_rmb(self, usage: Dict[str, int]) -> float:
        """
        根据 usage 估算本次调用花费（人民币）。

        usage 约定字段：
            - prompt_tokens
            - completion_tokens
            - cached_tokens（可选，命中缓存的 token 数）
        """
        if not usage:
            return 0.0
        prompt = int(usage.get("prompt_tokens", 0) or 0)
        completion = int(usage.get("completion_tokens", 0) or 0)
        cached = int(usage.get("cached_tokens", 0) or 0)

        uncached_prompt = max(0, prompt - cached)
        cost = (
            uncached_prompt * self._config.price_input_per_m / 1_000_000.0
            + cached * self._config.price_cached_input_per_m / 1_000_000.0
            + completion * self._config.price_output_per_m / 1_000_000.0
        )
        return cost

    # ---------- 配置更新 ----------

    def update_config(self, **changes: Any) -> None:
        for k, v in changes.items():
            if hasattr(self._config, k):
                setattr(self._config, k, v)
