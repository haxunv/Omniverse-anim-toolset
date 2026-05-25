# -*- coding: utf-8 -*-
"""
OpenAI 兼容后端
===============

通过 OpenAI Chat Completions 协议调用以下服务：

- 硅基流动 SiliconFlow（默认，``Pro/moonshotai/Kimi-K2.6``）
- Kimi 官方（Moonshot API）
- OpenAI
- DeepSeek
- 任何 OpenAI 兼容的自托管服务

使用纯 stdlib 的 ``urllib.request`` 实现，避免引入 ``openai`` / ``requests`` 依赖。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from ..messages import (
    AIMessage, Message, SystemMessage, HumanMessage, ToolCall, ToolMessage, make_tool_call_id,
)
from ..tool_registry import ToolDef
from .base import LLMBackend

try:
    from ...core.stage_utils import safe_log
except Exception:  # pragma: no cover
    def safe_log(msg: str, prefix: str = "Agent") -> None:
        print(f"[{prefix}] {msg}")


# =============================================================================
# OpenAICompatBackend
# =============================================================================

class OpenAICompatBackend(LLMBackend):
    """OpenAI Chat Completions 协议的后端实现。"""

    # ---------- chat ----------

    def chat(
        self,
        messages: List[Message],
        tools: Optional[List[ToolDef]] = None,
        **kwargs: Any,
    ) -> AIMessage:
        if not self.is_configured:
            raise RuntimeError("API Key not configured")
        if not self._config.base_url:
            raise RuntimeError("base_url not configured")

        url = self._config.base_url.rstrip("/") + "/chat/completions"

        payload: Dict[str, Any] = {
            "model": self._config.model,
            "messages": [self._message_to_openai(m) for m in messages],
            "temperature": kwargs.get("temperature", self._config.temperature),
            "max_tokens": kwargs.get("max_tokens", self._config.max_tokens),
        }

        if tools:
            payload["tools"] = [t.to_openai_tool() for t in tools]
            tool_choice = kwargs.get("tool_choice", "auto")
            if tool_choice:
                payload["tool_choice"] = tool_choice

        extra = dict(self._config.extra or {})
        extra.update(kwargs.get("extra", {}) or {})
        payload.update(extra)

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._config.api_key}",
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self._config.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise RuntimeError(f"HTTP {e.code} {e.reason}: {detail[:500]}") from e
        except Exception as e:
            raise RuntimeError(f"Request failed: {e}") from e

        try:
            data = json.loads(raw)
        except Exception as e:
            raise RuntimeError(f"Response parse failed: {e}; body={raw[:500]}") from e

        return self._parse_response(data)

    # ---------- test_connection ----------

    def test_connection(self) -> Tuple[bool, str]:
        if not self.is_configured:
            return False, "API Key not configured"
        try:
            msg = self.chat(
                [HumanMessage(content="ping")],
                tools=None,
                temperature=0.0,
                max_tokens=16,
            )
            return True, f"OK: {(msg.content or '').strip()[:80]}"
        except Exception as e:
            return False, f"Failed: {e}"

    # ---------- 消息 <-> OpenAI 格式 ----------

    @staticmethod
    def _message_to_openai(msg: Message) -> Dict[str, Any]:
        """把统一 Message 转成 OpenAI chat 消息格式。"""
        if isinstance(msg, SystemMessage):
            return {"role": "system", "content": msg.content or ""}

        if isinstance(msg, HumanMessage):
            return {"role": "user", "content": msg.content or ""}

        if isinstance(msg, AIMessage):
            out: Dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
            if msg.tool_calls:
                out["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                    for tc in msg.tool_calls
                ]
                # OpenAI 要求带 tool_calls 时 content 可为 null
                if not out["content"]:
                    out["content"] = None
            return out

        if isinstance(msg, ToolMessage):
            content = msg.content or ""
            if msg.is_error and not content.lower().startswith("error"):
                content = f"ERROR: {content}"
            return {
                "role": "tool",
                "tool_call_id": msg.tool_call_id,
                "content": content,
            }

        # 兜底
        return {"role": msg.role or "user", "content": msg.content or ""}

    # ---------- 响应解析 ----------

    @staticmethod
    def _parse_response(data: Dict[str, Any]) -> AIMessage:
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"No choices in response: {str(data)[:500]}")

        first = choices[0]
        message = first.get("message") or {}
        content = message.get("content") or ""
        finish_reason = first.get("finish_reason") or ""

        # tool_calls
        tool_calls: List[ToolCall] = []
        raw_tool_calls = message.get("tool_calls") or []
        for rtc in raw_tool_calls:
            fn = rtc.get("function") or {}
            name = fn.get("name") or ""
            args_raw = fn.get("arguments") or "{}"
            if isinstance(args_raw, str):
                try:
                    arguments = json.loads(args_raw) if args_raw.strip() else {}
                except Exception:
                    arguments = {"_raw": args_raw}
            elif isinstance(args_raw, dict):
                arguments = args_raw
            else:
                arguments = {}
            tool_calls.append(
                ToolCall(id=rtc.get("id") or make_tool_call_id(), name=name, arguments=arguments)
            )

        # usage（含缓存命中字段，Kimi 会在 prompt_tokens_details 里返回 cached_tokens）
        raw_usage = data.get("usage") or {}
        usage: Dict[str, int] = {
            "prompt_tokens": int(raw_usage.get("prompt_tokens", 0) or 0),
            "completion_tokens": int(raw_usage.get("completion_tokens", 0) or 0),
            "total_tokens": int(raw_usage.get("total_tokens", 0) or 0),
        }
        details = raw_usage.get("prompt_tokens_details") or {}
        cached = details.get("cached_tokens")
        if cached is None:
            cached = raw_usage.get("cached_tokens")
        if cached is not None:
            try:
                usage["cached_tokens"] = int(cached)
            except Exception:
                pass

        return AIMessage(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
        )
