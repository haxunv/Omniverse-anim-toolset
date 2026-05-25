# -*- coding: utf-8 -*-
"""
AgentNode - Agent 基类
======================

提供 Agent 的消息循环抽象：

1. 调用 LLM（携带 messages + tools）
2. 解析 AIMessage：
   - 无 tool_calls：直接结束
   - 有 tool_calls：针对每个 ToolCall
       * 若 READ_ONLY 且 auto_run_read_only=True：直接执行
       * 若 MUTATE：请求审批（交给 UI 层决定）
       * 若 DESTRUCTIVE：默认拒绝（除非当前 Session 已解锁）
       * 执行后写回 ToolMessage
3. 再次调用 LLM 直到 finish_reason == stop 或达到 max_iterations

审批逻辑：通过回调 ``on_request_approval(call, tool_def, ctx) -> ApprovalDecision`` 由 UI 决定。

事件通知：通过回调 ``on_event(event)`` 推送状态更新到 UI（增量更新消息列表）。
"""

from __future__ import annotations

import enum
import json
import os
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .messages import (
    AIMessage, HumanMessage, Message, SystemMessage, ToolCall, ToolMessage, make_tool_call_id,
)
from .session import AgentSession
from .tool_registry import ToolDef, ToolPermission, ToolRegistry
from .backend.base import LLMBackend

try:
    from ..core.stage_utils import safe_log
except Exception:  # pragma: no cover
    def safe_log(msg: str, prefix: str = "AgentNode") -> None:
        print(f"[{prefix}] {msg}")


# =============================================================================
# 审批决策
# =============================================================================

class ApprovalDecision(str, enum.Enum):
    """审批结果。"""
    APPROVE = "approve"
    REJECT = "reject"
    APPROVE_ALL_REMAINING = "approve_all_remaining"


@dataclass
class ApprovalRequest:
    """传给审批回调的上下文。"""
    tool_call: ToolCall
    tool_def: ToolDef
    session: AgentSession
    arguments: Dict[str, Any]  # 副本，UI 可修改后返回


@dataclass
class ApprovalResult:
    decision: ApprovalDecision
    arguments: Optional[Dict[str, Any]] = None  # 用户可能改过
    reason: str = ""


ApprovalCallback = Callable[[ApprovalRequest], ApprovalResult]


# =============================================================================
# Agent 阶段（plan / gather / act / verify / summarize）
# =============================================================================

class AgentPhase(str, enum.Enum):
    """
    Agent 推理阶段（软约束，仅作 UI 标注 + system prompt 引导）：

    - PLANNING:     调用 ``submit_plan`` 提交结构化计划
    - GATHERING:    调用 READ_ONLY 类工具收集场景 / 文档信息
    - ACTING:       调用 MUTATE / DESTRUCTIVE 工具执行修改
    - VERIFYING:    每次 mutate 后调用 verify_with 列出的工具读回校验
    - SUMMARIZING:  给最终自然语言总结，无工具调用

    AgentNode 不会硬性拦截；而是通过 phase_hint 上报 + system prompt 引导。
    """
    PLANNING = "planning"
    GATHERING = "gathering"
    ACTING = "acting"
    VERIFYING = "verifying"
    SUMMARIZING = "summarizing"


# =============================================================================
# Agent 事件（推给 UI）
# =============================================================================

class AgentEventType(str, enum.Enum):
    AI_MESSAGE = "ai_message"               # AI 输出（可能带 tool_calls）
    TOOL_CALL_STARTED = "tool_call_started"  # 某个 ToolCall 开始审批 / 执行
    TOOL_CALL_UPDATED = "tool_call_updated"  # 工具调用状态变化
    TOOL_RESULT = "tool_result"              # 工具执行完
    PHASE_CHANGED = "phase_changed"          # 当前 phase 变化（仅 UI 显示）
    FINAL = "final"                          # 本次 run 结束
    ERROR = "error"                          # 出错
    STATUS = "status"                        # 状态文案（"thinking"）


@dataclass
class AgentEvent:
    type: AgentEventType
    payload: Dict[str, Any] = field(default_factory=dict)


AgentEventCallback = Callable[[AgentEvent], None]


# =============================================================================
# ToolCall 执行状态（给 UI 卡片用）
# =============================================================================

class ToolCallStatus(str, enum.Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    BLOCKED = "blocked"      # 权限不足（destructive 未解锁）


# =============================================================================
# AgentNode
# =============================================================================

@dataclass
class AgentRunResult:
    final_message: Optional[AIMessage]
    iterations: int
    success: bool
    error: str = ""


class AgentNode:
    """
    Agent 基类（Phase 1：单 Agent，默认使用 ToolRegistry 里的全部工具）。

    后续 Phase 2 的 SupervisorAgent / LightingAgent 等可继承此类并覆盖 ``allowed_tools``。
    """

    def __init__(
        self,
        backend: LLMBackend,
        *,
        system_prompt: str = "",
        max_iterations: int = 30,
        auto_run_read_only: bool = True,
        allow_destructive: bool = False,
        allowed_tools: Optional[List[str]] = None,
        approval_callback: Optional[ApprovalCallback] = None,
        event_callback: Optional[AgentEventCallback] = None,
    ) -> None:
        self._backend = backend
        self._system_prompt = system_prompt
        self._max_iterations = max_iterations
        self._auto_run_read_only = auto_run_read_only
        self._allow_destructive = allow_destructive
        self._allowed_tools = allowed_tools
        self._approval_callback = approval_callback
        self._event_callback = event_callback
        self._cancelled = False

    # ---------- 配置 ----------

    @property
    def backend(self) -> LLMBackend:
        return self._backend

    def set_backend(self, backend: LLMBackend) -> None:
        self._backend = backend

    def set_approval_callback(self, cb: Optional[ApprovalCallback]) -> None:
        self._approval_callback = cb

    def set_event_callback(self, cb: Optional[AgentEventCallback]) -> None:
        self._event_callback = cb

    def set_auto_run_read_only(self, value: bool) -> None:
        self._auto_run_read_only = value

    def set_allow_destructive(self, value: bool) -> None:
        self._allow_destructive = value

    def set_allowed_tools(self, names: Optional[List[str]]) -> None:
        self._allowed_tools = names

    def set_system_prompt(self, prompt: str) -> None:
        self._system_prompt = prompt

    def cancel(self) -> None:
        self._cancelled = True

    def reset_cancel(self) -> None:
        self._cancelled = False

    # ---------- 工具获取 ----------

    def _get_tools_for_llm(self) -> List[ToolDef]:
        registry = ToolRegistry.instance()
        all_tools = registry.all_tools()
        if self._allowed_tools is None:
            return all_tools
        return [t for t in all_tools if t.name in self._allowed_tools]

    # ---------- 主循环 ----------

    def run(self, session: AgentSession, user_input: Optional[str] = None) -> AgentRunResult:
        """
        跑一次对话：如果提供 ``user_input`` 则先追加一条 HumanMessage，然后进入循环。
        """
        self.reset_cancel()

        # 确保 system prompt 在 session 开头存在
        if self._system_prompt and not any(isinstance(m, SystemMessage) for m in session.messages):
            session.add_system(self._system_prompt)

        if user_input is not None and user_input.strip():
            session.add_human(user_input)

        tools = self._get_tools_for_llm()

        final_ai: Optional[AIMessage] = None
        iteration = 0
        try:
            while iteration < self._max_iterations:
                if self._cancelled:
                    self._emit(AgentEventType.ERROR, {"error": "Cancelled"})
                    return AgentRunResult(final_message=final_ai, iterations=iteration, success=False, error="Cancelled")

                iteration += 1
                self._emit(AgentEventType.STATUS, {"text": f"Thinking (iteration {iteration})..."})

                # 调 LLM
                try:
                    ai_msg = self._backend.chat(session.messages_for_llm(), tools=tools)
                except Exception as e:
                    err = f"LLM call failed: {e}"
                    safe_log(err)
                    self._emit(AgentEventType.ERROR, {"error": err})
                    return AgentRunResult(final_message=final_ai, iterations=iteration, success=False, error=err)

                # 估算费用
                cost = self._backend.estimate_cost_rmb(ai_msg.usage)
                ai_msg.metadata["cost_rmb"] = cost
                ai_msg.metadata["backend"] = self._backend.config.provider
                ai_msg.metadata["model"] = self._backend.config.model

                # 写入 session
                session.add_message(ai_msg)
                session.accumulate_usage(ai_msg.usage, cost)
                final_ai = ai_msg

                self._emit(AgentEventType.AI_MESSAGE, {"message": ai_msg})

                # 没有 tool_calls：结束
                if not ai_msg.has_tool_calls:
                    self._emit(AgentEventType.FINAL, {"message": ai_msg})
                    return AgentRunResult(final_message=ai_msg, iterations=iteration, success=True)

                # 有 tool_calls：依次执行
                approve_all = False
                for call in ai_msg.tool_calls:
                    if self._cancelled:
                        self._emit(AgentEventType.ERROR, {"error": "Cancelled"})
                        return AgentRunResult(final_message=final_ai, iterations=iteration, success=False, error="Cancelled")

                    result_msg = self._execute_single_tool_call(
                        session=session,
                        call=call,
                        approve_all_flag_ref=[approve_all],
                    )

                    # 更新 approve_all flag（从执行函数里带回来）
                    approve_all = result_msg.metadata.get("_approve_all", approve_all)

                    session.add_message(result_msg)
                    self._emit(AgentEventType.TOOL_RESULT, {"message": result_msg})

                # 继续下一轮让 LLM 看到工具结果
                continue

            # 达到最大迭代
            err = f"Max iterations reached ({self._max_iterations})"
            self._emit(AgentEventType.ERROR, {"error": err})
            return AgentRunResult(final_message=final_ai, iterations=iteration, success=False, error=err)

        except Exception as e:
            err = f"Agent loop error: {e}\n{traceback.format_exc()}"
            safe_log(err)
            self._emit(AgentEventType.ERROR, {"error": str(e)})
            return AgentRunResult(final_message=final_ai, iterations=iteration, success=False, error=str(e))

    # ---------- 单个工具调用 ----------

    def _execute_single_tool_call(
        self,
        session: AgentSession,
        call: ToolCall,
        approve_all_flag_ref: List[bool],
    ) -> ToolMessage:
        """
        处理一个 ToolCall：审批 + 执行 + 打包成 ToolMessage。
        """
        registry = ToolRegistry.instance()
        tool_def = registry.get(call.name)

        if not tool_def:
            msg = f"Tool not found: {call.name}"
            safe_log(msg)
            return ToolMessage(
                tool_call_id=call.id or make_tool_call_id(),
                name=call.name,
                content=json.dumps({"error": msg}, ensure_ascii=False),
                success=False,
                is_error=True,
                arguments=dict(call.arguments),
                metadata={"status": ToolCallStatus.ERROR.value, "error": msg},
            )

        # 权限判定 & 审批
        status = ToolCallStatus.PENDING_APPROVAL
        arguments = dict(call.arguments or {})

        if tool_def.permission == ToolPermission.DESTRUCTIVE and not self._allow_destructive:
            blocked = "Destructive tools are disabled. Enable them in Settings to allow."
            self._emit(
                AgentEventType.TOOL_CALL_UPDATED,
                {"tool_call_id": call.id, "status": ToolCallStatus.BLOCKED.value, "reason": blocked},
            )
            return ToolMessage(
                tool_call_id=call.id or make_tool_call_id(),
                name=call.name,
                content=json.dumps({"error": blocked}, ensure_ascii=False),
                success=False,
                is_error=True,
                arguments=arguments,
                metadata={"status": ToolCallStatus.BLOCKED.value, "error": blocked},
            )

        need_approval = tool_def.permission != ToolPermission.READ_ONLY or not self._auto_run_read_only
        if tool_def.permission == ToolPermission.READ_ONLY and self._auto_run_read_only:
            need_approval = False

        # 如果上一次已经 approve all，跳过审批
        if approve_all_flag_ref[0]:
            need_approval = False

        self._emit(
            AgentEventType.TOOL_CALL_STARTED,
            {
                "tool_call_id": call.id,
                "name": call.name,
                "category": tool_def.category,
                "permission": tool_def.permission.value,
                "arguments": dict(arguments),
                "status": ToolCallStatus.PENDING_APPROVAL.value if need_approval else ToolCallStatus.RUNNING.value,
            },
        )

        if need_approval:
            if not self._approval_callback:
                # 没设审批回调 → 按规则拒绝 mutate/destructive
                return ToolMessage(
                    tool_call_id=call.id or make_tool_call_id(),
                    name=call.name,
                    content=json.dumps({"error": "No approval callback configured; rejected"}, ensure_ascii=False),
                    success=False,
                    is_error=True,
                    arguments=arguments,
                    metadata={"status": ToolCallStatus.REJECTED.value, "error": "no approval callback"},
                )

            try:
                result = self._approval_callback(
                    ApprovalRequest(
                        tool_call=call,
                        tool_def=tool_def,
                        session=session,
                        arguments=dict(arguments),
                    )
                )
            except Exception as e:
                err = f"Approval callback error: {e}"
                safe_log(err)
                return ToolMessage(
                    tool_call_id=call.id or make_tool_call_id(),
                    name=call.name,
                    content=json.dumps({"error": err}, ensure_ascii=False),
                    success=False,
                    is_error=True,
                    arguments=arguments,
                    metadata={"status": ToolCallStatus.ERROR.value, "error": err},
                )

            if result.arguments is not None:
                arguments = dict(result.arguments)

            if result.decision == ApprovalDecision.REJECT:
                self._emit(
                    AgentEventType.TOOL_CALL_UPDATED,
                    {"tool_call_id": call.id, "status": ToolCallStatus.REJECTED.value, "reason": result.reason},
                )
                return ToolMessage(
                    tool_call_id=call.id or make_tool_call_id(),
                    name=call.name,
                    content=json.dumps(
                        {"error": "Rejected by user", "reason": result.reason}, ensure_ascii=False
                    ),
                    success=False,
                    is_error=True,
                    arguments=arguments,
                    metadata={"status": ToolCallStatus.REJECTED.value},
                )

            if result.decision == ApprovalDecision.APPROVE_ALL_REMAINING:
                approve_all_flag_ref[0] = True

        # 执行
        self._emit(
            AgentEventType.TOOL_CALL_UPDATED,
            {"tool_call_id": call.id, "status": ToolCallStatus.RUNNING.value},
        )

        start = time.time()
        try:
            ret = tool_def.fn(**arguments)
            elapsed_ms = int((time.time() - start) * 1000)
            content = _stringify_tool_result(ret)
            tool_success = _tool_return_success(ret)
            tool_error = "" if tool_success else _tool_return_error(ret)

            # 对 MUTATE / DESTRUCTIVE 工具，若声明了 verify_with，则在 ToolMessage
            # 末尾追加一条 hint，引导 LLM 在完成本轮 act 后调用验证工具。
            if (
                tool_success
                and
                tool_def.permission != ToolPermission.READ_ONLY
                and tool_def.verify_with
            ):
                hint = self._build_verify_hint(tool_def, arguments)
                if hint:
                    content = _append_verify_hint(content, hint)

            tm = ToolMessage(
                tool_call_id=call.id or make_tool_call_id(),
                name=call.name,
                content=content,
                success=tool_success,
                is_error=not tool_success,
                arguments=arguments,
                metadata={
                    "status": ToolCallStatus.SUCCESS.value if tool_success else ToolCallStatus.ERROR.value,
                    "elapsed_ms": elapsed_ms,
                    "_approve_all": approve_all_flag_ref[0],
                    "verify_with": list(tool_def.verify_with),
                    **({"error": tool_error} if tool_error else {}),
                },
            )
            self._emit(
                AgentEventType.TOOL_CALL_UPDATED,
                {
                    "tool_call_id": call.id,
                    "status": ToolCallStatus.SUCCESS.value if tool_success else ToolCallStatus.ERROR.value,
                    "elapsed_ms": elapsed_ms,
                    **({"error": tool_error} if tool_error else {}),
                },
            )
            return tm

        except TypeError as e:
            # 参数不匹配
            elapsed_ms = int((time.time() - start) * 1000)
            err = f"Argument error: {e}"
            safe_log(err)
            self._emit(
                AgentEventType.TOOL_CALL_UPDATED,
                {"tool_call_id": call.id, "status": ToolCallStatus.ERROR.value, "error": err},
            )
            return ToolMessage(
                tool_call_id=call.id or make_tool_call_id(),
                name=call.name,
                content=json.dumps({"error": err}, ensure_ascii=False),
                success=False,
                is_error=True,
                arguments=arguments,
                metadata={
                    "status": ToolCallStatus.ERROR.value,
                    "elapsed_ms": elapsed_ms,
                    "_approve_all": approve_all_flag_ref[0],
                },
            )
        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            err = f"Execution error: {e}"
            safe_log(err + "\n" + traceback.format_exc())
            self._emit(
                AgentEventType.TOOL_CALL_UPDATED,
                {"tool_call_id": call.id, "status": ToolCallStatus.ERROR.value, "error": err},
            )
            return ToolMessage(
                tool_call_id=call.id or make_tool_call_id(),
                name=call.name,
                content=json.dumps({"error": err}, ensure_ascii=False),
                success=False,
                is_error=True,
                arguments=arguments,
                metadata={
                    "status": ToolCallStatus.ERROR.value,
                    "elapsed_ms": elapsed_ms,
                    "_approve_all": approve_all_flag_ref[0],
                },
            )

    # ---------- 辅助 ----------

    def _emit(self, etype: AgentEventType, payload: Dict[str, Any]) -> None:
        if self._event_callback:
            try:
                self._event_callback(AgentEvent(type=etype, payload=payload))
            except Exception as e:
                safe_log(f"event callback error: {e}")

    def _build_verify_hint(self, tool_def: ToolDef, arguments: Dict[str, Any]) -> str:
        """
        基于 ToolDef.verify_with 构造一段 hint，告诉 LLM 应该用哪些工具去验证。

        会尽量从 arguments 推断关键参数（例如 light_path / prim_path）作为提示。
        """
        if not tool_def.verify_with:
            return ""

        key_path = (
            arguments.get("light_path")
            or arguments.get("prim_path")
            or arguments.get("path")
            or arguments.get("camera_path")
        )

        names = ", ".join(tool_def.verify_with)
        if key_path:
            return (
                f"VERIFY_HINT: After this MUTATE succeeded, call one of [{names}] "
                f"on path {key_path!r} to read the value back and confirm the change "
                f"actually took effect before reporting success to the user."
            )
        return (
            f"VERIFY_HINT: After this MUTATE succeeded, call one of [{names}] "
            f"to read state back and confirm the change before reporting success."
        )


# =============================================================================
# 工具返回值 → 字符串 / 压缩
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


def _truncate_text(text: str, max_chars: int, *, label: str = "tool result") -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    keep_head = max(0, int(max_chars * 0.65))
    keep_tail = max(0, max_chars - keep_head - 400)
    payload = {
        "__truncated__": True,
        "kind": label,
        "original_chars": len(text),
        "kept_chars": max_chars,
        "head": text[:keep_head],
        "tail": text[-keep_tail:] if keep_tail else "",
        "note": (
            "The full tool result was too large for the LLM context and was truncated. "
            "Call a narrower inspection/search tool if exact omitted fields are needed."
        ),
    }
    return json.dumps(payload, ensure_ascii=False)


def _compact_value(value: Any, *, depth: int = 0) -> Any:
    max_depth = _get_context_int("max_json_depth", 6, 1, 20)
    max_string = _get_context_int("max_string_chars", 2000, 200, 20000)
    max_list = _get_context_int("max_list_items", 20, 1, 200)
    max_dict = _get_context_int("max_dict_items", 80, 5, 500)

    if depth >= max_depth:
        return {
            "__truncated__": True,
            "reason": "max_json_depth",
            "type": type(value).__name__,
        }

    if isinstance(value, str):
        if len(value) <= max_string:
            return value
        return {
            "__truncated_string__": True,
            "original_chars": len(value),
            "head": value[: int(max_string * 0.75)],
            "tail": value[-int(max_string * 0.25):],
        }

    if isinstance(value, (int, float, bool)) or value is None:
        return value

    if isinstance(value, (list, tuple)):
        compacted = [_compact_value(v, depth=depth + 1) for v in list(value)[:max_list]]
        if len(value) > max_list:
            compacted.append(
                {
                    "__truncated_list__": True,
                    "original_len": len(value),
                    "kept_len": max_list,
                }
            )
        return compacted

    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        items = list(value.items())
        for key, item in items[:max_dict]:
            out[str(key)] = _compact_value(item, depth=depth + 1)
        if len(items) > max_dict:
            out["__truncated_dict__"] = {
                "original_len": len(items),
                "kept_len": max_dict,
            }
        return out

    return str(value)


def _tool_return_success(ret: Any) -> bool:
    if isinstance(ret, dict):
        if ret.get("ok") is False:
            return False
        if ret.get("success") is False:
            return False
    return True


def _tool_return_error(ret: Any) -> str:
    if not isinstance(ret, dict):
        return "Tool returned failure"
    for key in ("error", "message", "reason"):
        value = ret.get(key)
        if value:
            return str(value)[:500]
    return "Tool returned ok=false or success=false"


def _stringify_tool_result(ret: Any) -> str:
    """把工具返回值转成给 LLM 看的字符串（尽量 JSON）。"""
    max_chars = _get_context_int("max_tool_result_chars", 12000, 1000, 200000)
    if ret is None:
        return json.dumps({"ok": True}, ensure_ascii=False)
    if isinstance(ret, str):
        return _truncate_text(ret, max_chars, label="tool result text")
    try:
        compacted = _compact_value(ret)
        content = json.dumps(compacted, ensure_ascii=False, default=str)
    except Exception:
        content = str(ret)
    return _truncate_text(content, max_chars, label="tool result JSON")


def _append_verify_hint(content: str, hint: str) -> str:
    """
    把 verify hint 追加到工具结果末尾。

    尽量保持 JSON 结构有效：如果 content 是 JSON 对象，则向其加 ``__verify_hint__``
    字段；否则在文本末尾以 ``\\n\\n[VERIFY] ...`` 形式追加。
    """
    if not hint:
        return content
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            parsed["__verify_hint__"] = hint
            return json.dumps(parsed, ensure_ascii=False, default=str)
    except Exception:
        pass
    return f"{content}\n\n[{hint}]"
