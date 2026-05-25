# -*- coding: utf-8 -*-
"""
Planning Tools - 计划阶段工具
=============================

提供 ``submit_plan`` 工具，让 Agent 在动手前先把计划"显式化"：

- intent: 用户意图的一句话复述
- steps: 准备执行的有序步骤
- tools_to_use: 预计会调用的工具名（不包括 plan 本身）
- risks: 风险或不确定项
- needs_clarification: 是否需要先向用户确认（若是，应该问什么）

这是一个 **READ_ONLY 工具**：它不修改 stage，只把结构化的计划写回到 Tool 结果里
让 LLM 自己看见，相当于"白板写字"。System prompt 会要求模型在涉及任何修改类
任务时先调用本工具。

为什么这样设计而不是硬性 phase 状态机：

- 模型现在普遍支持 tool use，但对硬切 phase 的 turn-based 强约束不友好
- "调用 submit_plan" 本身就是一种自我承诺机制，比纯文本的 "Let me think..." 更可靠
- 计划被 echo 回 ToolMessage，下一轮 LLM 看到后会按计划走
- 计划 JSON 也可以被 UI 高亮显示给用户做审视
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..tool_registry import tool, ToolPermission


@tool(
    description=(
        "Submit a structured plan BEFORE taking any modifying action. "
        "Call this whenever the user's request involves create/modify/delete operations, "
        "or whenever the task has more than 2 steps. "
        "After this call returns, proceed to call read-only inspection tools to gather "
        "the information your plan needs, then perform the actual mutate calls. "
        "Skip this only for trivial pure-query tasks (e.g. 'what's in the scene')."
    ),
    permission=ToolPermission.READ_ONLY,
    category="meta",
    tags=["plan", "meta"],
    phase_hint="plan",
    parameters_schema={
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "description": "One-sentence restatement of what the user actually wants.",
            },
            "steps": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Ordered concrete steps. Each step should be a single action like "
                    "'list all RectLights to find their current intensity' or "
                    "'modify intensity of /World/Lights/Rect_1 to 500'."
                ),
            },
            "tools_to_use": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tool names you expect to call (excluding submit_plan itself).",
            },
            "risks": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Potential risks / pitfalls / things that could be wrong "
                    "(e.g. 'user said blue light but no light actually has blue color')."
                ),
            },
            "needs_clarification": {
                "type": "boolean",
                "description": (
                    "True if the request is ambiguous and you must ask the user before "
                    "proceeding. If True, do NOT call any mutate tool and instead reply "
                    "with the clarification question."
                ),
                "default": False,
            },
            "clarification_question": {
                "type": "string",
                "description": "If needs_clarification=True, the question to ask the user.",
                "default": "",
            },
        },
        "required": ["intent", "steps"],
    },
)
def submit_plan(
    intent: str,
    steps: List[str],
    tools_to_use: Optional[List[str]] = None,
    risks: Optional[List[str]] = None,
    needs_clarification: bool = False,
    clarification_question: str = "",
) -> Dict[str, Any]:
    """
    Record a structured plan. Returns the same plan back so the LLM has it in context.
    """
    plan: Dict[str, Any] = {
        "ok": True,
        "phase": "planning",
        "intent": (intent or "").strip(),
        "steps": [s for s in (steps or []) if s and s.strip()],
        "tools_to_use": [t for t in (tools_to_use or []) if t and t.strip()],
        "risks": [r for r in (risks or []) if r and r.strip()],
        "needs_clarification": bool(needs_clarification),
        "clarification_question": (clarification_question or "").strip(),
        "next_action_hint": (
            "Now call read-only inspection tools to gather data your steps depend on, "
            "then proceed with mutate tools (each will be shown to the user for approval)."
        ),
    }
    if needs_clarification:
        plan["next_action_hint"] = (
            "needs_clarification=True. Stop calling tools. Reply to the user with the "
            "clarification_question and wait for the user's answer."
        )
    return plan
