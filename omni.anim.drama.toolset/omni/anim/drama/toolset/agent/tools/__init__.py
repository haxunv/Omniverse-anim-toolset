# -*- coding: utf-8 -*-
"""
Agent Tools - 工具包

每个子模块负责把 core/ 中的业务函数包装成 LLM 可调用的工具。

使用 ``register_all()`` 在扩展启动时批量注册所有工具。
"""

from __future__ import annotations


def register_all() -> int:
    """
    注册所有工具到全局 ToolRegistry。

    工具分组：

    Domain (L2, 编码了最佳实践与安全策略):
        - scene_tools:        场景 / 灯光 / 相机查询
        - lighting_tools:     灯光 create / modify / delete / link
        - asset_tools:        USD Search 资产检索 / reference 进 stage
        - usd_code_tools:     受控 USD Python 执行（ChatUSD-like fallback）
        - vision_tools:       describe_reference_image (图 -> SceneGraph JSON)
        - layout_tools:       pick_best_asset / propose_layout / create_camera_for_view
    Meta (L1, 通用元工具，让 agent 能"自己探索"):
        - planning_tools:     submit_plan
        - usd_introspection:  inspect_prim / list_animated_prims / get_time_samples / ...
        - kit_introspection:  list_kit_commands / get_kit_command_doc / execute_kit_command
        - skill_tools:        list_skills / search_skills / read_skill

    External (opt-in, 由 extension.py 根据 carb settings 决定是否启用):
        - mcp/:               接入外部 MCP server（如 NVIDIA Kit MCP）注册的工具

    Returns:
        int: 已注册的工具总数（不含 MCP；MCP 走 register_external_mcp）。
    """
    from . import scene_tools  # noqa: F401
    from . import lighting_tools  # noqa: F401
    from . import asset_tools  # noqa: F401
    from . import usd_code_tools  # noqa: F401
    from . import vision_tools  # noqa: F401
    from . import layout_tools  # noqa: F401
    from . import planning_tools  # noqa: F401
    from . import usd_introspection  # noqa: F401
    from . import kit_introspection  # noqa: F401
    from . import skill_tools  # noqa: F401

    from ..tool_registry import ToolRegistry
    return len(ToolRegistry.instance())


def register_external_mcp(url: str, *, prefix: str = "kit_mcp__", **kwargs):
    """
    Opt-in：把外部 MCP server 暴露的工具桥接到本扩展的 ToolRegistry。

    封装 ``agent.mcp.register_kit_mcp`` 给 extension.py 调用，便于以后这里
    加日志 / 节流 / 多 server 编排。

    Args:
        url: MCP server 地址，如 ``http://localhost:9902/mcp``。
        prefix: 工具名前缀；同前缀重复调用会先反注册旧工具再注册新工具。
        kwargs: 其余参数（permission / timeout / extra_headers 等）转发给
                ``register_kit_mcp``。

    Returns:
        register_kit_mcp 的 summary 字典（含 ``ok / registered / tool_names`` 等）。
    """
    from ..mcp import register_kit_mcp
    return register_kit_mcp(url=url, prefix=prefix, **kwargs)


def unregister_external_mcp(prefix: str = "kit_mcp__") -> int:
    """按前缀反注册所有 MCP 桥接工具，返回被移除的工具数。"""
    from ..mcp import unregister_kit_mcp
    return unregister_kit_mcp(prefix=prefix)
