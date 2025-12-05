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
