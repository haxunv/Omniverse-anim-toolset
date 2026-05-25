# -*- coding: utf-8 -*-
"""
Agent Session - 对话会话管理
============================

维护一次对话的消息列表、工具调用日志、token 累计统计。

- ``add_*`` 系列：新增消息
- ``messages_for_llm``: 拼装给 LLM 的消息列表（剔除 UI 元数据）
- ``clear``: 清空历史
- ``to_dict`` / ``from_dict``: 序列化 / 反序列化（供持久化）

Phase 1 只做内存态 + 简单的按条数截断；Phase 2 再接持久化。
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .messages import (
    Message, SystemMessage, HumanMessage, AIMessage, ToolMessage, ToolCall,
)


# =============================================================================
# AgentSession
# =============================================================================

@dataclass
class AgentSession:
    """
    对话会话。

    Attributes:
        id: 会话 id
        created_at: 创建时间戳
        messages: 历史消息（按时间顺序，包括 System / Human / AI / Tool）
        total_prompt_tokens: 累计输入 token
        total_completion_tokens: 累计输出 token
        total_cost_rmb: 累计费用（元）
        max_history: 发给 LLM 的最大历史消息条数（保留最近 N 条 + system prompt）
    """
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: float = field(default_factory=time.time)
    messages: List[Message] = field(default_factory=list)
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cost_rmb: float = 0.0
    max_history: int = 30

    # ---------- 新增消息 ----------

    def add_message(self, msg: Message) -> Message:
        """添加一条消息。"""
        self.messages.append(msg)
        return msg

    def add_system(self, content: str, **metadata: Any) -> SystemMessage:
        msg = SystemMessage(content=content, metadata=dict(metadata))
        self.add_message(msg)
        return msg

    def add_human(self, content: str, **metadata: Any) -> HumanMessage:
        msg = HumanMessage(content=content, metadata=dict(metadata))
        self.add_message(msg)
        return msg

    def add_ai(
        self,
        content: str = "",
        tool_calls: Optional[List[ToolCall]] = None,
        finish_reason: str = "",
        usage: Optional[Dict[str, int]] = None,
        **metadata: Any,
    ) -> AIMessage:
        msg = AIMessage(
            content=content,
            tool_calls=list(tool_calls or []),
            finish_reason=finish_reason,
            usage=dict(usage or {}),
            metadata=dict(metadata),
        )
        self.add_message(msg)
        return msg

    def add_tool_result(
        self,
        tool_call_id: str,
        name: str,
        content: str,
        success: bool = True,
        is_error: bool = False,
        arguments: Optional[Dict[str, Any]] = None,
        **metadata: Any,
    ) -> ToolMessage:
        msg = ToolMessage(
            content=content,
            tool_call_id=tool_call_id,
            name=name,
            success=success,
            is_error=is_error,
            arguments=dict(arguments or {}),
            metadata=dict(metadata),
        )
        self.add_message(msg)
        return msg

    # ---------- 查询 ----------

    def last_message(self) -> Optional[Message]:
        return self.messages[-1] if self.messages else None

    def last_ai_message(self) -> Optional[AIMessage]:
        for msg in reversed(self.messages):
            if isinstance(msg, AIMessage):
                return msg
        return None

    def find_tool_call(self, tool_call_id: str) -> Optional[ToolCall]:
        """在最近的 AIMessage 中查找指定 id 的 ToolCall。"""
        for msg in reversed(self.messages):
            if isinstance(msg, AIMessage):
                for tc in msg.tool_calls:
                    if tc.id == tool_call_id:
                        return tc
        return None

    # ---------- 供 LLM 使用 ----------

    def messages_for_llm(self) -> List[Message]:
        """
        返回给 LLM 的消息列表。

        策略：
            - 始终保留全部 SystemMessage（通常在开头）
            - 保留最近 ``max_history`` 条非 System 消息
            - 确保不会在中间截断掉某条 AIMessage 的 ToolMessage（保持 tool_call_id 配对完整）
        """
        systems = [m for m in self.messages if isinstance(m, SystemMessage)]
        others = [m for m in self.messages if not isinstance(m, SystemMessage)]

        max_history = _get_context_int(
            "max_history_messages",
            self.max_history,
            6,
            200,
        )
        start = max(0, len(others) - max_history)
        kept = others[start:]

        # 向前回溯：如果 kept[0] 是 ToolMessage，则把它对应的 AIMessage 一起带上
        if kept and start > 0 and isinstance(kept[0], ToolMessage):
            # 找到所属的 AIMessage
            j = start - 1
            while j >= 0 and isinstance(others[j], ToolMessage):
                j -= 1
            if j >= 0 and isinstance(others[j], AIMessage):
                kept = others[j:start] + kept

        return [_clone_message_for_llm(m) for m in systems + kept]

    def compact_history_for_llm(self) -> None:
        """
        原地压缩旧消息，供 UI 的 Clear 不方便使用时手动瘦身。

        正常发送给 LLM 时 ``messages_for_llm`` 已经返回压缩副本；这个方法用于
        后续如果想在 UI 上加一个 "Compact" 按钮。
        """
        self.messages = [_clone_message_for_llm(m) for m in self.messages]

    # ---------- 统计 ----------

    def accumulate_usage(self, usage: Dict[str, int], cost_rmb: float = 0.0) -> None:
        self.total_prompt_tokens += int(usage.get("prompt_tokens", 0) or 0)
        self.total_completion_tokens += int(usage.get("completion_tokens", 0) or 0)
        self.total_cost_rmb += float(cost_rmb)

    # ---------- 生命周期 ----------

    def clear(self, keep_system: bool = True) -> None:
        if keep_system:
            self.messages = [m for m in self.messages if isinstance(m, SystemMessage)]
        else:
            self.messages.clear()
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_cost_rmb = 0.0

    # ---------- 序列化 ----------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "messages": [m.to_dict() for m in self.messages],
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_cost_rmb": self.total_cost_rmb,
        }


# =============================================================================
# LLM 上下文压缩 helpers
# =============================================================================

_CTX_SETTINGS_PREFIX = "/exts/omni.anim.drama.toolset/agent/context"


def _get_context_int(name: str, default: int, lo: int, hi: int) -> int:
    env_name = f"ANIM_AGENT_{name.upper()}"
    raw: Any = os.environ.get(env_name)
    if raw in (None, ""):
        try:
            import carb.settings  # type: ignore

            raw = carb.settings.get_settings().get(f"{_CTX_SETTINGS_PREFIX}/{name}")
        except Exception:
            raw = None
    try:
        value = int(raw) if raw not in (None, "") else default
    except Exception:
        value = default
    return max(lo, min(value, hi))


def _truncate_text_for_llm(text: str, max_chars: int, kind: str) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    head = max(0, int(max_chars * 0.7))
    tail = max(0, max_chars - head - 400)
    return json.dumps(
        {
            "__truncated_history_message__": True,
            "kind": kind,
            "original_chars": len(text),
            "kept_chars": max_chars,
            "head": text[:head],
            "tail": text[-tail:] if tail else "",
            "note": "This old conversation message was truncated before being sent to the LLM.",
        },
        ensure_ascii=False,
    )


def _compact_argument(value: Any, *, depth: int = 0) -> Any:
    max_depth = _get_context_int("max_argument_depth", 4, 1, 12)
    max_string = _get_context_int("max_argument_string_chars", 1000, 100, 10000)
    max_list = _get_context_int("max_argument_list_items", 10, 1, 100)
    max_dict = _get_context_int("max_argument_dict_items", 40, 5, 300)

    if depth >= max_depth:
        return {"__truncated_argument__": True, "type": type(value).__name__}
    if isinstance(value, str):
        return value if len(value) <= max_string else value[:max_string] + "...[truncated]"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        out = [_compact_argument(v, depth=depth + 1) for v in list(value)[:max_list]]
        if len(value) > max_list:
            out.append(
                {
                    "__truncated_argument_list__": True,
                    "original_len": len(value),
                    "kept_len": max_list,
                }
            )
        return out
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        items = list(value.items())
        for key, item in items[:max_dict]:
            out[str(key)] = _compact_argument(item, depth=depth + 1)
        if len(items) > max_dict:
            out["__truncated_argument_dict__"] = {
                "original_len": len(items),
                "kept_len": max_dict,
            }
        return out
    return str(value)


def _clone_tool_call_for_llm(tc: ToolCall) -> ToolCall:
    return ToolCall(
        id=tc.id,
        name=tc.name,
        arguments=_compact_argument(dict(tc.arguments or {})),
    )


def _clone_message_for_llm(msg: Message) -> Message:
    """返回发送给 LLM 的轻量副本，不修改 UI 中看到的原始 session。"""
    if isinstance(msg, SystemMessage):
        return SystemMessage(content=msg.content)
    if isinstance(msg, HumanMessage):
        max_chars = _get_context_int("max_user_message_chars", 20000, 1000, 200000)
        return HumanMessage(
            content=_truncate_text_for_llm(msg.content or "", max_chars, "user")
        )
    if isinstance(msg, AIMessage):
        max_chars = _get_context_int("max_assistant_message_chars", 12000, 1000, 200000)
        return AIMessage(
            content=_truncate_text_for_llm(msg.content or "", max_chars, "assistant"),
            tool_calls=[_clone_tool_call_for_llm(tc) for tc in msg.tool_calls],
            finish_reason=msg.finish_reason,
            usage=dict(msg.usage or {}),
        )
    if isinstance(msg, ToolMessage):
        max_chars = _get_context_int("max_tool_result_chars", 12000, 1000, 200000)
        return ToolMessage(
            content=_truncate_text_for_llm(msg.content or "", max_chars, "tool"),
            tool_call_id=msg.tool_call_id,
            name=msg.name,
            success=msg.success,
            is_error=msg.is_error,
            arguments=_compact_argument(dict(msg.arguments or {})),
        )
    max_chars = _get_context_int("max_other_message_chars", 8000, 1000, 100000)
    return Message(
        role=msg.role,
        content=_truncate_text_for_llm(msg.content or "", max_chars, msg.role or "message"),
    )
