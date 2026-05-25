# -*- coding: utf-8 -*-
"""
Gemini 后端
===========

调用 Google Gemini 原生 ``generateContent`` 协议，支持 ``function_declarations``（function calling）。

纯 stdlib 实现（urllib），不依赖 ``google-generativeai`` SDK。
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


class GeminiBackend(LLMBackend):
    """Gemini 原生协议后端。"""

    def chat(
        self,
        messages: List[Message],
        tools: Optional[List[ToolDef]] = None,
        **kwargs: Any,
    ) -> AIMessage:
        if not self.is_configured:
            raise RuntimeError("API Key not configured")

        base = (self._config.base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        is_custom = "generativelanguage.googleapis.com" not in base

        if is_custom:
            url = f"{base}/models/{self._config.model}:generateContent"
            headers = {
                "Content-Type": "application/json",
                "x-api-key": self._config.api_key,
                "Authorization": f"Bearer {self._config.api_key}",
            }
        else:
            url = f"{base}/models/{self._config.model}:generateContent?key={self._config.api_key}"
            headers = {"Content-Type": "application/json"}

        system_instruction, contents = self._messages_to_gemini(messages)

        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": kwargs.get("temperature", self._config.temperature),
                "maxOutputTokens": kwargs.get("max_tokens", self._config.max_tokens),
            },
        }
        if system_instruction:
            payload["systemInstruction"] = {"role": "system", "parts": [{"text": system_instruction}]}

        if tools:
            payload["tools"] = [
                {
                    "functionDeclarations": [t.to_gemini_function() for t in tools],
                }
            ]

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

    def test_connection(self) -> Tuple[bool, str]:
        if not self.is_configured:
            return False, "API Key not configured"
        try:
            msg = self.chat(
                [HumanMessage(content="Hello, respond with 'OK'.")],
                tools=None,
                temperature=0.0,
                max_tokens=16,
            )
            return True, f"OK: {(msg.content or '').strip()[:80]}"
        except Exception as e:
            return False, f"Failed: {e}"

    # ---------- 消息转换 ----------

    @staticmethod
    def _messages_to_gemini(messages: List[Message]) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Gemini 用 user / model 两种 role。把 SystemMessage 合并成 systemInstruction，
        AIMessage 转 model，其余转 user。

        ToolMessage 在 Gemini 中用 ``functionResponse`` parts 表达，
        AIMessage.tool_calls 在 Gemini 中用 ``functionCall`` parts 表达。
        """
        system_parts: List[str] = []
        contents: List[Dict[str, Any]] = []

        for msg in messages:
            if isinstance(msg, SystemMessage):
                if msg.content:
                    system_parts.append(msg.content)
                continue

            if isinstance(msg, HumanMessage):
                contents.append({"role": "user", "parts": [{"text": msg.content or ""}]})
                continue

            if isinstance(msg, AIMessage):
                parts: List[Dict[str, Any]] = []
                if msg.content:
                    parts.append({"text": msg.content})
                for tc in msg.tool_calls:
                    parts.append(
                        {
                            "functionCall": {
                                "name": tc.name,
                                "args": dict(tc.arguments or {}),
                            }
                        }
                    )
                if not parts:
                    parts.append({"text": ""})
                contents.append({"role": "model", "parts": parts})
                continue

            if isinstance(msg, ToolMessage):
                # Gemini functionResponse
                try:
                    response_obj: Any = json.loads(msg.content) if msg.content else {}
                except Exception:
                    response_obj = {"result": msg.content}
                if not isinstance(response_obj, dict):
                    response_obj = {"result": response_obj}
                contents.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "functionResponse": {
                                    "name": msg.name,
                                    "response": response_obj,
                                }
                            }
                        ],
                    }
                )
                continue

            # 兜底
            contents.append({"role": "user", "parts": [{"text": msg.content or ""}]})

        return "\n\n".join(system_parts), contents

    # ---------- 响应解析 ----------

    @staticmethod
    def _parse_response(data: Dict[str, Any]) -> AIMessage:
        candidates = data.get("candidates") or []
        if not candidates:
            raise RuntimeError(f"No candidates in Gemini response: {str(data)[:500]}")

        first = candidates[0]
        content = first.get("content") or {}
        parts = content.get("parts") or []

        text_chunks: List[str] = []
        tool_calls: List[ToolCall] = []

        for part in parts:
            if "text" in part and part["text"]:
                text_chunks.append(part["text"])
            fc = part.get("functionCall")
            if fc:
                name = fc.get("name") or ""
                args = fc.get("args") or {}
                if not isinstance(args, dict):
                    args = {"_raw": args}
                tool_calls.append(
                    ToolCall(id=make_tool_call_id(), name=name, arguments=args)
                )

        usage_meta = data.get("usageMetadata") or {}
        usage: Dict[str, int] = {
            "prompt_tokens": int(usage_meta.get("promptTokenCount", 0) or 0),
            "completion_tokens": int(usage_meta.get("candidatesTokenCount", 0) or 0),
            "total_tokens": int(usage_meta.get("totalTokenCount", 0) or 0),
        }
        cached = usage_meta.get("cachedContentTokenCount")
        if cached is not None:
            try:
                usage["cached_tokens"] = int(cached)
            except Exception:
                pass

        return AIMessage(
            content="".join(text_chunks),
            tool_calls=tool_calls,
            finish_reason=first.get("finishReason") or "",
            usage=usage,
        )
