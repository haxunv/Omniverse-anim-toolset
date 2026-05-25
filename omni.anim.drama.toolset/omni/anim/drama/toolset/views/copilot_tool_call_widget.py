# -*- coding: utf-8 -*-
"""
Copilot 工具调用卡片 Widget
===========================

对应 AIMessage.tool_calls 中的一个 ToolCall，以及它的审批/执行/结果全过程。

状态机（与 ``ToolCallStatus`` 对齐）：

    pending_approval → approved → running → success / error
                     → rejected
                     → blocked （destructive 未解锁）
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional

import omni.ui as ui

from .styles import Colors, Sizes
from ..agent.messages import ToolCall
from ..agent.network_node import ApprovalDecision, ToolCallStatus


# =============================================================================
# 帮助函数：把 UI mutation 推到下一帧
# =============================================================================
#
# omni.ui 不允许在事件回调（如 Button.clicked_fn）里同步调用 Container.clear() /
# 重建子树，否则报：
#   "Container::clear was called during an event or draw, this is not supported"
#
# 这里用一次性 subscription 把回调推到下一个 update tick 执行；执行后立刻解订阅，
# 避免持续触发。

def _defer_to_next_frame(callback: Callable[[], None]) -> None:
    """Run ``callback`` on the next Kit update tick (UI-mutation safe)."""
    sub_holder: list = [None]

    def _on_update(_evt: Any) -> None:
        sub = sub_holder[0]
        sub_holder[0] = None
        if sub is not None:
            try:
                sub.unsubscribe()
            except Exception:
                pass
        try:
            callback()
        except Exception:
            pass

    try:
        import omni.kit.app  # local import: keep widget importable in unit tests
        sub_holder[0] = (
            omni.kit.app.get_app()
            .get_update_event_stream()
            .create_subscription_to_pop(_on_update, name="anim.drama.toolset.tool_card_defer")
        )
    except Exception:
        # Fallback: if Kit is not running (rare), fall through to immediate call.
        try:
            callback()
        except Exception:
            pass


# =============================================================================
# 颜色
# =============================================================================

STATUS_COLORS: Dict[str, int] = {
    ToolCallStatus.PENDING_APPROVAL.value: Colors.WARNING,
    ToolCallStatus.APPROVED.value: Colors.INFO,
    ToolCallStatus.RUNNING.value: Colors.INFO,
    ToolCallStatus.SUCCESS.value: Colors.SUCCESS,
    ToolCallStatus.ERROR.value: Colors.ERROR,
    ToolCallStatus.REJECTED.value: Colors.TEXT_DISABLED,
    ToolCallStatus.BLOCKED.value: Colors.ERROR,
}

STATUS_LABELS: Dict[str, str] = {
    ToolCallStatus.PENDING_APPROVAL.value: "Pending",
    ToolCallStatus.APPROVED.value: "Approved",
    ToolCallStatus.RUNNING.value: "Running",
    ToolCallStatus.SUCCESS.value: "Done",
    ToolCallStatus.ERROR.value: "Failed",
    ToolCallStatus.REJECTED.value: "Rejected",
    ToolCallStatus.BLOCKED.value: "Blocked",
}

PERMISSION_LABELS: Dict[str, str] = {
    "read_only": "read-only",
    "mutate": "mutate",
    "destructive": "destructive",
}

PERMISSION_PREFIX: Dict[str, str] = {
    "read_only": "[R]",
    "mutate": "[M]",
    "destructive": "[!]",
}


# =============================================================================
# 回调类型
# =============================================================================

ApprovalHandler = Callable[[str, ApprovalDecision], None]
# approval_id, decision


# =============================================================================
# CopilotToolCallWidget
# =============================================================================

class CopilotToolCallWidget:
    """单个 ToolCall 卡片。"""

    def __init__(
        self,
        tool_call: ToolCall,
        permission: str = "read_only",
        category: str = "general",
        initial_status: str = ToolCallStatus.PENDING_APPROVAL.value,
        index_label: str = "",
        on_approval: Optional[ApprovalHandler] = None,
    ) -> None:
        self._tool_call = tool_call
        self._permission = permission
        self._category = category
        self._status = initial_status
        self._index_label = index_label  # e.g. "(1/3)"
        self._on_approval = on_approval

        self._approval_id: Optional[str] = None  # 由 UI 层在挂起审批时设置
        self._result_text = ""
        self._error_text = ""
        self._elapsed_ms = 0

        # UI refs
        self._status_label: Optional[ui.Label] = None
        self._result_label: Optional[ui.Label] = None
        self._buttons_frame: Optional[ui.Frame] = None
        self._built = False

        self._build()

    # ---------- 外部访问 ----------

    @property
    def tool_call_id(self) -> str:
        return self._tool_call.id

    @property
    def status(self) -> str:
        return self._status

    def bind_approval(self, approval_id: str) -> None:
        """UI 收到 pending approval 时把 approval_id 绑进来。"""
        self._approval_id = approval_id

    # ---------- 构建 ----------

    def _build(self) -> None:
        border = 0xFF4A4A4A
        with ui.ZStack(height=0):
            ui.Rectangle(
                style={
                    "background_color": 0xFF262626,
                    "border_radius": 4,
                    "border_color": border,
                    "border_width": 1,
                }
            )
            with ui.VStack(spacing=2):
                ui.Spacer(height=4)

                # 头部：名字 · 分类 · 权限 · 状态
                with ui.HStack(height=18):
                    ui.Spacer(width=8)
                    ui.Label(
                        self._header_left_text(),
                        style={"color": Colors.TEXT_PRIMARY, "font_size": 12},
                    )
                    ui.Spacer()
                    self._status_label = ui.Label(
                        self._status_text(),
                        style={"color": STATUS_COLORS.get(self._status, Colors.INFO), "font_size": 11},
                        width=100,
                        alignment=ui.Alignment.RIGHT,
                    )
                    ui.Spacer(width=8)

                ui.Separator(height=2)

                # 参数块
                args_text = self._format_arguments()
                if args_text:
                    with ui.HStack():
                        ui.Spacer(width=8)
                        ui.Label(
                            args_text,
                            word_wrap=True,
                            style={"color": Colors.TEXT_SECONDARY, "font_size": 11},
                        )
                        ui.Spacer(width=8)

                # 结果 / 错误区
                with ui.HStack():
                    ui.Spacer(width=8)
                    self._result_label = ui.Label(
                        self._result_display_text(),
                        word_wrap=True,
                        style={"color": Colors.TEXT_PRIMARY, "font_size": 11},
                        visible=bool(self._result_display_text()),
                    )
                    ui.Spacer(width=8)

                # 按钮区（可选）
                self._buttons_frame = ui.Frame(height=0)
                with self._buttons_frame:
                    self._build_buttons_if_needed()

                ui.Spacer(height=4)

        self._built = True

    def _build_buttons_if_needed(self) -> None:
        """根据当前 status 决定是否渲染按钮。"""
        if self._status != ToolCallStatus.PENDING_APPROVAL.value:
            return
        if self._permission == "read_only":
            return
        # 构建审批按钮
        with ui.HStack(spacing=4, height=26):
            ui.Spacer(width=8)
            ui.Button(
                "Approve",
                clicked_fn=lambda: self._handle_approval(ApprovalDecision.APPROVE),
                style={"background_color": 0xFF2E7D32, "color": Colors.TEXT_PRIMARY, "border_radius": 3},
                width=80,
                height=24,
            )
            ui.Button(
                "Reject",
                clicked_fn=lambda: self._handle_approval(ApprovalDecision.REJECT),
                style={"background_color": 0xFF7A2A2A, "color": Colors.TEXT_PRIMARY, "border_radius": 3},
                width=70,
                height=24,
            )
            ui.Button(
                "Approve All Remaining",
                clicked_fn=lambda: self._handle_approval(ApprovalDecision.APPROVE_ALL_REMAINING),
                style={"background_color": 0xFF2E5E7D, "color": Colors.TEXT_PRIMARY, "border_radius": 3},
                height=24,
            )
            ui.Spacer(width=8)

    # ---------- 文本 ----------

    def _header_left_text(self) -> str:
        icon = PERMISSION_PREFIX.get(self._permission, "[T]")
        perm = PERMISSION_LABELS.get(self._permission, self._permission)
        prefix = f"{icon} {self._tool_call.name}"
        if self._index_label:
            prefix += f" {self._index_label}"
        return f"{prefix}  | {perm}  | {self._category}"

    def _status_text(self) -> str:
        label = STATUS_LABELS.get(self._status, self._status)
        if self._status == ToolCallStatus.SUCCESS.value and self._elapsed_ms:
            return f"OK {label} ({self._elapsed_ms}ms)"
        if self._status == ToolCallStatus.ERROR.value:
            return f"X {label}"
        if self._status == ToolCallStatus.RUNNING.value:
            return f"{label}..."
        if self._status == ToolCallStatus.PENDING_APPROVAL.value:
            return f"... {label}"
        return label

    def _format_arguments(self) -> str:
        args = self._tool_call.arguments or {}
        if not args:
            return ""
        try:
            return "Args:\n" + json.dumps(args, ensure_ascii=False, indent=2)
        except Exception:
            return f"Args: {args}"

    def _result_display_text(self) -> str:
        if self._status == ToolCallStatus.ERROR.value:
            return f"Error: {self._error_text or '(no details)'}"
        if self._status in (ToolCallStatus.REJECTED.value, ToolCallStatus.BLOCKED.value):
            return self._error_text or ""
        if self._status == ToolCallStatus.SUCCESS.value and self._result_text:
            # 截断过长内容
            snippet = self._result_text
            if len(snippet) > 800:
                snippet = snippet[:800] + "..."
            return f"Result:\n{snippet}"
        return ""

    # ---------- 状态更新 ----------

    def update_status(
        self,
        status: str,
        elapsed_ms: Optional[int] = None,
        error: Optional[str] = None,
        result_text: Optional[str] = None,
    ) -> None:
        self._status = status
        if elapsed_ms is not None:
            self._elapsed_ms = int(elapsed_ms)
        if error is not None:
            self._error_text = error
        if result_text is not None:
            self._result_text = result_text

        # 刷新 UI
        if self._status_label:
            try:
                self._status_label.text = self._status_text()
                self._status_label.style = {
                    "color": STATUS_COLORS.get(self._status, Colors.INFO),
                    "font_size": 11,
                }
            except Exception:
                pass
        if self._result_label:
            txt = self._result_display_text()
            try:
                self._result_label.text = txt
                self._result_label.visible = bool(txt)
            except Exception:
                pass
        # 重建按钮区
        if self._buttons_frame:
            try:
                self._buttons_frame.clear()
                with self._buttons_frame:
                    self._build_buttons_if_needed()
            except Exception:
                pass

    # ---------- 内部 ----------

    def _handle_approval(self, decision: ApprovalDecision) -> None:
        if self._on_approval and self._approval_id:
            try:
                self._on_approval(self._approval_id, decision)
            except Exception:
                pass
        # 点击后把状态更新为 approved/rejected 给用户即时反馈。
        # 注意：必须 defer 到下一帧，因为 update_status 会调用 Container.clear() 重建
        # 按钮区，omni.ui 不允许在事件回调里同步执行这个操作。
        if decision == ApprovalDecision.REJECT:
            _defer_to_next_frame(
                lambda: self.update_status(ToolCallStatus.REJECTED.value, error="Rejected by user")
            )
        else:
            _defer_to_next_frame(
                lambda: self.update_status(ToolCallStatus.APPROVED.value)
            )
