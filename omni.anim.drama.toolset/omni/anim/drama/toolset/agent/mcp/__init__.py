# -*- coding: utf-8 -*-
"""
MCP (Model Context Protocol) 接入层
====================================

让本扩展的 agent 把外部 MCP server 暴露的工具，**当作普通工具**注册进
``ToolRegistry``，从而和我们自己写的 anime/scene/lighting 工具同台被 LLM 调用。

设计目标：
- 零额外 Python 依赖（用 stdlib ``urllib.request`` + JSON-RPC，对齐
  ``backend/openai_compat_backend.py`` 的风格）。
- Opt-in：默认不启动；通过 carb settings 或 ``register_kit_mcp(...)`` 显式打开。
- 优雅降级：server 不在线时只打日志，不抛异常，不影响 agent 主流程。
- 名字隔离：注册时给 MCP 工具加前缀（默认 ``kit_mcp__``）以避免与本地工具撞名。

子模块：

- ``transport``: 极简 MCP-over-HTTP JSON-RPC 客户端，处理 initialize 握手、
  Mcp-Session-Id、tools/list、tools/call。
- ``client``:    同步友好的 ``MCPClient`` 包装层，给注册器和单测用。
- ``bridge``:    把 server 暴露的工具列表桥接成 ``ToolDef`` 注册到 ``ToolRegistry``。

使用示例（在 ``tools/__init__.py`` 的 ``register_all`` 里被调用）::

    from ..mcp import register_kit_mcp
    register_kit_mcp(url="http://localhost:9902/mcp")
"""

from __future__ import annotations

from .bridge import register_kit_mcp, unregister_kit_mcp  # noqa: F401
from .client import MCPClient  # noqa: F401
