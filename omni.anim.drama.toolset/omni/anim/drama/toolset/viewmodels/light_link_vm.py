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
        geometry_paths: 选中的几何体路径列表（支持多选）
        light_path: 选中的灯光路径
        include_shadow: 是否同时创建 Shadow Link
    """

    def __init__(self):
        """初始化 LightLinkViewModel。"""
        super().__init__()

        self._geometry_paths: List[str] = []
        self._light_path: str = ""
        self._include_shadow: bool = True

        # 数据变更回调
        self._data_changed_callbacks = []

    # =========================================================================
    # 属性
    # =========================================================================

    @property
    def geometry_paths(self) -> List[str]:
        """获取几何体路径列表。"""
        return self._geometry_paths

    @geometry_paths.setter
    def geometry_paths(self, value: List[str]) -> None:
        """设置几何体路径列表。"""
        self._geometry_paths = value
        self._notify_data_changed()

    @property
    def geometry_path(self) -> str:
        """获取第一个几何体路径（兼容旧接口）。"""
        return self._geometry_paths[0] if self._geometry_paths else ""

    @property
    def geometry_count(self) -> int:
        """获取几何体数量。"""
        return len(self._geometry_paths)

    def get_geometry_display(self) -> str:
        """获取几何体显示文本。"""
        count = len(self._geometry_paths)
        if count == 0:
            return "Not Set"
        elif count == 1:
            return self._geometry_paths[0]
        else:
            # 显示第一个和数量
            first_name = self._geometry_paths[0].split("/")[-1]
            return f"{first_name} (+{count - 1} more)"

    def get_geometry_list_data(self) -> List[dict]:
        """
        获取几何体列表数据，用于表格显示。

        Returns:
            List[dict]: 包含 index, name, path 的字典列表
        """
        result = []
        for i, path in enumerate(self._geometry_paths):
            name = path.split("/")[-1] if "/" in path else path
            result.append({
                "index": i,
                "name": name,
                "path": path
            })
        return result

    def remove_geometry_at(self, index: int) -> bool:
        """
        删除指定索引的几何体。

        Args:
            index: 要删除的几何体索引

        Returns:
            bool: 是否成功删除
        """
        if 0 <= index < len(self._geometry_paths):
            removed = self._geometry_paths.pop(index)
            name = removed.split("/")[-1]
            self.log(f"✓ Removed: {name}")
            self._notify_data_changed()
            return True
        return False

    def remove_geometry_by_path(self, path: str) -> bool:
        """
        根据路径删除几何体。

        Args:
            path: 要删除的几何体路径

        Returns:
            bool: 是否成功删除
        """
        if path in self._geometry_paths:
            self._geometry_paths.remove(path)
            name = path.split("/")[-1]
            self.log(f"✓ Removed: {name}")
            self._notify_data_changed()
            return True
        return False

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
        从当前选择设置几何体（支持多选）。

        Returns:
            bool: 是否成功设置
        """
        selection = get_selection_paths()
        if not selection:
            self.log("⚠️ Please select geometry first")
            return False

        stage = get_stage()
        if not stage:
            self.log("❌ No Stage open")
            return False

        valid_paths = []
        skipped_lights = 0

        for path in selection:
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsValid():
                self.log(f"⚠️ Skipped invalid Prim: {path}")
                continue

            # 跳过灯光
            if is_light_prim(prim):
                skipped_lights += 1
                continue

            valid_paths.append(path)

        if not valid_paths:
            self.log("❌ No valid geometry in selection")
            if skipped_lights > 0:
                self.log(f"   (Skipped {skipped_lights} lights)")
            return False

        self._geometry_paths = valid_paths

        if len(valid_paths) == 1:
            self.log(f"✓ Geometry = {valid_paths[0]}")
        else:
            self.log(f"✓ Geometries = {len(valid_paths)} selected")
            for i, path in enumerate(valid_paths[:5]):  # 只显示前5个
                name = path.split("/")[-1]
                self.log(f"   {i+1}. {name}")
            if len(valid_paths) > 5:
                self.log(f"   ... and {len(valid_paths) - 5} more")

        if skipped_lights > 0:
            self.log(f"   (Skipped {skipped_lights} lights)")

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
        创建 Light Link（支持多个几何体）。

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        # 验证输入
        if not self._geometry_paths:
            msg = "❌ Please set geometry first"
            self.log(msg)
            return False, msg

        if not self._light_path:
            msg = "❌ Please set light first"
            self.log(msg)
            return False, msg

        success_count = 0
        fail_count = 0

        self.log(f"Creating Light Link for {len(self._geometry_paths)} geometries...")

        for geo_path in self._geometry_paths:
            # 创建 Light Link
            success, message = create_light_link(
                light_path=self._light_path,
                geometry_path=geo_path,
                include_mode=True
            )

            if success:
                success_count += 1

                # 如果需要，同时创建 Shadow Link
                if self._include_shadow:
                    create_shadow_link(
                        light_path=self._light_path,
                        geometry_path=geo_path,
                        include_mode=True
                    )
            else:
                fail_count += 1
                geo_name = geo_path.split("/")[-1]
                self.log(f"   ⚠️ Failed: {geo_name} - {message}")

        # 汇总结果
        if fail_count == 0:
            self.log(f"✅ Light Link created successfully!")
            self.log(f"   Light: {self._light_path}")
            self.log(f"   Geometries: {success_count}")
            if self._include_shadow:
                self.log(f"   + Shadow Links created")
            return True, f"Created {success_count} links"
        elif success_count > 0:
            self.log(f"⚠️ Partial success: {success_count} succeeded, {fail_count} failed")
            return True, f"Created {success_count} links, {fail_count} failed"
        else:
            self.log(f"❌ All {fail_count} links failed")
            return False, "All links failed"

    def remove_link(self) -> Tuple[bool, str]:
        """
        移除当前灯光的 Light Link。

        如果设置了几何体，则只移除对应几何体的链接；
        否则移除该灯光的所有链接。

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        if not self._light_path:
            msg = "❌ Please set light first"
            self.log(msg)
            return False, msg

        if self._geometry_paths:
            # 移除指定几何体的链接
            success_count = 0
            fail_count = 0

            for geo_path in self._geometry_paths:
                success, message = remove_light_link(
                    light_path=self._light_path,
                    geometry_path=geo_path
                )
                if success:
                    success_count += 1
                else:
                    fail_count += 1

            if success_count > 0:
                self.log(f"✅ Removed {success_count} Light Link(s)")
                if fail_count > 0:
                    self.log(f"   ({fail_count} failed)")
                return True, f"Removed {success_count} links"
            else:
                self.log(f"❌ Remove failed")
                return False, "Remove failed"
        else:
            # 移除该灯光的所有链接
            success, message = remove_light_link(
                light_path=self._light_path,
                geometry_path=None
            )

            if success:
                self.log(f"✅ All Light Links removed")
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
        if not self._geometry_paths:
            return False, "Geometry not set."

        if not self._light_path:
            return False, "Light not set."

        count = len(self._geometry_paths)
        return True, f"Ready to create {count} Light Link(s)."

    # =========================================================================
    # 快捷操作
    # =========================================================================

    def clear_selections(self) -> None:
        """清空所有选择。"""
        self._geometry_paths = []
        self._light_path = ""
        self._notify_data_changed()
        self.log("Selection cleared")

    def add_geometry_from_selection(self) -> bool:
        """
        从当前选择添加几何体到已有列表（追加模式）。

        Returns:
            bool: 是否成功添加
        """
        selection = get_selection_paths()
        if not selection:
            self.log("⚠️ Please select geometry first")
            return False

        stage = get_stage()
        if not stage:
            self.log("❌ No Stage open")
            return False

        added_count = 0
        for path in selection:
            if path in self._geometry_paths:
                continue  # 已经在列表中

            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsValid():
                continue

            if is_light_prim(prim):
                continue  # 跳过灯光

            self._geometry_paths.append(path)
            added_count += 1

        if added_count > 0:
            self.log(f"✓ Added {added_count} geometry, total: {len(self._geometry_paths)}")
            self._notify_data_changed()
            return True
        else:
            self.log("⚠️ No new geometry to add")
            return False

    def clear_geometries(self) -> None:
        """只清空几何体选择。"""
        self._geometry_paths = []
        self._notify_data_changed()
        self.log("Geometries cleared")

    # =========================================================================
    # 生命周期
    # =========================================================================

    def dispose(self) -> None:
        """清理资源。"""
        self._data_changed_callbacks.clear()
        self._geometry_paths = []
        self._light_path = ""
        super().dispose()

