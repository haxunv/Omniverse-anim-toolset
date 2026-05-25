# -*- coding: utf-8 -*-
"""
Agent 消息类型
==============

定义 Copilot Agent 使用的消息类型，命名对齐 ChatUSD / LangChain 风格：

- SystemMessage: 系统指令 / 任务说明
- HumanMessage: 用户输入
- AIMessage: LLM 回复（可能带 tool_calls）
- ToolMessage: 工具执行结果（回写给 LLM）

所有消息共享同一个父类 `Message`，便于 Session 统一管理与序列化。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# =============================================================================
# ToolCall（AIMessage 里承载的工具调用请求）
# =============================================================================

@dataclass
class ToolCall:
    """
    LLM 发起的一次工具调用请求。

    Attributes:
        id: 工具调用 id（由 LLM 或我们本地生成）
        name: 工具名，例如 ``modify_light``
        arguments: 参数字典（已 JSON 解析后的 dict）
    """
    id: str
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "name": self.name, "arguments": dict(self.arguments)}


# =============================================================================
# 消息基类
# =============================================================================

@dataclass
class Message:
    """
    Agent 消息基类。

    Attributes:
        role: 角色（system/user/assistant/tool）
        content: 文本内容（可能为空）
        id: 消息 id
        created_at: 创建时间戳（秒）
        metadata: 扩展元数据（token 计数、耗时等）
    """
    role: str = ""
    content: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


# =============================================================================
# 具体消息类型
# =============================================================================

@dataclass
class SystemMessage(Message):
    """系统指令消息。"""
    role: str = "system"


@dataclass
class HumanMessage(Message):
    """用户输入消息。"""
    role: str = "user"


@dataclass
class AIMessage(Message):
    """
    AI 回复消息。

    Attributes:
        tool_calls: 本轮 LLM 要求执行的工具调用列表（可能为空）
        finish_reason: 停止原因（stop / tool_calls / length 等）
        usage: token 使用统计（prompt_tokens / completion_tokens / total_tokens）
    """
    role: str = "assistant"
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: str = ""
    usage: Dict[str, int] = field(default_factory=dict)

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["tool_calls"] = [tc.to_dict() for tc in self.tool_calls]
        return d


@dataclass
class ToolMessage(Message):
    """
    工具执行结果消息（回写给 LLM）。

    Attributes:
        tool_call_id: 对应 AIMessage.tool_calls 中的某一项 id
        name: 工具名
        success: 是否成功
        is_error: 是否错误（供 LLM 判断）
        arguments: 实际被执行时使用的参数（审批后可能被用户改过）
    """
    role: str = "tool"
    tool_call_id: str = ""
    name: str = ""
    success: bool = True
    is_error: bool = False
    arguments: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["tool_call_id"] = self.tool_call_id
        d["name"] = self.name
        d["success"] = self.success
        d["is_error"] = self.is_error
        d["arguments"] = dict(self.arguments)
        return d


# =============================================================================
# 辅助工具
# =============================================================================

def make_tool_call_id() -> str:
    """生成一个工具调用 id（当 LLM 未返回 id 时使用）。"""
    return f"call_{uuid.uuid4().hex[:16]}"
