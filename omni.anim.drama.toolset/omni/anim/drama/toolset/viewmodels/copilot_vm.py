# -*- coding: utf-8 -*-
"""
Copilot ViewModel
=================

桥接 UI 层与 Agent 层：

- 配置管理（provider / api_key / base_url / model / 行为开关），复用 carb.settings
- Session 维护
- 异步调度 Agent（在 ThreadPoolExecutor 里跑，避免阻塞 Kit 主循环）
- 审批流程（worker 线程请求审批 → UI 线程显示卡片 → 用户点击 → 回写）
- 事件队列（Agent 产生事件放入 queue，UI 主循环每帧 drain）
"""

from __future__ import annotations

import base64
import queue
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .base_viewmodel import BaseViewModel
from ..agent.messages import (
    AIMessage, HumanMessage, Message, SystemMessage, ToolCall, ToolMessage,
)
from ..agent.session import AgentSession
from ..agent.tool_registry import ToolDef, ToolPermission, ToolRegistry
from ..agent.network_node import (
    AgentEvent, AgentEventType, AgentNode, ApprovalCallback, ApprovalDecision,
    ApprovalRequest, ApprovalResult, ToolCallStatus,
)
from ..agent.agents.single_agent import SingleAgent, DEFAULT_SYSTEM_PROMPT
from ..agent.backend.base import (
    BackendConfig, LLMBackend, PROVIDER_PRESETS, apply_preset,
)
from ..agent.backend.openai_compat_backend import OpenAICompatBackend
from ..agent.backend.gemini_backend import GeminiBackend


# =============================================================================
# Settings keys
# =============================================================================

SETTINGS_PREFIX = "/exts/omni.anim.drama.toolset/agent/"

S_PROVIDER = SETTINGS_PREFIX + "provider"
S_BASE_URL = SETTINGS_PREFIX + "base_url"
S_API_KEY = SETTINGS_PREFIX + "api_key"
S_MODEL = SETTINGS_PREFIX + "model"
S_TEMPERATURE = SETTINGS_PREFIX + "temperature"
S_MAX_TOKENS = SETTINGS_PREFIX + "max_tokens"
S_AUTO_RUN_RO = SETTINGS_PREFIX + "auto_run_read_only"
S_AUTO_APPROVE_MUTATE = SETTINGS_PREFIX + "auto_approve_mutate"
S_ALLOW_DESTRUCTIVE = SETTINGS_PREFIX + "allow_destructive"
S_SHOW_COST = SETTINGS_PREFIX + "show_cost"
S_PANEL_WIDTH = SETTINGS_PREFIX + "panel_width"
S_PANEL_VISIBLE = SETTINGS_PREFIX + "panel_visible"
S_MAX_ITERATIONS = SETTINGS_PREFIX + "max_iterations"


DEFAULT_PROVIDER = "siliconflow"
DEFAULT_MAX_ITERATIONS = 30


# =============================================================================
# ApprovalFuture（worker 线程等待 UI 审批）
# =============================================================================

@dataclass
class PendingApproval:
    """等待 UI 处理的一个审批请求。"""
    id: str
    request: ApprovalRequest
    event: threading.Event = field(default_factory=threading.Event)
    result: Optional[ApprovalResult] = None


# =============================================================================
# CopilotViewModel
# =============================================================================

class CopilotViewModel(BaseViewModel):
    """Copilot 侧栏的 ViewModel。"""

    def __init__(self) -> None:
        super().__init__()

        # --- 配置 ---
        self._provider: str = DEFAULT_PROVIDER
        self._base_url: str = ""
        self._api_key: str = ""
        self._model: str = ""
        self._temperature: float = 0.3
        self._max_tokens: int = 4096

        # --- 行为 ---
        self._auto_run_read_only: bool = True
        self._auto_approve_mutate: bool = False
        self._allow_destructive: bool = False
        self._show_cost: bool = True

        # --- UI 状态 ---
        self._panel_width: float = 340.0
        self._panel_visible: bool = True

        # --- 运行时 ---
        self._session: AgentSession = AgentSession()
        self._backend: Optional[LLMBackend] = None
        self._agent: Optional[AgentNode] = None
        self._is_running: bool = False

        # 事件队列（Agent 线程 → UI 主线程）
        self._events: "queue.Queue[AgentEvent]" = queue.Queue()
        # 待处理审批（Agent 线程 → UI 主线程）
        self._pending_approvals: "queue.Queue[PendingApproval]" = queue.Queue()

        # 外部 UI 回调（在 UI 线程调用）
        self._on_event_ui_callbacks: List[Callable[[AgentEvent], None]] = []
        self._on_pending_approval_callbacks: List[Callable[[PendingApproval], None]] = []
        self._on_running_changed_callbacks: List[Callable[[bool], None]] = []
        self._on_config_changed_callbacks: List[Callable[[], None]] = []
        self._on_session_cleared_callbacks: List[Callable[[], None]] = []

        # 线程池
        self._executor = ThreadPoolExecutor(max_workers=2)

        # 加载设置
        self._load_settings()

    # =========================================================================
    # 配置
    # =========================================================================

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def api_key(self) -> str:
        return self._api_key

    @property
    def model(self) -> str:
        return self._model

    @property
    def temperature(self) -> float:
        return self._temperature

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    @property
    def auto_run_read_only(self) -> bool:
        return self._auto_run_read_only

    @property
    def auto_approve_mutate(self) -> bool:
        return self._auto_approve_mutate

    @property
    def allow_destructive(self) -> bool:
        return self._allow_destructive

    @property
    def show_cost(self) -> bool:
        return self._show_cost

    @property
    def panel_width(self) -> float:
        return self._panel_width

    @property
    def panel_visible(self) -> bool:
        return self._panel_visible

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def session(self) -> AgentSession:
        return self._session

    def set_provider(self, provider: str, use_preset: bool = True, save: bool = False) -> None:
        self._provider = provider
        if use_preset and provider in PROVIDER_PRESETS:
            preset = PROVIDER_PRESETS[provider]
            self._base_url = preset.get("base_url", self._base_url)
            if not self._model or self._model in (p.get("model", "") for p in PROVIDER_PRESETS.values()):
                self._model = preset.get("model", self._model)
        self._reset_backend()
        self._notify_config_changed()
        if save:
            self._save_settings()

    def set_base_url(self, value: str, save: bool = False) -> None:
        self._base_url = value
        self._reset_backend()
        self._notify_config_changed()
        if save:
            self._save_settings()

    def set_api_key(self, value: str, save: bool = False) -> None:
        self._api_key = value
        self._reset_backend()
        self._notify_config_changed()
        if save:
            self._save_settings()

    def set_model(self, value: str, save: bool = False) -> None:
        self._model = value
        self._reset_backend()
        self._notify_config_changed()
        if save:
            self._save_settings()

    def set_temperature(self, value: float, save: bool = False) -> None:
        self._temperature = max(0.0, min(2.0, float(value)))
        self._reset_backend()
        if save:
            self._save_settings()

    def set_max_tokens(self, value: int, save: bool = False) -> None:
        self._max_tokens = max(64, int(value))
        self._reset_backend()
        if save:
            self._save_settings()

    def set_auto_run_read_only(self, value: bool, save: bool = False) -> None:
        self._auto_run_read_only = bool(value)
        if self._agent:
            self._agent.set_auto_run_read_only(self._auto_run_read_only)
        if save:
            self._save_settings()

    def set_auto_approve_mutate(self, value: bool, save: bool = False) -> None:
        self._auto_approve_mutate = bool(value)
        if save:
            self._save_settings()

    def set_allow_destructive(self, value: bool, save: bool = False) -> None:
        self._allow_destructive = bool(value)
        if self._agent:
            self._agent.set_allow_destructive(self._allow_destructive)
        if save:
            self._save_settings()

    def set_show_cost(self, value: bool, save: bool = False) -> None:
        self._show_cost = bool(value)
        if save:
            self._save_settings()

    def set_panel_width(self, value: float, save: bool = False) -> None:
        self._panel_width = max(220.0, float(value))
        if save:
            self._save_settings()

    def set_panel_visible(self, value: bool, save: bool = False) -> None:
        self._panel_visible = bool(value)
        if save:
            self._save_settings()

    # =========================================================================
    # Backend / Agent
    # =========================================================================

    def _build_backend(self) -> LLMBackend:
        cfg = BackendConfig(
            provider=self._provider or DEFAULT_PROVIDER,
            base_url=self._base_url,
            api_key=self._api_key,
            model=self._model,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        apply_preset(cfg, cfg.provider)

        if cfg.provider == "gemini":
            return GeminiBackend(cfg)
        return OpenAICompatBackend(cfg)

    def _ensure_backend(self) -> LLMBackend:
        if self._backend is None:
            self._backend = self._build_backend()
        return self._backend

    def _reset_backend(self) -> None:
        """配置变更时重置 backend/agent，下次使用时按最新配置重建。"""
        self._backend = None
        self._agent = None

    def _ensure_agent(self) -> AgentNode:
        if self._agent is None:
            backend = self._ensure_backend()
            self._agent = SingleAgent(
                backend=backend,
                max_iterations=self._read_max_iterations(),
                auto_run_read_only=self._auto_run_read_only,
                allow_destructive=self._allow_destructive,
                approval_callback=self._worker_approval_callback,
                event_callback=self._worker_event_callback,
            )
        return self._agent

    @staticmethod
    def _read_max_iterations() -> int:
        """Resolve agent loop iteration cap from carb settings (fallback to default)."""
        try:
            import carb.settings  # type: ignore

            value = carb.settings.get_settings().get(S_MAX_ITERATIONS)
        except Exception:
            value = None
        try:
            v = int(value) if value not in (None, "") else DEFAULT_MAX_ITERATIONS
        except Exception:
            v = DEFAULT_MAX_ITERATIONS
        # Hard bounds: at least 4 (degenerate), at most 200 (don't burn tokens).
        return max(4, min(v, 200))

    # =========================================================================
    # 连接测试
    # =========================================================================

    def test_connection(self, cb: Callable[[bool, str], None]) -> None:
        """异步测试连接。"""
        if not self.is_configured:
            cb(False, "Please enter API Key first")
            return

        def run() -> None:
            try:
                backend = self._build_backend()
                success, msg = backend.test_connection()
                cb(success, msg)
            except Exception as e:
                cb(False, f"Test failed: {e}")

        self._executor.submit(run)

    # =========================================================================
    # 对话
    # =========================================================================

    def send_message(self, text: str) -> None:
        """发送用户消息，异步跑 Agent。"""
        text = (text or "").strip()
        if not text:
            return

        if self._is_running:
            self.log("Agent is busy, please wait or cancel current task")
            return

        if not self.is_configured:
            self.log("API Key not configured. Open Settings to configure.")
            # 仍然把用户消息加进 session，让 UI 显示，但不跑 LLM
            self._session.add_human(text)
            err_event = AgentEvent(
                type=AgentEventType.ERROR,
                payload={"error": "API Key not configured"},
            )
            self._events.put(err_event)
            return

        # 由 worker 统一把用户消息加入 session（保持顺序）
        self._set_running(True)

        def worker() -> None:
            try:
                agent = self._ensure_agent()
                agent.set_auto_run_read_only(self._auto_run_read_only)
                agent.set_allow_destructive(self._allow_destructive)
                agent.run(self._session, user_input=text)
            except Exception as e:
                err_event = AgentEvent(
                    type=AgentEventType.ERROR,
                    payload={"error": f"Agent error: {e}"},
                )
                self._events.put(err_event)
            finally:
                self._set_running(False)

        self._executor.submit(worker)

    def cancel(self) -> None:
        if self._agent:
            self._agent.cancel()
        # 唤醒所有挂起的 approval，让 worker 退出
        self._drain_and_reject_pending_approvals()

    def clear_session(self) -> None:
        self._session = AgentSession()
        self._drain_and_reject_pending_approvals()
        for cb in list(self._on_session_cleared_callbacks):
            try:
                cb()
            except Exception as e:
                self.log(f"cleared callback error: {e}")

    # =========================================================================
    # 审批（在 UI 主线程调用）
    # =========================================================================

    def resolve_approval(
        self,
        approval_id: str,
        decision: ApprovalDecision,
        arguments: Optional[Dict[str, Any]] = None,
        reason: str = "",
        remove_from_queue: bool = True,
    ) -> None:
        """UI 点击按钮后调用此方法回写决定。"""
        pending = self._find_pending(approval_id, remove=remove_from_queue)
        if not pending:
            self.log(f"[anime agent] Approval not found: {approval_id}")
            return
        pending.result = ApprovalResult(
            decision=decision,
            arguments=arguments,
            reason=reason,
        )
        pending.event.set()

    def _find_pending(self, approval_id: str, remove: bool = True) -> Optional[PendingApproval]:
        """从 pending 队列中找到指定 id（会把无关项重新放回）。"""
        found: Optional[PendingApproval] = None
        buffer: List[PendingApproval] = []
        while True:
            try:
                item = self._pending_approvals.get_nowait()
            except queue.Empty:
                break
            if item.id == approval_id and found is None:
                found = item
                if not remove:
                    buffer.append(item)
            else:
                buffer.append(item)
        # 把未匹配的放回
        for item in buffer:
            self._pending_approvals.put(item)
        return found

    def _drain_and_reject_pending_approvals(self) -> None:
        """把队列中所有挂起的审批都拒掉（用于取消/清空）。"""
        while True:
            try:
                item = self._pending_approvals.get_nowait()
            except queue.Empty:
                break
            item.result = ApprovalResult(decision=ApprovalDecision.REJECT, reason="Cancelled")
            item.event.set()

    # =========================================================================
    # UI 主线程每帧回调：drain 事件队列
    # =========================================================================

    def drain_events(self) -> int:
        """
        在 UI 主线程周期性调用，把 worker 发来的事件派发给 UI 回调。

        Returns:
            int: 本次处理的事件数。
        """
        count = 0
        while True:
            try:
                evt = self._events.get_nowait()
            except queue.Empty:
                break
            count += 1
            for cb in list(self._on_event_ui_callbacks):
                try:
                    cb(evt)
                except Exception as e:
                    self.log(f"ui event cb error: {e}")
        return count

    def drain_pending_approvals(self) -> int:
        """
        在 UI 主线程周期性调用，把 worker 发来的审批请求交给 UI 显示。

        注意：为了让 resolve_approval 之后能再找到它，我们**不**在这里把 pending 出队，
        而是让 UI 标记"已显示"并持有它；真正出队在 resolve_approval 时进行。
        """
        # 由于我们把 pending 的所有权保留在 queue 里，这里只"窥视"当前队列内容
        # 为简化，我们临时整体出队、通知 UI、再全部放回
        count = 0
        buffer: List[PendingApproval] = []
        while True:
            try:
                item = self._pending_approvals.get_nowait()
            except queue.Empty:
                break
            buffer.append(item)

        for item in buffer:
            if not item.event.is_set() and not getattr(item, "_ui_notified", False):
                setattr(item, "_ui_notified", True)
                for cb in list(self._on_pending_approval_callbacks):
                    try:
                        cb(item)
                        count += 1
                    except Exception as e:
                        self.log(f"ui approval cb error: {e}")

        # 未被 resolve 的放回（resolve_approval 的取出路径不在此方法）
        for item in buffer:
            if not item.event.is_set():
                self._pending_approvals.put(item)
        return count

    # =========================================================================
    # Worker 线程回调
    # =========================================================================

    def _worker_event_callback(self, evt: AgentEvent) -> None:
        self._events.put(evt)

    def _worker_approval_callback(self, req: ApprovalRequest) -> ApprovalResult:
        """
        Agent worker 调用此方法请求审批。
        此方法阻塞，直到 UI 主线程调用 ``resolve_approval``。
        """
        # 自动批准 mutate（但 destructive 永远要审批——上层 AgentNode 已经保证了这一点）
        if (
            req.tool_def.permission == ToolPermission.MUTATE
            and self._auto_approve_mutate
        ):
            return ApprovalResult(decision=ApprovalDecision.APPROVE, arguments=None)

        pending = PendingApproval(id=uuid.uuid4().hex[:12], request=req)
        self._pending_approvals.put(pending)

        # 等 UI 响应（最多 5 分钟）
        got = pending.event.wait(timeout=300.0)
        if not got or pending.result is None:
            return ApprovalResult(decision=ApprovalDecision.REJECT, reason="Approval timed out")
        return pending.result

    # =========================================================================
    # 回调注册
    # =========================================================================

    def add_event_callback(self, cb: Callable[[AgentEvent], None]) -> None:
        if cb not in self._on_event_ui_callbacks:
            self._on_event_ui_callbacks.append(cb)

    def remove_event_callback(self, cb: Callable[[AgentEvent], None]) -> None:
        if cb in self._on_event_ui_callbacks:
            self._on_event_ui_callbacks.remove(cb)

    def add_pending_approval_callback(self, cb: Callable[[PendingApproval], None]) -> None:
        if cb not in self._on_pending_approval_callbacks:
            self._on_pending_approval_callbacks.append(cb)

    def remove_pending_approval_callback(self, cb: Callable[[PendingApproval], None]) -> None:
        if cb in self._on_pending_approval_callbacks:
            self._on_pending_approval_callbacks.remove(cb)

    def add_running_changed_callback(self, cb: Callable[[bool], None]) -> None:
        if cb not in self._on_running_changed_callbacks:
            self._on_running_changed_callbacks.append(cb)

    def remove_running_changed_callback(self, cb: Callable[[bool], None]) -> None:
        if cb in self._on_running_changed_callbacks:
            self._on_running_changed_callbacks.remove(cb)

    def add_config_changed_callback(self, cb: Callable[[], None]) -> None:
        if cb not in self._on_config_changed_callbacks:
            self._on_config_changed_callbacks.append(cb)

    def remove_config_changed_callback(self, cb: Callable[[], None]) -> None:
        if cb in self._on_config_changed_callbacks:
            self._on_config_changed_callbacks.remove(cb)

    def add_session_cleared_callback(self, cb: Callable[[], None]) -> None:
        if cb not in self._on_session_cleared_callbacks:
            self._on_session_cleared_callbacks.append(cb)

    def remove_session_cleared_callback(self, cb: Callable[[], None]) -> None:
        if cb in self._on_session_cleared_callbacks:
            self._on_session_cleared_callbacks.remove(cb)

    def _notify_config_changed(self) -> None:
        for cb in list(self._on_config_changed_callbacks):
            try:
                cb()
            except Exception as e:
                self.log(f"config cb error: {e}")

    def _set_running(self, value: bool) -> None:
        if self._is_running == value:
            return
        self._is_running = value
        for cb in list(self._on_running_changed_callbacks):
            try:
                cb(value)
            except Exception as e:
                self.log(f"running cb error: {e}")

    # =========================================================================
    # Settings Persistence
    # =========================================================================

    @staticmethod
    def _encode(s: str) -> str:
        if not s:
            return ""
        try:
            return base64.b64encode(s.encode("utf-8")).decode("utf-8")
        except Exception:
            return ""

    @staticmethod
    def _decode(s: str) -> str:
        if not s:
            return ""
        try:
            return base64.b64decode(s.encode("utf-8")).decode("utf-8")
        except Exception:
            return ""

    @staticmethod
    def _get_settings() -> Any:
        try:
            import carb.settings  # type: ignore
            return carb.settings.get_settings()
        except Exception:
            return None

    def _load_settings(self) -> None:
        s = self._get_settings()
        if s is None:
            # 没有 carb（例如冒烟测试环境），应用 provider 预设
            self.set_provider(DEFAULT_PROVIDER, use_preset=True, save=False)
            return
        try:
            provider = s.get(S_PROVIDER) or DEFAULT_PROVIDER
            self._provider = provider

            base_url = s.get(S_BASE_URL)
            if base_url:
                self._base_url = base_url

            api_key_enc = s.get(S_API_KEY)
            if api_key_enc:
                self._api_key = self._decode(api_key_enc)

            model = s.get(S_MODEL)
            if model:
                self._model = model

            temp = s.get(S_TEMPERATURE)
            if temp is not None:
                try:
                    self._temperature = float(temp)
                except Exception:
                    pass

            mt = s.get(S_MAX_TOKENS)
            if mt is not None:
                try:
                    self._max_tokens = int(mt)
                except Exception:
                    pass

            auto_ro = s.get(S_AUTO_RUN_RO)
            if auto_ro is not None:
                self._auto_run_read_only = bool(auto_ro)

            auto_mu = s.get(S_AUTO_APPROVE_MUTATE)
            if auto_mu is not None:
                self._auto_approve_mutate = bool(auto_mu)

            allow_de = s.get(S_ALLOW_DESTRUCTIVE)
            if allow_de is not None:
                self._allow_destructive = bool(allow_de)

            show_cost = s.get(S_SHOW_COST)
            if show_cost is not None:
                self._show_cost = bool(show_cost)

            pw = s.get(S_PANEL_WIDTH)
            if pw is not None:
                try:
                    self._panel_width = float(pw)
                except Exception:
                    pass

            pv = s.get(S_PANEL_VISIBLE)
            if pv is not None:
                self._panel_visible = bool(pv)

            # 如果 base_url/model 还是空，按 provider 预设填
            if not self._base_url or not self._model:
                preset = PROVIDER_PRESETS.get(self._provider, {})
                if not self._base_url:
                    self._base_url = preset.get("base_url", "")
                if not self._model:
                    self._model = preset.get("model", "")

            self.log("anime agent config loaded")
        except Exception as e:
            self.log(f"Failed to load anime agent config: {e}")

    def save_settings(self) -> None:
        self._save_settings()

    def _save_settings(self) -> None:
        s = self._get_settings()
        if s is None:
            return
        try:
            s.set(S_PROVIDER, self._provider)
            s.set(S_BASE_URL, self._base_url)
            s.set(S_API_KEY, self._encode(self._api_key))
            s.set(S_MODEL, self._model)
            s.set(S_TEMPERATURE, float(self._temperature))
            s.set(S_MAX_TOKENS, int(self._max_tokens))
            s.set(S_AUTO_RUN_RO, bool(self._auto_run_read_only))
            s.set(S_AUTO_APPROVE_MUTATE, bool(self._auto_approve_mutate))
            s.set(S_ALLOW_DESTRUCTIVE, bool(self._allow_destructive))
            s.set(S_SHOW_COST, bool(self._show_cost))
            s.set(S_PANEL_WIDTH, float(self._panel_width))
            s.set(S_PANEL_VISIBLE, bool(self._panel_visible))
            self.log("anime agent config saved")
        except Exception as e:
            self.log(f"Failed to save anime agent config: {e}")

    # =========================================================================
    # 生命周期
    # =========================================================================

    def dispose(self) -> None:
        super().dispose()
        self.cancel()
        try:
            if self._executor:
                self._executor.shutdown(wait=False)
        except Exception:
            pass
        self._on_event_ui_callbacks.clear()
        self._on_pending_approval_callbacks.clear()
        self._on_running_changed_callbacks.clear()
        self._on_config_changed_callbacks.clear()
        self._on_session_cleared_callbacks.clear()
