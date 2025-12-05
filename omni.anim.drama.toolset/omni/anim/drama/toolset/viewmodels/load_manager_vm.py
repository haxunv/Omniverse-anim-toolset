# -*- coding: utf-8 -*-
"""
角色加载管理 ViewModel
======================

管理角色加载/卸载功能的 UI 状态和业务逻辑调用。

功能:
    - 设置工作角色
    - 管理其他角色列表
    - 批量加载/卸载操作
"""

from typing import List, Tuple
import traceback

from .base_viewmodel import BaseViewModel
from ..core.stage_utils import get_selection_paths, get_prim_at_path
from ..core.load_manager import (
    load_or_activate,
    unload_or_deactivate,
    batch_load,
    batch_unload,
)


class LoadManagerViewModel(BaseViewModel):
    """
    角色加载管理的 ViewModel。

    管理工作角色和其他角色列表的状态，
    并提供加载/卸载操作的命令。

    Attributes:
        work_character: 当前工作角色路径
        other_characters: 其他角色路径列表
    """

    def __init__(self):
        """初始化 LoadManagerViewModel。"""
        super().__init__()
        self._work_character: str = ""
        self._other_characters: List[str] = []

        # 数据变更回调
        self._data_changed_callbacks = []

    # =========================================================================
    # 属性
    # =========================================================================

    @property
    def work_character(self) -> str:
        """获取当前工作角色路径。"""
        return self._work_character

    @work_character.setter
    def work_character(self, value: str) -> None:
        """设置当前工作角色路径。"""
        self._work_character = value
        self._notify_data_changed()

    @property
    def other_characters(self) -> List[str]:
        """获取其他角色路径列表。"""
        return self._other_characters.copy()

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
                print(f"[LoadManagerVM] Data changed callback error: {e}")

    # =========================================================================
    # 命令：设置工作角色
    # =========================================================================

    def set_work_from_selection(self) -> bool:
        """
        从当前选择设置工作角色。

        Returns:
            bool: 是否成功设置
        """
        selection = get_selection_paths()
        if not selection:
            self.log("Select a prim as working character root first.")
            return False

        self._work_character = selection[0]
        self.log(f"Working character = {self._work_character}")
        self._notify_data_changed()
        return True

    # =========================================================================
    # 命令：管理其他角色列表
    # =========================================================================

    def add_others_from_selection(self) -> int:
        """
        从当前选择添加其他角色。

        Returns:
            int: 添加的角色数量
        """
        selection = get_selection_paths()
        if not selection:
            self.log("Select prims to add as 'other characters'.")
            return 0

        added = 0
        for path in selection:
            # 跳过工作角色
            if path == self._work_character:
                continue
            # 跳过已存在的
            if path not in self._other_characters:
                self._other_characters.append(path)
                added += 1

        self.log(f"Added {added} other characters from selection.")
        self._notify_data_changed()
        return added

    def add_by_path(self, path: str) -> bool:
        """
        通过路径手动添加其他角色。

        支持添加 Deactive 状态的 Prim。

        Args:
            path: Prim 路径

        Returns:
            bool: 是否成功添加
        """
        path = path.strip()
        if not path:
            self.log("Path is empty, nothing to add.")
            return False

        # 验证路径存在
        prim = get_prim_at_path(path)
        if not prim:
            self.log(f"Prim not found at path: {path}")
            return False

        # 检查是否是工作角色
        if path == self._work_character:
            self.log("Path is the working character, skip adding to others.")
            return False

        # 检查是否已存在
        if path in self._other_characters:
            self.log(f"Path already in other list: {path}")
            return False

        self._other_characters.append(path)
        self.log(f"Added by path: {path}")
        self._notify_data_changed()
        return True

    def clear_others(self) -> None:
        """清空其他角色列表。"""
        self._other_characters.clear()
        self.log("Cleared other character list.")
        self._notify_data_changed()

    def remove_other(self, path: str) -> bool:
        """
        移除指定的其他角色。

        Args:
            path: 要移除的路径

        Returns:
            bool: 是否成功移除
        """
        if path in self._other_characters:
            self._other_characters.remove(path)
            self.log(f"Removed: {path}")
            self._notify_data_changed()
            return True
        return False

    # =========================================================================
    # 命令：加载/卸载操作
    # =========================================================================

    def load_work_unload_others(self) -> Tuple[int, int]:
        """
        加载工作角色，卸载其他角色。

        Returns:
            Tuple[int, int]: (成功数, 失败数)
        """
        try:
            success_count = 0
            fail_count = 0

            # 加载工作角色
            if self._work_character:
                self.log(f"Loading working character: {self._work_character}")
                success, msg = load_or_activate(self._work_character)
                if success:
                    success_count += 1
                else:
                    fail_count += 1
            else:
                self.log("No working character set.")

            # 卸载其他角色
            for path in self._other_characters:
                self.log(f"Unloading other character: {path}")
                success, msg = unload_or_deactivate(path)
                if success:
                    success_count += 1
                else:
                    fail_count += 1

            self.log("Done: work loaded, others deactivated.")
            return success_count, fail_count

        except Exception as e:
            self.log(f"Error: {e}")
            traceback.print_exc()
            return 0, 0

    def load_others(self) -> Tuple[int, int]:
        """
        加载其他角色列表中的所有角色。

        Returns:
            Tuple[int, int]: (成功数, 失败数)
        """
        try:
            if not self._other_characters:
                self.log("Other list is empty, nothing to load.")
                return 0, 0

            for path in self._other_characters:
                self.log(f"[Others] Load: {path}")

            success, fail, _ = batch_load(self._other_characters)
            self.log(f"All 'other characters' loaded. Success: {success}, Failed: {fail}")
            return success, fail

        except Exception as e:
            self.log(f"Error in load_others: {e}")
            traceback.print_exc()
            return 0, 0

    def unload_others(self) -> Tuple[int, int]:
        """
        卸载其他角色列表中的所有角色。

        Returns:
            Tuple[int, int]: (成功数, 失败数)
        """
        try:
            if not self._other_characters:
                self.log("Other list is empty, nothing to unload.")
                return 0, 0

            for path in self._other_characters:
                self.log(f"[Others] Unload (Deactivate): {path}")

            success, fail, _ = batch_unload(self._other_characters)
            self.log(f"All 'other characters' deactivated. Success: {success}, Failed: {fail}")
            return success, fail

        except Exception as e:
            self.log(f"Error in unload_others: {e}")
            traceback.print_exc()
            return 0, 0

    def load_all(self) -> Tuple[int, int]:
        """
        加载所有角色（工作角色 + 其他角色）。

        Returns:
            Tuple[int, int]: (成功数, 失败数)
        """
        try:
            all_paths = []

            if self._work_character:
                self.log(f"[ALL] Load working: {self._work_character}")
                all_paths.append(self._work_character)

            for path in self._other_characters:
                self.log(f"[ALL] Load other: {path}")
                all_paths.append(path)

            if not all_paths:
                self.log("No characters to load.")
                return 0, 0

            success, fail, _ = batch_load(all_paths)
            self.log(f"All characters loaded (activated). Success: {success}, Failed: {fail}")
            return success, fail

        except Exception as e:
            self.log(f"Error: {e}")
            traceback.print_exc()
            return 0, 0

    def unload_all(self) -> Tuple[int, int]:
        """
        卸载所有角色（工作角色 + 其他角色）。

        Returns:
            Tuple[int, int]: (成功数, 失败数)
        """
        try:
            all_paths = []

            if self._work_character:
                self.log(f"[ALL] Unload working: {self._work_character}")
                all_paths.append(self._work_character)

            for path in self._other_characters:
                self.log(f"[ALL] Unload other: {path}")
                all_paths.append(path)

            if not all_paths:
                self.log("No characters to unload.")
                return 0, 0

            success, fail, _ = batch_unload(all_paths)
            self.log(f"All characters deactivated. Success: {success}, Failed: {fail}")
            return success, fail

        except Exception as e:
            self.log(f"Error: {e}")
            traceback.print_exc()
            return 0, 0

    # =========================================================================
    # 生命周期
    # =========================================================================

    def dispose(self) -> None:
        """清理资源。"""
        self._data_changed_callbacks.clear()
        self._other_characters.clear()
        self._work_character = ""
        super().dispose()
