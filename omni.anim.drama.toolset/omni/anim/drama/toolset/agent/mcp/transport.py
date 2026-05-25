# -*- coding: utf-8 -*-
"""
MCP HTTP Transport - JSON-RPC over HTTP
========================================

实现 Model Context Protocol 的 streamable-HTTP 传输层（最小子集）。

我们只需要三件事：

1. ``initialize``  握手 + 拿 ``Mcp-Session-Id``
2. ``tools/list``  列出 server 暴露的工具
3. ``tools/call``  调用某个工具

不实现：

- SSE 流式（``text/event-stream``）：我们只需要请求-响应，让 server 走 JSON。
- prompts / resources / sampling / roots：和我们的场景无关。
- 通知（notifications）：只发一条 ``notifications/initialized``，无需监听。

参考：
- MCP 规范 2025-03-26
- NVIDIA Kit MCP Server 用 NAT (NeMo Agent Toolkit) 实现，遵循同一规范

依赖：仅 stdlib，对齐 ``agent/backend/openai_compat_backend.py`` 的写法。
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, Optional

try:
    from ...core.stage_utils import safe_log
except Exception:  # pragma: no cover
    def safe_log(msg: str, prefix: str = "MCP") -> None:
        print(f"[{prefix}] {msg}")


# =============================================================================
# 异常
# =============================================================================

class MCPError(Exception):
    """所有 MCP 相关错误的基类。"""


class MCPTransportError(MCPError):
    """网络层 / HTTP 层错误（连接失败、超时、非 2xx 状态码）。"""


class MCPProtocolError(MCPError):
    """JSON-RPC 协议层错误（server 返回 ``error`` 字段）。"""


# =============================================================================
# 协议常量
# =============================================================================

PROTOCOL_VERSION = "2025-03-26"
DEFAULT_TIMEOUT = 30.0  # 秒；list_tools 一般 < 1s，tool/call 视工具而定
CLIENT_NAME = "omni.anim.drama.toolset.copilot"
CLIENT_VERSION = "0.3.0"


# =============================================================================
# Transport
# =============================================================================

class HTTPJsonRpcTransport:
    """
    极简的 MCP-over-HTTP JSON-RPC 客户端。

    使用：

        t = HTTPJsonRpcTransport("http://localhost:9902/mcp")
        t.initialize()
        tools = t.request("tools/list", {})["tools"]
        result = t.request("tools/call", {"name": "...", "arguments": {...}})

    线程安全：内部加锁保证一次连接里 request 顺序串行（MCP 规范允许并发，
    但我们 agent worker 本来就是单线程跑工具，串行更稳）。
    """

    def __init__(
        self,
        url: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        if not url:
            raise MCPTransportError("MCP url must be non-empty.")
        self._url = url
        self._timeout = float(timeout)
        self._extra_headers = dict(extra_headers or {})
        self._session_id: Optional[str] = None
        self._initialized = False
        self._lock = threading.Lock()

    # ---------- 公共属性 ----------

    @property
    def url(self) -> str:
        return self._url

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    # ---------- 主流程 ----------

    def initialize(self) -> Dict[str, Any]:
        """
        发起 MCP initialize 握手。

        Returns:
            server 的 ``serverInfo`` / ``capabilities`` 字典（用于诊断 / UI 展示）。

        Raises:
            MCPTransportError: 网络错误。
            MCPProtocolError:  server 拒绝或协议版本不匹配。
        """
        params = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {
                # 我们不实现这些能力，但要列出，让 server 知道。
                "roots": {"listChanged": False},
                "sampling": {},
            },
            "clientInfo": {
                "name": CLIENT_NAME,
                "version": CLIENT_VERSION,
            },
        }
        result = self.request("initialize", params, _bypass_init_check=True)

        # 通知 server 我们 initialized
        try:
            self._send_notification("notifications/initialized", {})
        except Exception as e:  # 非关键失败：记录但不中断
            safe_log(f"notifications/initialized failed: {e}", prefix="MCP")

        self._initialized = True
        return result or {}

    def request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        timeout: Optional[float] = None,
        _bypass_init_check: bool = False,
    ) -> Dict[str, Any]:
        """
        发起一次 JSON-RPC 请求并等待 result。

        Raises:
            MCPTransportError / MCPProtocolError
        """
        if not _bypass_init_check and not self._initialized:
            raise MCPProtocolError("Transport not initialized; call initialize() first.")

        envelope = {
            "jsonrpc": "2.0",
            "id": uuid.uuid4().hex[:16],
            "method": method,
            "params": params or {},
        }
        with self._lock:
            response = self._post(envelope, timeout=timeout)

        if "error" in response and response["error"]:
            err = response["error"]
            raise MCPProtocolError(
                f"MCP error: code={err.get('code')} message={err.get('message')!r}"
            )
        return response.get("result") or {}

    def close(self) -> None:
        """显式发起 ``DELETE`` 关闭 session（server 可选支持）。"""
        if not self._session_id:
            return
        try:
            req = urllib.request.Request(self._url, method="DELETE", headers=self._headers())
            urllib.request.urlopen(req, timeout=5.0).read()
        except Exception as e:  # 关闭失败不重要
            safe_log(f"close session failed (ignored): {e}", prefix="MCP")
        finally:
            self._session_id = None
            self._initialized = False

    # ---------- 内部 ----------

    def _send_notification(self, method: str, params: Dict[str, Any]) -> None:
        """发 JSON-RPC notification（无 id，不等待响应）。"""
        envelope = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        }
        with self._lock:
            self._post(envelope, expect_response=False, timeout=5.0)

    def _post(
        self,
        envelope: Dict[str, Any],
        *,
        timeout: Optional[float] = None,
        expect_response: bool = True,
    ) -> Dict[str, Any]:
        """同步 POST 一条 JSON-RPC envelope。"""
        body = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self._url,
            data=body,
            method="POST",
            headers=self._headers(),
        )
        eff_timeout = timeout if timeout is not None else self._timeout
        try:
            with urllib.request.urlopen(req, timeout=eff_timeout) as resp:
                # 捕获 server 分配的 session id（仅 initialize 响应里有）
                sid = resp.headers.get("Mcp-Session-Id")
                if sid:
                    self._session_id = sid

                status = resp.status
                if status == 202 or not expect_response:
                    return {}

                content_type = (resp.headers.get("Content-Type") or "").lower()
                raw = resp.read()
                if not raw:
                    return {}
                # 简单兼容：text/event-stream 时取第一条 data 行
                if "text/event-stream" in content_type:
                    return _parse_first_sse_data(raw.decode("utf-8", errors="replace"))
                # 默认 application/json
                try:
                    return json.loads(raw.decode("utf-8", errors="replace"))
                except json.JSONDecodeError as e:
                    raise MCPTransportError(f"Invalid JSON from MCP server: {e}")
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode("utf-8", errors="replace")
            except Exception:
                detail = ""
            raise MCPTransportError(
                f"HTTP {e.code} from MCP server {self._url}: {detail[:300]}"
            )
        except urllib.error.URLError as e:
            raise MCPTransportError(f"Cannot reach MCP server {self._url}: {e.reason}")
        except TimeoutError as e:
            raise MCPTransportError(f"MCP request timed out after {eff_timeout}s: {e}")

    def _headers(self) -> Dict[str, str]:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        h.update(self._extra_headers)
        if self._session_id:
            h["Mcp-Session-Id"] = self._session_id
        return h


# =============================================================================
# Helpers
# =============================================================================

def _parse_first_sse_data(text: str) -> Dict[str, Any]:
    """
    一个最小 SSE 解析：抓第一条 ``data: {...}`` 行的 JSON。

    Kit MCP server 在简单的 request/response 模式下通常返回 application/json，
    这个函数只是兜底，避免 Accept 头协商出 SSE 时直接失败。
    """
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            payload = line[len("data:"):].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                continue
    return {}
