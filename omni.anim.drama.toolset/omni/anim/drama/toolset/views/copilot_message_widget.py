# -*- coding: utf-8 -*-
"""
Copilot 消息行 Widget
======================

每条 ``Message``（HumanMessage / AIMessage / SystemMessage / 错误消息）渲染为一行，
占据消息流的整个宽度（类似网页聊天的扁平风格）：

- 左侧 3px 色条标识角色（user 蓝 / AI 灰 / error 红）
- 上方 header（角色 + 时间）
- 中间 content（多行自动换行）
- 下方 meta（tokens / cost，仅 AI）
"""

from __future__ import annotations

import time
from typing import Optional

import omni.ui as ui

from .styles import Colors, Sizes
from ..agent.messages import AIMessage, HumanMessage, Message, SystemMessage


# =============================================================================
# 角色色条
# =============================================================================

ACCENT_USER = 0xFF3A8EBA      # 蓝
ACCENT_AI = 0xFF5BAA6F        # 绿
ACCENT_SYSTEM = 0xFF888888    # 灰
ACCENT_ERROR = 0xFFCC4444     # 红
ACCENT_INFO = 0xFF666666

ROW_BG_AI = 0xFF252525
ROW_BG_USER = 0xFF1A2A36
ROW_BG_ERROR = 0xFF3A1E1E
ROW_BG_DEFAULT = 0xFF1E1E1E


# =============================================================================
# CopilotMessageWidget
# =============================================================================

class CopilotMessageWidget:
    """
    单条消息行（占满父容器宽度）。
    """

    def __init__(self, message: Message, kind: Optional[str] = None) -> None:
        self._message = message
        self._kind = kind or self._infer_kind(message)
        self._content_label: Optional[ui.Label] = None
        self._meta_label: Optional[ui.Label] = None
        self._build()

    @staticmethod
    def _infer_kind(msg: Message) -> str:
        if isinstance(msg, HumanMessage):
            return "user"
        if isinstance(msg, AIMessage):
            return "ai"
        if isinstance(msg, SystemMessage):
            return "system"
        return "info"

    def _accent(self) -> int:
        return {
            "user": ACCENT_USER,
            "ai": ACCENT_AI,
            "system": ACCENT_SYSTEM,
            "error": ACCENT_ERROR,
            "info": ACCENT_INFO,
        }.get(self._kind, ACCENT_INFO)

    def _row_bg(self) -> int:
        return {
            "user": ROW_BG_USER,
            "ai": ROW_BG_AI,
            "system": ROW_BG_DEFAULT,
            "error": ROW_BG_ERROR,
            "info": ROW_BG_DEFAULT,
        }.get(self._kind, ROW_BG_DEFAULT)

    # ---------- 构建 ----------

    def _build(self) -> None:
        # 整行：背景色 + 左色条 + 内容
        with ui.ZStack(height=0):
            ui.Rectangle(style={"background_color": self._row_bg(), "border_radius": 0})

            with ui.HStack(spacing=0):
                # 左侧 3px 色条
                with ui.VStack(width=3):
                    ui.Rectangle(style={"background_color": self._accent()})

                ui.Spacer(width=Sizes.MARGIN_MEDIUM)

                # 主内容列（占满剩余宽度）
                with ui.VStack(spacing=2):
                    ui.Spacer(height=6)

                    # Header
                    with ui.HStack(height=14):
                        ui.Label(
                            self._header_text(),
                            style={"font_size": 10, "color": Colors.TEXT_SECONDARY},
                        )
                        ui.Spacer()

                    ui.Spacer(height=2)

                    # Content
                    self._content_label = ui.Label(
                        self._content_text(),
                        word_wrap=True,
                        alignment=ui.Alignment.LEFT_TOP,
                        style={
                            "color": Colors.TEXT_PRIMARY,
                            "font_size": 13,
                        },
                    )

                    # Meta（AI 专属，包含 tokens / cost）
                    meta = self._meta_text()
                    if meta:
                        ui.Spacer(height=2)
                        with ui.HStack(height=12):
                            self._meta_label = ui.Label(
                                meta,
                                style={"font_size": 10, "color": Colors.TEXT_DISABLED},
                            )
                            ui.Spacer()

                    ui.Spacer(height=6)

                ui.Spacer(width=Sizes.MARGIN_MEDIUM)

    # ---------- 文本 ----------

    def _header_text(self) -> str:
        ts = time.strftime("%H:%M:%S", time.localtime(self._message.created_at))
        if self._kind == "user":
            return f"User    |  {ts}"
        if self._kind == "ai":
            model = (self._message.metadata or {}).get("model") or "AI"
            return f"AI ({model})    |  {ts}"
        if self._kind == "system":
            return f"System    |  {ts}"
        if self._kind == "error":
            return f"Error    |  {ts}"
        return f"{self._message.role or 'info'}    |  {ts}"

    def _content_text(self) -> str:
        content = (self._message.content or "").strip()
        if not content:
            if isinstance(self._message, AIMessage) and self._message.tool_calls:
                names = ", ".join(tc.name for tc in self._message.tool_calls)
                return f"(Calling tools: {names})"
            return "(empty)"
        # 简单清理 markdown 字符（防御性，AI 应当遵从 system prompt 不输出 markdown）
        return _strip_markdown(content)

    def _meta_text(self) -> str:
        if not isinstance(self._message, AIMessage):
            return ""
        usage = self._message.usage or {}
        meta = self._message.metadata or {}
        cost = meta.get("cost_rmb")
        parts = []
        prompt = usage.get("prompt_tokens") or 0
        completion = usage.get("completion_tokens") or 0
        total = usage.get("total_tokens") or (prompt + completion)
        if total:
            parts.append(f"{total} tokens")
        if cost:
            parts.append(f"RMB {cost:.4f}")
        fr = self._message.finish_reason
        if fr and fr != "stop":
            parts.append(fr)
        return "  |  ".join(parts)

    # ---------- 外部更新 ----------

    def update_message(self, message: Message) -> None:
        """消息内容变化时刷新文本（例如流式输出时）。"""
        self._message = message
        if self._content_label:
            try:
                self._content_label.text = self._content_text()
            except Exception:
                pass
        meta = self._meta_text()
        if meta and self._meta_label:
            try:
                self._meta_label.text = meta
            except Exception:
                pass


# =============================================================================
# Markdown 清理（最低限度，防止 AI 偶发输出 ** ` # 等字符）
# =============================================================================

def _strip_markdown(text: str) -> str:
    """
    把常见的 markdown 字符简单去掉/替换：
    - **bold** → bold
    - *italic* → italic（仅限不影响普通星号）
    - `code` → code
    - 行首 # / ## / ### → 去掉
    - --- 或 *** 分隔线 → 保留为空行
    保守处理，不用复杂正则避免误伤。
    """
    if not text:
        return text

    # 处理 ``` 代码块（直接保留内容）
    out_lines = []
    in_fence = False
    for line in text.splitlines():
        s = line.rstrip()
        # ``` 代码围栏
        if s.startswith("```"):
            in_fence = not in_fence
            continue
        # 行首 # / ## / ###
        ls = s.lstrip()
        if ls.startswith("#"):
            # 把 ### Title 变 Title:
            stripped = ls.lstrip("#").lstrip()
            if stripped:
                s = " " * (len(s) - len(ls)) + stripped
        out_lines.append(s)
    text = "\n".join(out_lines)

    # **bold** → bold（成对替换）
    text = _replace_pair(text, "**")
    # *italic* / _italic_（成对，避免影响乘号 / 下划线名）
    # 此处省略以避免误伤
    # `code` → code（成对）
    text = _replace_pair(text, "`")

    return text


def _replace_pair(text: str, marker: str) -> str:
    """成对去除 marker（例如 ** 或 `）。"""
    if marker not in text:
        return text
    parts = text.split(marker)
    if len(parts) < 3:
        return text
    # 偶数索引保留外部，奇数索引是被包裹的内容
    out = []
    for i, p in enumerate(parts):
        out.append(p)
    return "".join(out)
