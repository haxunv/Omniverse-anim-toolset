# -*- coding: utf-8 -*-
"""
MCP Client - 同步包装层
=======================

把 ``transport.HTTPJsonRpcTransport`` 包成业务友好的 API：

- ``MCPClient.list_tools()``    → ``List[MCPToolInfo]``
- ``MCPClient.call_tool(name, args)`` → ``Dict``  ← 给 ToolDef 桥接器用

为什么不用 mcp 官方 SDK：

- 它强依赖 anyio + 异步上下文；Omniverse Kit 的 Python 不一定能干净安装。
- 我们只用到极小的子集，自己实现 200 行就够，且对齐项目风格（urllib + 同步）。

线程模型：
- 所有方法都同步阻塞返回。
- 内部 transport 已加锁，可以从多线程同时调用同一个 client，但顺序串行。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .transport import (
    HTTPJsonRpcTransport,
    MCPError,
    MCPProtocolError,
    MCPTransportError,
)

try:
    from ...core.stage_utils import safe_log
except Exception:  # pragma: no cover
    def safe_log(msg: str, prefix: str = "MCP") -> None:
        print(f"[{prefix}] {msg}")


# =============================================================================
# 数据结构
# =============================================================================

@dataclass
class MCPToolInfo:
    """server 暴露的一个工具的元信息。"""
    name: str
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MCPToolInfo":
        return cls(
            name=str(d.get("name") or ""),
            description=str(d.get("description") or ""),
            input_schema=dict(d.get("inputSchema") or {}),
        )


@dataclass
class MCPServerInfo:
    """server 在 initialize 时返回的元信息（用于诊断）。"""
    protocol_version: str = ""
    server_name: str = ""
    server_version: str = ""
    instructions: str = ""
    capabilities: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_init_result(cls, d: Dict[str, Any]) -> "MCPServerInfo":
        info = (d or {}).get("serverInfo") or {}
        return cls(
            protocol_version=str(d.get("protocolVersion") or ""),
            server_name=str(info.get("name") or ""),
            server_version=str(info.get("version") or ""),
            instructions=str(d.get("instructions") or ""),
            capabilities=dict(d.get("capabilities") or {}),
        )


# =============================================================================
# MCPClient
# =============================================================================

class MCPClient:
    """
    一个 MCP server 的同步客户端。

    用法::

        client = MCPClient("http://localhost:9902/mcp")
        info = client.connect()                 # initialize 握手
        tools = client.list_tools()             # 拿工具列表
        out = client.call_tool("search_kit_extensions", {"query": "transform"})
    """

    def __init__(
        self,
        url: str,
        *,
        timeout: float = 30.0,
        extra_headers: Optional[Dict[str, str]] = None,
        log_prefix: str = "MCP",
    ) -> None:
        self._url = url
        self._log_prefix = log_prefix
        self._transport = HTTPJsonRpcTransport(
            url, timeout=timeout, extra_headers=extra_headers
        )
        self._info: Optional[MCPServerInfo] = None
        self._tools_cache: Optional[List[MCPToolInfo]] = None
        self._lock = threading.Lock()

    # ---------- 公共 ----------

    @property
    def url(self) -> str:
        return self._url

    @property
    def is_connected(self) -> bool:
        return self._transport.is_initialized

    @property
    def server_info(self) -> Optional[MCPServerInfo]:
        return self._info

    def connect(self) -> MCPServerInfo:
        """握手 + 缓存 server info。已连接则直接返回缓存。"""
        with self._lock:
            if self._transport.is_initialized and self._info:
                return self._info
            try:
                init_result = self._transport.initialize()
            except MCPError as e:
                raise
            except Exception as e:
                raise MCPTransportError(f"initialize failed: {e}")
            self._info = MCPServerInfo.from_init_result(init_result)
            safe_log(
                f"connected to {self._url} ({self._info.server_name} "
                f"{self._info.server_version}, proto={self._info.protocol_version})",
                prefix=self._log_prefix,
            )
            return self._info

    def list_tools(self, *, refresh: bool = False) -> List[MCPToolInfo]:
        """列出 server 工具。结果有缓存（除非 refresh=True）。"""
        if not self._transport.is_initialized:
            self.connect()
        if not refresh and self._tools_cache is not None:
            return list(self._tools_cache)

        result = self._transport.request("tools/list", {})
        raw_tools = result.get("tools") or []
        tools = [MCPToolInfo.from_dict(t) for t in raw_tools if isinstance(t, dict)]
        self._tools_cache = tools
        safe_log(f"listed {len(tools)} tool(s) from {self._url}", prefix=self._log_prefix)
        return list(tools)

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        调用 server 的某个工具。

        返回：MCP 规范的 ``{"content": [...], "isError": bool}`` 字典。
        我们刻意不"扁平化"，让上层桥接器决定怎么呈现给 LLM。
        """
        if not self._transport.is_initialized:
            self.connect()

        params = {"name": name, "arguments": dict(arguments or {})}
        result = self._transport.request("tools/call", params)
        # 规范字段做容错
        return {
            "content": list(result.get("content") or []),
            "isError": bool(result.get("isError") or False),
            # 透传其它字段，方便诊断
            "raw": result,
        }

    def close(self) -> None:
        try:
            self._transport.close()
        finally:
            self._tools_cache = None
            self._info = None

    # ---------- 健康检查（用于 UI 状态指示） ----------

    def ping(self) -> bool:
        """
        快速可达性检查。不抛异常；返回 True/False。

        实际行为：尝试 initialize（有缓存就跳过），失败返回 False。
        """
        try:
            self.connect()
            return True
        except Exception as e:
            safe_log(f"ping failed: {e}", prefix=self._log_prefix)
            return False
