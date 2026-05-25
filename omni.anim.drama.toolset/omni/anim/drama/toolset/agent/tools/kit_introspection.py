# -*- coding: utf-8 -*-
"""
Kit Command Introspection - omni.kit.commands 自省 / 受控执行
==============================================================

让 Agent 在没有现成高层工具时，能直接发现并调用 Omniverse Kit 中已注册的命令。

工具：
- list_kit_commands:    列出 / 搜索已注册命令
- get_kit_command_doc:  获取某命令的 docstring + 参数（来自 inspect 与官方 API）
- execute_kit_command:  受控执行某命令（MUTATE，需要审批）

为什么有这个：
``omni.kit.commands`` 是 Omniverse 中"撤销安全"的官方修改入口。它本身就提供
``get_commands_list`` / ``get_command_doc`` / ``get_command_parameters`` 等内省 API，
非常适合给 Agent 当 fallback：当我们没写过对应的高层工具时，Agent 可以列命令、
看 doc，然后再调用 ``execute_kit_command`` 完成任务，并且全程会进入 undo 栈。

安全：
- ``execute_kit_command`` 设为 ``MUTATE``，必须经过审批；
- 我们维护一份 ``KIT_COMMAND_DENYLIST``，对明显危险的命令（删 layer / 写文件等）默认拒绝；
- 参数通过 ``inspect`` 校验，未知参数会被拒绝（防 typo / 防越权）。

注：``omni.kit.commands`` 在 Kit 进程内一定可用；模块外部测试时会优雅降级。
"""

from __future__ import annotations

import inspect
import re
from typing import Any, Dict, List, Optional

from ..tool_registry import tool, ToolPermission


# =============================================================================
# 危险命令黑名单（默认拒绝执行）
# =============================================================================

# 关键字匹配（小写）：命中即拒绝
KIT_COMMAND_DENYLIST_KEYWORDS = {
    "saveas", "save_as",
    "removelayer", "remove_layer",
    "deletefile", "delete_file",
    "shutdown", "exit",
    "createnewstage", "create_new_stage",
}

# 显式允许：即使关键字命中，这里也放行（暂留空）
KIT_COMMAND_ALLOWLIST: set = set()


def _is_denied(command_name: str) -> bool:
    if command_name in KIT_COMMAND_ALLOWLIST:
        return False
    lower = command_name.lower()
    return any(k in lower for k in KIT_COMMAND_DENYLIST_KEYWORDS)


# =============================================================================
# 内部：拿 omni.kit.commands 模块（懒加载，单元测试外可降级）
# =============================================================================

def _get_commands_module():
    try:
        import omni.kit.commands as kc
        return kc
    except Exception as e:  # pragma: no cover
        return None


def _safe_split_command(command_name: str) -> str:
    """
    omni.kit.commands 注册的命令通常是单一名字（无 module 前缀），
    用户可能传 'omni.kit.commands.MyCommand'，我们只取最后一段。
    """
    if not command_name:
        return ""
    return command_name.strip().split(".")[-1]


# =============================================================================
# list_kit_commands
# =============================================================================

@tool(
    description=(
        "List Omniverse Kit commands registered in the current process. Optionally "
        "filter by case-insensitive substring (`query`) and/or by command-module "
        "extension (`extension`). Use this as a fallback when no high-level tool "
        "covers your need: discover the underlying Kit command, inspect its doc "
        "with get_kit_command_doc, then execute it with execute_kit_command "
        "(which is MUTATE and requires approval)."
    ),
    permission=ToolPermission.READ_ONLY,
    category="introspection",
    tags=["kit", "command", "meta"],
    phase_hint="gather",
)
def list_kit_commands(
    query: str = "",
    extension: str = "",
    limit: int = 100,
) -> Dict[str, Any]:
    """
    List Kit commands.

    Args:
        query: Case-insensitive substring on the command NAME.
        extension: Filter by extension/module name (e.g. 'omni.kit.commands').
        limit: Max number of commands to return (default 100, hard cap 500).
    """
    kc = _get_commands_module()
    if kc is None:
        return {"error": "omni.kit.commands is not available in this process."}

    cap = max(1, min(int(limit), 500))

    try:
        all_cmds = kc.get_commands_list()
    except Exception as e:
        return {"error": f"get_commands_list failed: {e}"}

    needle = (query or "").lower().strip()
    ext_needle = (extension or "").lower().strip()

    out: List[Dict[str, Any]] = []
    for cmd_cls in all_cmds:
        try:
            name = getattr(cmd_cls, "__name__", str(cmd_cls))
            module = getattr(cmd_cls, "__module__", "")
        except Exception:
            continue

        if needle and needle not in name.lower():
            continue
        if ext_needle and ext_needle not in (module or "").lower():
            continue

        doc = (getattr(cmd_cls, "__doc__", "") or "").strip().splitlines()
        first_line = doc[0].strip() if doc else ""

        out.append({
            "name": name,
            "module": module,
            "summary": first_line[:200],
            "denied_by_default": _is_denied(name),
        })
        if len(out) >= cap:
            break

    return {
        "query": query,
        "extension": extension,
        "count": len(out),
        "truncated": len(out) >= cap,
        "commands": out,
    }


# =============================================================================
# get_kit_command_doc
# =============================================================================

_PARAM_RE = re.compile(r"\bself\b|\*\*?\w+")


def _summarize_command_signature(cmd_cls) -> Dict[str, Any]:
    """
    通过 inspect 抓取命令 ``__init__`` / ``do`` 的签名做参数说明。
    """
    out: Dict[str, Any] = {"params": [], "doc": (cmd_cls.__doc__ or "").strip()}
    for attr_name in ("__init__", "do"):
        fn = getattr(cmd_cls, attr_name, None)
        if not fn:
            continue
        try:
            sig = inspect.signature(fn)
        except (ValueError, TypeError):
            continue
        params = []
        for pname, p in sig.parameters.items():
            if pname in ("self", "cls"):
                continue
            if p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            entry = {
                "name": pname,
                "kind": str(p.kind),
                "has_default": p.default is not inspect.Parameter.empty,
            }
            if p.annotation is not inspect.Parameter.empty:
                entry["annotation"] = str(p.annotation)
            if p.default is not inspect.Parameter.empty:
                try:
                    entry["default"] = repr(p.default)
                except Exception:
                    entry["default"] = "<unrepr>"
            params.append(entry)
        if params:
            out["params"] = params
            out["from"] = attr_name
            break
    return out


@tool(
    description=(
        "Return docstring and parameter signature for a single Kit command. "
        "Call this after list_kit_commands has identified a candidate, BEFORE "
        "calling execute_kit_command, so you know exactly which arguments to pass."
    ),
    permission=ToolPermission.READ_ONLY,
    category="introspection",
    tags=["kit", "command", "meta"],
    phase_hint="gather",
)
def get_kit_command_doc(command_name: str) -> Dict[str, Any]:
    """
    Get doc + parameter signature for a Kit command.

    Args:
        command_name: Command class name (e.g. 'CreatePrimCommand', 'MovePrim').
    """
    kc = _get_commands_module()
    if kc is None:
        return {"error": "omni.kit.commands is not available in this process."}

    name = _safe_split_command(command_name)
    if not name:
        return {"error": "command_name must be non-empty."}

    try:
        all_cmds = kc.get_commands_list()
    except Exception as e:
        return {"error": f"get_commands_list failed: {e}"}

    candidate = None
    for cmd_cls in all_cmds:
        if getattr(cmd_cls, "__name__", "") == name:
            candidate = cmd_cls
            break
    if candidate is None:
        return {"error": f"Command not found: {name}"}

    info: Dict[str, Any] = {
        "name": name,
        "module": getattr(candidate, "__module__", ""),
        "denied_by_default": _is_denied(name),
    }
    info.update(_summarize_command_signature(candidate))

    # 官方 API: get_command_doc / get_command_parameters（如果可用）
    for api in ("get_command_doc", "get_command_parameters"):
        fn = getattr(kc, api, None)
        if not callable(fn):
            continue
        try:
            info[api] = fn(name)
        except Exception:
            pass

    return info


# =============================================================================
# execute_kit_command
# =============================================================================

@tool(
    description=(
        "Execute an Omniverse Kit command by name with the given keyword arguments. "
        "This is the LAST RESORT: prefer high-level tools (modify_light, "
        "create_light, etc.) when they exist. Use this when no domain tool fits and "
        "you have already inspected the command via get_kit_command_doc. "
        "All Kit commands are undo-safe and pushed onto the global undo stack. "
        "DESTRUCTIVE-style commands (save-as, delete-layer, shutdown, ...) are "
        "denied by default and cannot be executed even with approval."
    ),
    permission=ToolPermission.MUTATE,
    category="introspection",
    tags=["kit", "command", "execute"],
    phase_hint="act",
    verify_with=["inspect_prim", "get_stage_metadata"],
    parameters_schema={
        "type": "object",
        "properties": {
            "command_name": {
                "type": "string",
                "description": "Kit command name, e.g. 'CreatePrimCommand', 'MovePrim'.",
            },
            "kwargs": {
                "type": "object",
                "description": (
                    "Keyword arguments dict to pass to the command. Must match the "
                    "parameter names returned by get_kit_command_doc."
                ),
            },
        },
        "required": ["command_name"],
    },
)
def execute_kit_command(
    command_name: str,
    kwargs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Execute a Kit command by name. Args:
        command_name: Kit command class name.
        kwargs: Keyword arguments matching the command's signature.
    """
    kc = _get_commands_module()
    if kc is None:
        return {"ok": False, "error": "omni.kit.commands is not available."}

    name = _safe_split_command(command_name)
    if not name:
        return {"ok": False, "error": "command_name must be non-empty."}

    if _is_denied(name):
        return {
            "ok": False,
            "error": f"Command '{name}' is in the default denylist and cannot be executed.",
            "hint": (
                "If you genuinely need this, ask the user to add the name to "
                "KIT_COMMAND_ALLOWLIST in kit_introspection.py."
            ),
        }

    # 校验：确认命令真的存在 + 参数名合法
    try:
        all_cmds = kc.get_commands_list()
    except Exception as e:
        return {"ok": False, "error": f"get_commands_list failed: {e}"}

    candidate = None
    for cmd_cls in all_cmds:
        if getattr(cmd_cls, "__name__", "") == name:
            candidate = cmd_cls
            break
    if candidate is None:
        return {"ok": False, "error": f"Command not found: {name}"}

    raw_args = dict(kwargs or {})

    # 比对参数白名单（从 __init__ / do 签名取）
    sig_info = _summarize_command_signature(candidate)
    valid_params = {p["name"] for p in sig_info.get("params", [])}
    if valid_params:
        unknown = [k for k in raw_args if k not in valid_params]
        if unknown:
            return {
                "ok": False,
                "error": (
                    f"Unknown kwargs for command '{name}': {unknown}. "
                    f"Valid params: {sorted(valid_params)}."
                ),
            }

    try:
        result = kc.execute(name, **raw_args)
    except Exception as e:
        return {"ok": False, "error": f"execute failed: {e}", "command": name, "kwargs": raw_args}

    # omni.kit.commands.execute 通常返回 (success, ret) 或 ret
    success = True
    ret_val: Any = result
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], bool):
        success, ret_val = result

    out: Dict[str, Any] = {
        "ok": bool(success),
        "command": name,
        "kwargs": raw_args,
    }
    try:
        out["result"] = repr(ret_val) if ret_val is not None else None
    except Exception:
        out["result"] = "<unrepr>"
    return out
