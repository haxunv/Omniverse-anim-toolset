# -*- coding: utf-8 -*-
"""
MCP → ToolRegistry Bridge
==========================

把外部 MCP server 暴露的工具，**注册成本扩展的标准 ToolDef**，让 LLM 看到时
和我们自己写的工具一视同仁。

设计要点：

1. **名字隔离**：注册到 ``ToolRegistry`` 时统一加前缀（默认 ``kit_mcp__``），
   避免和本地工具撞名；同时记录原始名字，调用时还原。
2. **权限策略**：MCP 协议没有 ``read_only / mutate / destructive`` 概念，
   我们对每台 MCP server 整体设定一个默认权限（默认 ``READ_ONLY``）。
   理由：Kit MCP / USD Code MCP / OmniUI MCP 三台官方 server 都是
   "查文档 / 查代码示例" 类工具，纯只读。
3. **schema 透传**：MCP 工具的 ``inputSchema`` 是 JSON Schema，直接塞进
   ``ToolDef.parameters_schema``。我们的 ``LLMBackend`` 已经把 ToolDef 转成
   OpenAI / Gemini 工具格式，零改造。
4. **结果序列化**：MCP ``call_tool`` 返回 ``{"content": [...], "isError": ...}``。
   桥接层把它压成单条字符串供 LLM 消费，但保留原始结构以便 UI / 调试。
5. **优雅降级**：连接失败 → 打日志返回 0 个工具，不抛异常，agent 继续工作。
6. **可重入**：``register_kit_mcp`` 多次调用不会重复注册（按前缀检测并清理）。

入口：

- ``register_kit_mcp(url, ...)``：注册 Kit MCP / 任意 MCP server 的所有工具。
- ``unregister_kit_mcp(prefix)``：按前缀反注册（用于热重载或关闭功能）。
"""

from __future__ import annotations

import json
import re
import threading
from typing import Any, Callable, Dict, List, Optional

from ..tool_registry import ToolDef, ToolPermission, ToolRegistry, _validate_tool_name
from .client import MCPClient, MCPToolInfo
from .transport import MCPError

try:
    from ...core.stage_utils import safe_log
except Exception:  # pragma: no cover
    def safe_log(msg: str, prefix: str = "MCP") -> None:
        print(f"[{prefix}] {msg}")


# =============================================================================
# 注册器状态（用于反注册 / 状态查询）
# =============================================================================

_REGISTRY_LOCK = threading.Lock()
# prefix -> {"client": MCPClient, "tool_names": List[str], "url": str}
_ACTIVE_REGISTRATIONS: Dict[str, Dict[str, Any]] = {}


# =============================================================================
# 公共 API
# =============================================================================

DEFAULT_KIT_MCP_URL = "http://localhost:9902/mcp"
DEFAULT_PREFIX = "kit_mcp__"
DEFAULT_CATEGORY = "kit-mcp"


def register_kit_mcp(
    url: str = DEFAULT_KIT_MCP_URL,
    *,
    prefix: str = DEFAULT_PREFIX,
    category: str = DEFAULT_CATEGORY,
    permission: ToolPermission = ToolPermission.READ_ONLY,
    timeout: float = 30.0,
    extra_headers: Optional[Dict[str, str]] = None,
    raise_on_error: bool = False,
) -> Dict[str, Any]:
    """
    把指定 MCP server 暴露的所有工具注册到 ``ToolRegistry``。

    Args:
        url:         server 地址（默认 Kit MCP 本地 9902）。
        prefix:      工具名前缀；同名 server 重复注册会先反注册旧的。
        category:    注册到 ToolDef 的 category，UI 可据此分组。
        permission:  对该 server 全部工具统一设定的权限等级。
                     Kit MCP 官方三台都是只读，保持默认即可。
        timeout:     单次请求超时（秒）。
        extra_headers: 自定义 HTTP 头（如 server 需要 ``Authorization``）。
        raise_on_error: True 时连接失败会抛出 MCPError；False 时仅打日志返回 0 工具。

    Returns:
        ``{"ok": bool, "url": str, "prefix": str, "registered": int,
           "server_name": str, "server_version": str, "tool_names": [...],
           "error": Optional[str]}``
    """
    summary: Dict[str, Any] = {
        "ok": False,
        "url": url,
        "prefix": prefix,
        "registered": 0,
        "server_name": "",
        "server_version": "",
        "tool_names": [],
        "error": "",
    }

    with _REGISTRY_LOCK:
        # 1. 先把同前缀的旧注册清干净（可重入）
        _unregister_locked(prefix)

        # 2. 起 client，握手
        client = MCPClient(url, timeout=timeout, extra_headers=extra_headers)
        try:
            info = client.connect()
            tools_info = client.list_tools()
        except MCPError as e:
            msg = f"register_kit_mcp({url}) failed: {e}"
            safe_log(msg, prefix="MCP")
            summary["error"] = str(e)
            if raise_on_error:
                raise
            return summary
        except Exception as e:  # 网络层 / 解析层
            msg = f"register_kit_mcp({url}) failed: {e}"
            safe_log(msg, prefix="MCP")
            summary["error"] = str(e)
            if raise_on_error:
                raise
            return summary

        summary["server_name"] = info.server_name
        summary["server_version"] = info.server_version

        # 3. 逐个工具桥接
        registry = ToolRegistry.instance()
        registered_names: List[str] = []
        for t in tools_info:
            tool_def = _build_tool_def(
                client=client,
                tool=t,
                prefix=prefix,
                category=category,
                permission=permission,
            )
            if tool_def is None:
                continue
            registry.register(tool_def)
            registered_names.append(tool_def.name)

        _ACTIVE_REGISTRATIONS[prefix] = {
            "client": client,
            "tool_names": list(registered_names),
            "url": url,
        }

        summary.update(
            ok=len(registered_names) > 0,
            registered=len(registered_names),
            tool_names=list(registered_names),
        )
        safe_log(
            f"registered {len(registered_names)} MCP tool(s) "
            f"from {info.server_name or url} with prefix {prefix!r}",
            prefix="MCP",
        )
        return summary


def unregister_kit_mcp(prefix: str = DEFAULT_PREFIX) -> int:
    """按前缀反注册一组 MCP 工具，返回被移除的工具数。"""
    with _REGISTRY_LOCK:
        return _unregister_locked(prefix)


def get_active_registrations() -> Dict[str, Dict[str, Any]]:
    """返回当前已注册的 MCP 端点（仅元数据，不含 client 实例引用）。"""
    with _REGISTRY_LOCK:
        return {
            prefix: {
                "url": entry.get("url", ""),
                "tool_count": len(entry.get("tool_names", []) or []),
                "tool_names": list(entry.get("tool_names", []) or []),
            }
            for prefix, entry in _ACTIVE_REGISTRATIONS.items()
        }


# =============================================================================
# 内部
# =============================================================================

def _unregister_locked(prefix: str) -> int:
    """已持有 _REGISTRY_LOCK 的反注册实现。"""
    entry = _ACTIVE_REGISTRATIONS.pop(prefix, None)
    if not entry:
        return 0
    registry = ToolRegistry.instance()
    n = 0
    for name in entry.get("tool_names") or []:
        if name in registry:
            registry.unregister(name)
            n += 1
    client: Optional[MCPClient] = entry.get("client")
    if client:
        try:
            client.close()
        except Exception:
            pass
    return n


_NAME_SAFE_RE = re.compile(r"[^a-zA-Z0-9_-]")


def _sanitize_tool_name(prefix: str, raw: str) -> Optional[str]:
    """
    把 ``prefix + raw`` 规范化成符合 ``ToolRegistry`` 命名规则的字符串。

    规则与 ``tool_registry._validate_tool_name`` 对齐：
        ``^[a-zA-Z_][a-zA-Z0-9_-]{2,63}$``
    """
    if not raw:
        return None
    safe_raw = _NAME_SAFE_RE.sub("_", raw)
    candidate = (prefix or "") + safe_raw
    # 总长度限制
    if len(candidate) > 64:
        candidate = candidate[:64]
    # 前缀必须以字母 / 下划线开头
    if not candidate[:1].isalpha() and candidate[:1] != "_":
        candidate = "_" + candidate
        candidate = candidate[:64]
    try:
        _validate_tool_name(candidate)
    except Exception:
        return None
    return candidate


def _build_tool_def(
    *,
    client: MCPClient,
    tool: MCPToolInfo,
    prefix: str,
    category: str,
    permission: ToolPermission,
) -> Optional[ToolDef]:
    """把单个 MCPToolInfo 转成本地 ToolDef。"""
    name = _sanitize_tool_name(prefix, tool.name)
    if not name:
        safe_log(f"skip MCP tool with invalid name: {tool.name!r}", prefix="MCP")
        return None

    description = (tool.description or "").strip() or f"MCP tool {tool.name}"
    # 在描述里说清楚来源 + 原始名，便于 LLM 区分
    description = (
        f"[via MCP {client.url}] {description}\n"
        f"(MCP tool name: {tool.name!r}; calls go through the external MCP server.)"
    )

    schema = tool.input_schema or {"type": "object", "properties": {}}
    if not isinstance(schema, dict):
        schema = {"type": "object", "properties": {}}
    # 确保 type 字段存在（Gemini 兼容性）
    schema.setdefault("type", "object")
    schema.setdefault("properties", {})

    fn = _make_proxy_fn(client=client, original_name=tool.name)

    return ToolDef(
        name=name,
        description=description,
        fn=fn,
        parameters_schema=schema,
        permission=permission,
        category=category,
        tags=["mcp", "external"],
        verify_with=[],
        phase_hint="gather" if permission == ToolPermission.READ_ONLY else "act",
    )


def _make_proxy_fn(*, client: MCPClient, original_name: str) -> Callable[..., Dict[str, Any]]:
    """
    生成一个调用 MCP 工具的代理函数。

    ToolRegistry 的执行入口是 ``tool_def.fn(**arguments)``——LLM 给的 kwargs。
    我们直接转发给 MCP server，再把响应压成 LLM 友好的字典。
    """
    def _proxy(**kwargs: Any) -> Dict[str, Any]:
        try:
            ret = client.call_tool(original_name, kwargs)
        except MCPError as e:
            return {"ok": False, "error": f"MCP call failed: {e}", "tool": original_name}
        except Exception as e:
            return {"ok": False, "error": f"MCP transport failed: {e}", "tool": original_name}

        is_error = bool(ret.get("isError"))
        content_items = ret.get("content") or []
        # MCP content 是分块列表：[{type:text,text:...}, {type:image,data:...}, ...]
        # 把所有 text 块拼成一个字符串给 LLM。
        text_parts: List[str] = []
        non_text: List[Dict[str, Any]] = []
        for item in content_items:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and isinstance(item.get("text"), str):
                text_parts.append(item["text"])
            else:
                non_text.append(item)

        text = "\n\n".join(p for p in text_parts if p) if text_parts else ""

        out: Dict[str, Any] = {
            "ok": not is_error,
            "tool": original_name,
        }
        if text:
            out["text"] = text
        if non_text:
            out["non_text_content"] = non_text
        if is_error:
            out["error"] = text or "MCP tool reported isError=true"
        return out

    _proxy.__name__ = f"mcp_{original_name}"
    _proxy.__doc__ = f"Proxy for MCP tool {original_name!r} on {client.url}"
    return _proxy
