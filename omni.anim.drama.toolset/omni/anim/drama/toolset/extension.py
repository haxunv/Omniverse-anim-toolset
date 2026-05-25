# -*- coding: utf-8 -*-
"""
Anim Drama Toolset Extension
============================

Omniverse Kit 扩展入口模块。
"""

import omni.ext
import omni.ui as ui


# =============================================================================
# 扩展信息
# =============================================================================

EXTENSION_NAME = "omni.anim.drama.toolset"
WINDOW_TITLE = "Anim Drama Toolset"
MENU_PATH = f"Window/{WINDOW_TITLE}"


# =============================================================================
# 外部 MCP 设置项（opt-in）
# =============================================================================
# 通过 carb settings 控制是否在启动时桥接外部 MCP server（默认关闭）。
# 在 omniverse 启动配置或本扩展的 toml 里加：
#     [settings]
#     exts."omni.anim.drama.toolset".agent.mcp.kit.enable = true
#     exts."omni.anim.drama.toolset".agent.mcp.kit.url    = "http://localhost:9902/mcp"
S_MCP_KIT_ENABLE = "/exts/omni.anim.drama.toolset/agent/mcp/kit/enable"
S_MCP_KIT_URL = "/exts/omni.anim.drama.toolset/agent/mcp/kit/url"
S_MCP_KIT_PREFIX = "/exts/omni.anim.drama.toolset/agent/mcp/kit/prefix"
S_MCP_KIT_TIMEOUT = "/exts/omni.anim.drama.toolset/agent/mcp/kit/timeout"
DEFAULT_KIT_MCP_URL = "http://localhost:9902/mcp"
DEFAULT_KIT_MCP_PREFIX = "kit_mcp__"


# =============================================================================
# 扩展类
# =============================================================================

class AnimDramaToolsetExtension(omni.ext.IExt):
    """
    Anim Drama Toolset 扩展类。
    """

    def on_startup(self, ext_id: str) -> None:
        """扩展启动回调。"""
        print(f"[{EXTENSION_NAME}] Extension startup")

        # 注册实例供公共 API 使用
        from . import _set_instance
        _set_instance(self)

        # 注册 anime agent 的工具到全局 ToolRegistry
        try:
            from .agent.tools import register_all as _register_agent_tools
            tool_count = _register_agent_tools()
            print(f"[{EXTENSION_NAME}] Registered {tool_count} anime agent tools")
        except Exception as e:
            print(f"[{EXTENSION_NAME}] Failed to register anime agent tools: {e}")

        # 可选：桥接外部 MCP server（默认关闭，需通过 carb settings 启用）
        self._mcp_summary = self._maybe_register_kit_mcp()

        # 延迟导入，避免循环依赖
        from .views.main_window import MainWindow

        # 创建主窗口
        self._window = MainWindow()

        # 监听窗口可见性变化，同步菜单状态
        self._window.set_visibility_changed_fn(self._on_window_visibility_changed)

        # 添加到 Window 菜单
        self._menu_item = None
        try:
            import omni.kit.ui
            editor_menu = omni.kit.ui.get_editor_menu()
            if editor_menu:
                self._menu_item = editor_menu.add_item(
                    MENU_PATH,
                    self._on_menu_click,
                    toggle=True,
                    value=True
                )
        except Exception as e:
            print(f"[{EXTENSION_NAME}] Menu registration failed: {e}")

    def on_shutdown(self) -> None:
        """扩展关闭回调。"""
        print(f"[{EXTENSION_NAME}] Extension shutdown")

        # 反注册外部 MCP 工具
        try:
            if getattr(self, "_mcp_summary", None) and self._mcp_summary.get("ok"):
                from .agent.tools import unregister_external_mcp
                prefix = self._mcp_summary.get("prefix") or DEFAULT_KIT_MCP_PREFIX
                removed = unregister_external_mcp(prefix=prefix)
                if removed:
                    print(f"[{EXTENSION_NAME}] Unregistered {removed} MCP tool(s) (prefix={prefix!r})")
        except Exception as e:
            print(f"[{EXTENSION_NAME}] Failed to unregister MCP tools: {e}")

        # 移除菜单
        try:
            if self._menu_item:
                import omni.kit.ui
                editor_menu = omni.kit.ui.get_editor_menu()
                if editor_menu:
                    editor_menu.remove_item(self._menu_item)
        except Exception:
            pass

        # 销毁窗口
        if hasattr(self, '_window') and self._window:
            self._window.destroy()
            self._window = None

    # =========================================================================
    # MCP 桥接
    # =========================================================================

    def _maybe_register_kit_mcp(self) -> dict:
        """
        如 carb settings 启用了 Kit MCP 桥接，则尝试连接并注册。

        失败不抛异常：networking 错误 / server 不在线 / API key 缺失等都只打印日志，
        agent 继续按原工具集运行。
        """
        try:
            import carb.settings
            settings = carb.settings.get_settings()
        except Exception as e:
            print(f"[{EXTENSION_NAME}] carb.settings unavailable, skip MCP bridge: {e}")
            return {"ok": False, "skipped": True}

        enabled = bool(settings.get(S_MCP_KIT_ENABLE) or False)
        if not enabled:
            return {"ok": False, "enabled": False}

        url = settings.get(S_MCP_KIT_URL) or DEFAULT_KIT_MCP_URL
        prefix = settings.get(S_MCP_KIT_PREFIX) or DEFAULT_KIT_MCP_PREFIX
        timeout = settings.get(S_MCP_KIT_TIMEOUT)
        try:
            timeout = float(timeout) if timeout else 30.0
        except (TypeError, ValueError):
            timeout = 30.0

        print(f"[{EXTENSION_NAME}] Kit MCP enabled, connecting to {url} ...")
        try:
            from .agent.tools import register_external_mcp
            summary = register_external_mcp(
                url=url,
                prefix=prefix,
                timeout=timeout,
                raise_on_error=False,
            )
        except Exception as e:
            print(f"[{EXTENSION_NAME}] Kit MCP registration crashed: {e}")
            return {"ok": False, "error": str(e), "url": url, "prefix": prefix}

        if summary.get("ok"):
            print(
                f"[{EXTENSION_NAME}] Kit MCP connected: "
                f"{summary.get('server_name')} {summary.get('server_version')}, "
                f"+{summary.get('registered')} tool(s)."
            )
        else:
            print(
                f"[{EXTENSION_NAME}] Kit MCP NOT connected ({url}): "
                f"{summary.get('error') or 'no tools registered'}. "
                f"Agent will continue without Kit MCP tools."
            )
        return summary

    def _on_menu_click(self, menu_path: str, value: bool) -> None:
        """菜单点击回调。"""
        if self._window:
            self._window.visible = value

    def _on_window_visibility_changed(self, visible: bool) -> None:
        """窗口可见性变化回调，同步更新菜单状态。"""
        if self._menu_item:
            try:
                import omni.kit.ui
                editor_menu = omni.kit.ui.get_editor_menu()
                if editor_menu:
                    editor_menu.set_value(MENU_PATH, visible)
            except Exception:
                pass
