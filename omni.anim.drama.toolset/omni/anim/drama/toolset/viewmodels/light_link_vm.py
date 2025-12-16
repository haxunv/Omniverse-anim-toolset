# -*- coding: utf-8 -*-
"""
Light Link ViewModel
====================

管理 Light Link 功能的 UI 状态和业务逻辑调用。

功能:
    - 设置源几何体和目标灯光
    - 执行 Light Link 创建和移除
    - 查看当前 Light Link 状态
"""

from typing import Optional, Tuple, List

from .base_viewmodel import BaseViewModel
from ..core.stage_utils import get_stage, get_selection_paths
from ..core.light_link import (
    create_light_link,
    remove_light_link,
    get_light_link_targets,
    get_light_link_info,
    is_light_prim,
    is_geometry_prim,
    create_shadow_link,
)


class LightLinkViewModel(BaseViewModel):
    """
    Light Link 的 ViewModel。

    管理几何体路径、灯光路径等状态，
    并提供 Light Link 创建和管理的命令。

    Attributes:
        geometry_path: 选中的几何体路径
        light_path: 选中的灯光路径
        include_shadow: 是否同时创建 Shadow Link
    """

    def __init__(self):
        """初始化 LightLinkViewModel。"""
        super().__init__()

        self._geometry_path: str = ""
        self._light_path: str = ""
        self._include_shadow: bool = True

        # 数据变更回调
        self._data_changed_callbacks = []

    # =========================================================================
    # 属性
    # =========================================================================

    @property
    def geometry_path(self) -> str:
        """获取几何体路径。"""
        return self._geometry_path

    @geometry_path.setter
    def geometry_path(self, value: str) -> None:
        """设置几何体路径。"""
        self._geometry_path = value
        self._notify_data_changed()

    @property
    def light_path(self) -> str:
        """获取灯光路径。"""
        return self._light_path

    @light_path.setter
    def light_path(self, value: str) -> None:
        """设置灯光路径。"""
        self._light_path = value
        self._notify_data_changed()

    @property
    def include_shadow(self) -> bool:
        """获取是否包含阴影链接。"""
        return self._include_shadow

    @include_shadow.setter
    def include_shadow(self, value: bool) -> None:
        """设置是否包含阴影链接。"""
        self._include_shadow = value
        self._notify_data_changed()

    # =========================================================================
    # 数据变更通知
    # =========================================================================

    def add_data_changed_callback(self, callback) -> None:
        """添加数据变更监听器。"""
        if callback not in self._data_changed_callbacks:
            self._data_changed_callbacks.append(callback)

    def remove_data_changed_callback(self, callback) -> None:
        """移除数据变更监听器。"""
        if callback in self._data_changed_callbacks:
            self._data_changed_callbacks.remove(callback)

    def _notify_data_changed(self) -> None:
        """通知数据已变更。"""
        for callback in self._data_changed_callbacks:
            try:
                callback()
            except Exception as e:
                print(f"[LightLinkVM] Data changed callback error: {e}")

    # =========================================================================
    # 命令：设置几何体和灯光
    # =========================================================================

    def set_geometry_from_selection(self) -> bool:
        """
        从当前选择设置几何体。

        Returns:
            bool: 是否成功设置
        """
        selection = get_selection_paths()
        if not selection:
            self.log("⚠️ Please select a geometry first")
            return False

        stage = get_stage()
        if not stage:
            self.log("❌ No Stage open")
            return False

        # 验证是否为几何体
        prim = stage.GetPrimAtPath(selection[0])
        if not prim or not prim.IsValid():
            self.log(f"❌ Invalid Prim: {selection[0]}")
            return False

        # 检查是否误选了灯光
        if is_light_prim(prim):
            self.log(f"⚠️ Selected a light, please select geometry: {selection[0]}")
            return False

        self._geometry_path = selection[0]
        self.log(f"✓ Geometry = {self._geometry_path}")
        self._notify_data_changed()
        return True

    def set_light_from_selection(self) -> bool:
        """
        从当前选择设置灯光。

        Returns:
            bool: 是否成功设置
        """
        selection = get_selection_paths()
        if not selection:
            self.log("⚠️ Please select a light first")
            return False

        stage = get_stage()
        if not stage:
            self.log("❌ No Stage open")
            return False

        # 验证是否为灯光
        prim = stage.GetPrimAtPath(selection[0])
        if not prim or not prim.IsValid():
            self.log(f"❌ Invalid Prim: {selection[0]}")
            return False

        if not is_light_prim(prim):
            self.log(f"⚠️ Selected is not a light, please select a light: {selection[0]}")
            return False

        self._light_path = selection[0]
        self.log(f"✓ Light = {self._light_path}")
        self._notify_data_changed()
        return True

    # =========================================================================
    # 命令：创建 Light Link
    # =========================================================================

    def create_link(self) -> Tuple[bool, str]:
        """
        创建 Light Link。

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        # 验证输入
        if not self._geometry_path:
            msg = "❌ Please set geometry first"
            self.log(msg)
            return False, msg

        if not self._light_path:
            msg = "❌ Please set light first"
            self.log(msg)
            return False, msg

        # 创建 Light Link
        success, message = create_light_link(
            light_path=self._light_path,
            geometry_path=self._geometry_path,
            include_mode=True
        )

        if success:
            self.log(f"✅ Light Link created successfully!")
            self.log(f"   Light: {self._light_path}")
            self.log(f"   Geometry: {self._geometry_path}")

            # 如果需要，同时创建 Shadow Link
            if self._include_shadow:
                shadow_success, shadow_msg = create_shadow_link(
                    light_path=self._light_path,
                    geometry_path=self._geometry_path,
                    include_mode=True
                )
                if shadow_success:
                    self.log(f"   + Shadow Link created")
                else:
                    self.log(f"   ⚠️ Shadow Link failed: {shadow_msg}")
        else:
            self.log(f"❌ Creation failed: {message}")

        return success, message

    def remove_link(self) -> Tuple[bool, str]:
        """
        移除当前灯光的所有 Light Link。

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        if not self._light_path:
            msg = "❌ Please set light first"
            self.log(msg)
            return False, msg

        success, message = remove_light_link(
            light_path=self._light_path,
            geometry_path=self._geometry_path if self._geometry_path else None
        )

        if success:
            self.log(f"✅ Light Link removed")
        else:
            self.log(f"❌ Remove failed: {message}")

        return success, message

    # =========================================================================
    # 命令：查看信息
    # =========================================================================

    def show_light_link_info(self) -> str:
        """
        显示当前灯光的 Light Link 信息。

        Returns:
            str: 格式化的信息字符串
        """
        if not self._light_path:
            msg = "⚠️ Please set light first"
            self.log(msg)
            return msg

        info = get_light_link_info(self._light_path)

        if "error" in info:
            self.log(f"❌ {info['error']}")
            return info["error"]

        # 格式化输出
        lines = [
            f"═══ Light Link Info ═══",
            f"Light: {info['light_path']}",
            f"Has Light Link: {'Yes' if info['has_light_link'] else 'No'}",
        ]

        if info['has_light_link']:
            lines.append(f"Include Root: {info['include_root']}")
            lines.append(f"Includes ({len(info['includes'])}):")
            for path in info['includes']:
                lines.append(f"  + {path}")
            lines.append(f"Excludes ({len(info['excludes'])}):")
            for path in info['excludes']:
                lines.append(f"  - {path}")

        result = "\n".join(lines)
        self.log(result)
        return result

    def get_linked_targets(self) -> Tuple[List[str], List[str]]:
        """
        获取当前灯光链接的目标。

        Returns:
            Tuple[List[str], List[str]]: (includes, excludes)
        """
        if not self._light_path:
            return [], []

        return get_light_link_targets(self._light_path)

    # =========================================================================
    # 验证
    # =========================================================================

    def validate(self) -> Tuple[bool, str]:
        """
        验证当前配置是否可以创建 Light Link。

        Returns:
            Tuple[bool, str]: (是否有效, 错误消息)
        """
        if not self._geometry_path:
            return False, "Geometry not set."

        if not self._light_path:
            return False, "Light not set."

        return True, "Ready to create Light Link."

    # =========================================================================
    # 快捷操作
    # =========================================================================

    def clear_selections(self) -> None:
        """清空所有选择。"""
        self._geometry_path = ""
        self._light_path = ""
        self._notify_data_changed()
        self.log("Selection cleared")

    def swap_selections(self) -> None:
        """交换几何体和灯光选择（用于调试/特殊用途）。"""
        self._geometry_path, self._light_path = self._light_path, self._geometry_path
        self._notify_data_changed()
        self.log("Selection swapped")

    # =========================================================================
    # 生命周期
    # =========================================================================

    def dispose(self) -> None:
        """清理资源。"""
        self._data_changed_callbacks.clear()
        self._geometry_path = ""
        self._light_path = ""
        super().dispose()

