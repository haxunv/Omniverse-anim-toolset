# -*- coding: utf-8 -*-
"""
Copilot Tab 主面板
==================

挂在主窗口 "AI Copilot" Tab 下的内容容器。

布局：

- 顶部工具条（标题 / Settings / Clear / 状态 / cost）
- 中部消息流（滚动区域，按时间顺序展示消息气泡 + 工具调用卡片）
- 底部输入区（多行输入框 + Send / Cancel）

每帧通过 ``omni.kit.app`` update 事件 drain ``CopilotViewModel`` 的事件与审批队列。

注：所有 UI 显示文本均为纯英文 ASCII（OV 字体不支持中文与 emoji）。
"""

from __future__ import annotations

import traceback
from typing import Dict, List, Optional

import omni.ui as ui

from .styles import Colors, Sizes
from .copilot_message_widget import CopilotMessageWidget
from .copilot_tool_call_widget import CopilotToolCallWidget
from .copilot_settings_dialog import CopilotSettingsDialog

from ..viewmodels.copilot_vm import CopilotViewModel, PendingApproval
from ..agent.messages import AIMessage, HumanMessage, Message, SystemMessage
from ..agent.network_node import (
    AgentEvent, AgentEventType, ApprovalDecision, ToolCallStatus,
)


class CopilotPanel:
    """AI Copilot Tab 主面板。"""

    def __init__(self, vm: CopilotViewModel) -> None:
        self._vm = vm

        # UI refs
        self._root_frame: Optional[ui.Frame] = None
        self._status_label: Optional[ui.Label] = None
        self._messages_stack: Optional[ui.VStack] = None
        self._scroll: Optional[ui.ScrollingFrame] = None
        self._input_field: Optional[ui.StringField] = None
        self._send_button: Optional[ui.Button] = None
        self._cancel_button: Optional[ui.Button] = None
        self._cost_label: Optional[ui.Label] = None

        # 工具调用卡片索引
        self._tool_cards: Dict[str, CopilotToolCallWidget] = {}
        # approval_id → tool_call_id 反查
        self._approval_to_call: Dict[str, str] = {}

        # 设置弹窗（按需创建）
        self._settings_dialog: Optional[CopilotSettingsDialog] = None

        # 订阅 app update 事件
        self._update_sub = None

        # 连接 VM 回调
        self._vm.add_event_callback(self._on_vm_event_ui)
        self._vm.add_pending_approval_callback(self._on_vm_pending_approval_ui)
        self._vm.add_running_changed_callback(self._on_running_changed)
        self._vm.add_session_cleared_callback(self._on_session_cleared)
        self._vm.add_config_changed_callback(self._on_config_changed)

    # =========================================================================
    # 构建（在外部容器 ``with`` 块里调用）
    # =========================================================================

    def build(self) -> None:
        self._root_frame = ui.Frame(
            style={"background_color": Colors.BACKGROUND_DARK},
        )
        with self._root_frame:
            with ui.VStack(spacing=0):
                # 顶部工具条
                self._build_header()
                ui.Separator(height=1)

                # 消息流
                with ui.Frame():
                    self._scroll = ui.ScrollingFrame(
                        horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                        vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
                        style={"background_color": 0xFF1E1E1E},
                    )
                    with self._scroll:
                        self._messages_stack = ui.VStack(
                            spacing=2,
                        )
                        # 重建已有 session 消息
                        self._rebuild_all_messages()

                ui.Separator(height=1)

                # 状态 / 费用
                with ui.HStack(height=18):
                    ui.Spacer(width=Sizes.MARGIN_MEDIUM)
                    self._status_label = ui.Label(
                        self._status_text(),
                        style={"color": Colors.TEXT_SECONDARY, "font_size": 10},
                    )
                    ui.Spacer()
                    self._cost_label = ui.Label(
                        self._cost_text(),
                        style={"color": Colors.TEXT_SECONDARY, "font_size": 10},
                    )
                    ui.Spacer(width=Sizes.MARGIN_MEDIUM)

                # 输入区
                self._build_input_area()

        # 订阅 app update
        self._subscribe_app_update()

    def _build_header(self) -> None:
        with ui.HStack(height=28, style={"background_color": Colors.BACKGROUND}):
            ui.Spacer(width=Sizes.MARGIN_MEDIUM)
            ui.Label(
                "Anime Agent",
                style={"font_size": 13, "color": Colors.TEXT_PRIMARY},
            )
            ui.Spacer()
            ui.Button(
                "Settings",
                width=70, height=22,
                clicked_fn=self._open_settings,
                tooltip="Configure LLM provider, API key, model and behavior",
                style={"background_color": Colors.PRIMARY, "color": Colors.TEXT_PRIMARY,
                       "border_radius": 3, "font_size": 11},
            )
            ui.Spacer(width=4)
            ui.Button(
                "Clear",
                width=50, height=22,
                clicked_fn=self._clear_conversation,
                tooltip="Clear conversation history",
                style={"background_color": 0xFF5A5A5A, "color": Colors.TEXT_PRIMARY,
                       "border_radius": 3, "font_size": 11},
            )
            ui.Spacer(width=Sizes.MARGIN_MEDIUM)

    def _build_input_area(self) -> None:
        with ui.VStack(
            spacing=Sizes.SPACING_SMALL,
            margin=Sizes.MARGIN_MEDIUM,
            height=0,
        ):
            with ui.ZStack(height=72):
                ui.Rectangle(style={
                    "background_color": Colors.BACKGROUND_DARK,
                    "border_radius": 4,
                    "border_color": Colors.BORDER,
                    "border_width": 1,
                })
                with ui.HStack():
                    ui.Spacer(width=6)
                    self._input_field = ui.StringField(
                        multiline=True,
                        height=68,
                        style={
                            "background_color": 0x00000000,
                            "color": Colors.TEXT_PRIMARY,
                            "font_size": 12,
                        },
                    )
                    ui.Spacer(width=6)

            with ui.HStack(height=Sizes.BUTTON_HEIGHT, spacing=Sizes.SPACING_SMALL):
                self._send_button = ui.Button(
                    "Send",
                    clicked_fn=self._send_current_input,
                    style={"background_color": Colors.PRIMARY, "color": Colors.TEXT_PRIMARY,
                           "border_radius": 3},
                    height=Sizes.BUTTON_HEIGHT,
                )
                self._cancel_button = ui.Button(
                    "Cancel",
                    clicked_fn=self._cancel_running,
                    style={"background_color": 0xFF5A5A5A, "color": Colors.TEXT_PRIMARY,
                           "border_radius": 3},
                    height=Sizes.BUTTON_HEIGHT,
                    width=80,
                )
                self._cancel_button.visible = False

    # =========================================================================
    # Session 消息渲染
    # =========================================================================

    def _rebuild_all_messages(self) -> None:
        """从 session 重建全部消息（仅在初次构建 / clear 时使用）。"""
        if not self._messages_stack:
            return
        try:
            self._messages_stack.clear()
        except Exception:
            pass

        self._tool_cards.clear()
        self._approval_to_call.clear()

        with self._messages_stack:
            for msg in self._vm.session.messages:
                self._append_message(msg)

    def _append_message(self, msg: Message) -> None:
        """把一条消息追加到消息流末尾。"""
        if self._messages_stack is None:
            return

        # SystemMessage 默认不显示
        if isinstance(msg, SystemMessage):
            return

        try:
            with self._messages_stack:
                CopilotMessageWidget(msg)
                # AIMessage 紧跟其 tool_calls 卡片
                if isinstance(msg, AIMessage) and msg.tool_calls:
                    total = len(msg.tool_calls)
                    for i, tc in enumerate(msg.tool_calls, 1):
                        card = CopilotToolCallWidget(
                            tool_call=tc,
                            permission=(msg.metadata or {}).get("_perm_hint", "read_only"),
                            category=(msg.metadata or {}).get("_cat_hint", "general"),
                            initial_status=ToolCallStatus.PENDING_APPROVAL.value,
                            index_label=f"({i}/{total})" if total > 1 else "",
                            on_approval=self._on_tool_card_approval,
                        )
                        self._tool_cards[tc.id] = card
        except Exception:
            traceback.print_exc()

        self._scroll_to_bottom()

    def _append_plain(self, kind: str, text: str) -> None:
        """追加一条状态/错误气泡（非 session 消息）。"""
        if self._messages_stack is None:
            return

        from ..agent.messages import Message as _Msg
        msg = _Msg(role="info", content=text)

        with self._messages_stack:
            CopilotMessageWidget(msg, kind=kind)

        self._scroll_to_bottom()

    # =========================================================================
    # VM 事件 / 审批回调（在 UI 线程）
    # =========================================================================

    def _on_vm_event_ui(self, evt: AgentEvent) -> None:
        try:
            if evt.type == AgentEventType.AI_MESSAGE:
                msg = evt.payload.get("message")
                if isinstance(msg, AIMessage):
                    self._append_message(msg)

            elif evt.type == AgentEventType.TOOL_CALL_STARTED:
                tc_id = evt.payload.get("tool_call_id") or ""
                card = self._tool_cards.get(tc_id)
                if card:
                    perm = evt.payload.get("permission")
                    if perm:
                        card._permission = perm
                    cat = evt.payload.get("category")
                    if cat:
                        card._category = cat
                    status = evt.payload.get("status") or ToolCallStatus.PENDING_APPROVAL.value
                    card.update_status(status)

            elif evt.type == AgentEventType.TOOL_CALL_UPDATED:
                tc_id = evt.payload.get("tool_call_id") or ""
                card = self._tool_cards.get(tc_id)
                if card:
                    status = evt.payload.get("status") or card.status
                    card.update_status(
                        status,
                        elapsed_ms=evt.payload.get("elapsed_ms"),
                        error=evt.payload.get("error") or evt.payload.get("reason"),
                    )

            elif evt.type == AgentEventType.TOOL_RESULT:
                tm = evt.payload.get("message")
                if tm is not None:
                    tc_id = getattr(tm, "tool_call_id", "") or ""
                    card = self._tool_cards.get(tc_id)
                    if card:
                        is_error = bool(getattr(tm, "is_error", False) or not getattr(tm, "success", True))
                        status = ToolCallStatus.ERROR.value if is_error else ToolCallStatus.SUCCESS.value
                        meta = getattr(tm, "metadata", {}) or {}
                        card.update_status(
                            status,
                            elapsed_ms=meta.get("elapsed_ms"),
                            error=meta.get("error") if is_error else None,
                            result_text=(tm.content if not is_error else None),
                        )

            elif evt.type == AgentEventType.ERROR:
                err = evt.payload.get("error") or "Unknown error"
                self._append_plain("error", str(err))

            elif evt.type == AgentEventType.STATUS:
                text = evt.payload.get("text") or ""
                self._set_status(text)

            elif evt.type == AgentEventType.FINAL:
                self._set_status("Done")

            self._update_cost_label()
        except Exception:
            traceback.print_exc()

    def _on_vm_pending_approval_ui(self, pending: PendingApproval) -> None:
        try:
            tc_id = pending.request.tool_call.id
            self._approval_to_call[pending.id] = tc_id
            card = self._tool_cards.get(tc_id)
            if card:
                card.bind_approval(pending.id)
                card._permission = pending.request.tool_def.permission.value
                card._category = pending.request.tool_def.category
                card.update_status(ToolCallStatus.PENDING_APPROVAL.value)
        except Exception:
            traceback.print_exc()

    def _on_tool_card_approval(self, approval_id: str, decision: ApprovalDecision) -> None:
        self._vm.resolve_approval(approval_id, decision)

    def _on_running_changed(self, running: bool) -> None:
        try:
            if self._send_button:
                self._send_button.visible = not running
            if self._cancel_button:
                self._cancel_button.visible = running
            self._set_status("Running..." if running else "Ready")
        except Exception:
            pass

    def _on_session_cleared(self) -> None:
        self._rebuild_all_messages()
        self._set_status("Conversation cleared")
        self._update_cost_label()

    def _on_config_changed(self) -> None:
        self._set_status(self._status_text())

    # =========================================================================
    # 交互
    # =========================================================================

    def _send_current_input(self) -> None:
        if self._input_field is None:
            return
        text = self._input_field.model.get_value_as_string()
        if not text.strip():
            return
        self._input_field.model.set_value("")
        self._vm.send_message(text)

    def _cancel_running(self) -> None:
        self._vm.cancel()

    def _clear_conversation(self) -> None:
        self._vm.clear_session()

    def _open_settings(self) -> None:
        if self._settings_dialog is None:
            self._settings_dialog = CopilotSettingsDialog(self._vm)
        self._settings_dialog.show()

    # =========================================================================
    # 状态条
    # =========================================================================

    def _set_status(self, text: str) -> None:
        if self._status_label:
            try:
                self._status_label.text = text
            except Exception:
                pass

    def _status_text(self) -> str:
        if not self._vm.is_configured:
            return "API Key not configured. Click [Settings] to configure."
        return "Ready"

    def _cost_text(self) -> str:
        if not self._vm.show_cost:
            return ""
        sess = self._vm.session
        total = sess.total_prompt_tokens + sess.total_completion_tokens
        return f"{total} tokens | RMB {sess.total_cost_rmb:.4f}"

    def _update_cost_label(self) -> None:
        if self._cost_label:
            try:
                self._cost_label.text = self._cost_text()
            except Exception:
                pass

    def _scroll_to_bottom(self) -> None:
        if self._scroll is None:
            return
        try:
            self._scroll.scroll_y = 1e6
        except Exception:
            pass

    # =========================================================================
    # App update 订阅（drain 事件 + 审批）
    # =========================================================================

    def _subscribe_app_update(self) -> None:
        try:
            import omni.kit.app  # type: ignore
            app = omni.kit.app.get_app()
            stream = app.get_update_event_stream()
            self._update_sub = stream.create_subscription_to_pop(
                self._on_app_update,
                name="omni.anim.drama.toolset.copilot.drain",
            )
        except Exception:
            self._update_sub = None

    def _on_app_update(self, _evt) -> None:
        try:
            self._vm.drain_events()
            self._vm.drain_pending_approvals()
        except Exception:
            traceback.print_exc()

    # =========================================================================
    # 生命周期
    # =========================================================================

    def dispose(self) -> None:
        try:
            self._vm.remove_event_callback(self._on_vm_event_ui)
            self._vm.remove_pending_approval_callback(self._on_vm_pending_approval_ui)
            self._vm.remove_running_changed_callback(self._on_running_changed)
            self._vm.remove_session_cleared_callback(self._on_session_cleared)
            self._vm.remove_config_changed_callback(self._on_config_changed)
        except Exception:
            pass

        if self._update_sub is not None:
            try:
                self._update_sub = None
            except Exception:
                pass

        if self._settings_dialog:
            try:
                self._settings_dialog.destroy()
            except Exception:
                pass
            self._settings_dialog = None

        self._tool_cards.clear()
        self._approval_to_call.clear()
