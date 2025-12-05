# -*- coding: utf-8 -*-
"""
曲线宽度调整 ViewModel
======================

管理 BasisCurves 宽度调整功能的 UI 状态和业务逻辑调用。

功能:
    - 实时预览宽度调整效果
    - 批量应用宽度到所有曲线
    - 重置宽度属性
"""

import time
from typing import Tuple

from .base_viewmodel import BaseViewModel
from ..core.stage_utils import get_selection_paths
from ..core.curves_width import (
    collect_curves,
    first_curve_from_selection,
    author_ramp_to_curves,
    clear_widths,
    session_hide_non_preview_curves,
    session_clear_visibility,
    session_force_show_all_curves,
)


# 预览更新的最大帧率
PREVIEW_FPS = 15.0


class CurvesWidthViewModel(BaseViewModel):
    """
    曲线宽度调整的 ViewModel。

    管理目标路径、宽度参数等状态，
    并提供预览和应用操作的命令。

    Attributes:
        target_path: 目标 Prim 路径
        scale: 整体缩放系数
        root_width: 根部宽度
        tip_width: 尖端宽度
        preview_count: 预览曲线数量
        solo_preview: 是否只显示预览曲线
    """

    def __init__(self):
        """初始化 CurvesWidthViewModel。"""
        super().__init__()

        # 目标路径
        self._target_path: str = ""

        # 宽度参数
        self._scale: float = 1.0
        self._root_width: float = 0.25
        self._tip_width: float = 0.03

        # 预览设置
        self._preview_count: int = 2
        self._solo_preview: bool = True

        # 内部状态
        self._last_preview_time: float = 0.0
        self._is_applying: bool = False

        # 参数变更回调
        self._param_changed_callbacks = []

    # =========================================================================
    # 属性
    # =========================================================================

    @property
    def target_path(self) -> str:
        """获取目标路径。"""
        return self._target_path

    @target_path.setter
    def target_path(self, value: str) -> None:
        """设置目标路径。"""
        self._target_path = value
        self._notify_param_changed()

    @property
    def scale(self) -> float:
        """获取整体缩放系数。"""
        return self._scale

    @scale.setter
    def scale(self, value: float) -> None:
        """设置整体缩放系数。"""
        self._scale = max(0.0, value)
        self._on_param_changed()

    @property
    def root_width(self) -> float:
        """获取根部宽度。"""
        return self._root_width

    @root_width.setter
    def root_width(self, value: float) -> None:
        """设置根部宽度。"""
        self._root_width = max(0.0, value)
        self._on_param_changed()

    @property
    def tip_width(self) -> float:
        """获取尖端宽度。"""
        return self._tip_width

    @tip_width.setter
    def tip_width(self, value: float) -> None:
        """设置尖端宽度。"""
        self._tip_width = max(0.0, value)
        self._on_param_changed()

    @property
    def preview_count(self) -> int:
        """获取预览曲线数量。"""
        return self._preview_count

    @preview_count.setter
    def preview_count(self, value: int) -> None:
        """设置预览曲线数量。"""
        self._preview_count = max(1, value)
        self._on_param_changed()

    @property
    def solo_preview(self) -> bool:
        """获取是否只显示预览曲线。"""
        return self._solo_preview

    @solo_preview.setter
    def solo_preview(self, value: bool) -> None:
        """设置是否只显示预览曲线。"""
        self._solo_preview = value
        self._on_param_changed()

    # =========================================================================
    # 参数变更通知
    # =========================================================================

    def add_param_changed_callback(self, callback) -> None:
        """添加参数变更监听器。"""
        if callback not in self._param_changed_callbacks:
            self._param_changed_callbacks.append(callback)

    def remove_param_changed_callback(self, callback) -> None:
        """移除参数变更监听器。"""
        if callback in self._param_changed_callbacks:
            self._param_changed_callbacks.remove(callback)

    def _notify_param_changed(self) -> None:
        """通知参数已变更。"""
        for callback in self._param_changed_callbacks:
            try:
                callback()
            except Exception as e:
                print(f"[CurvesWidthVM] Param changed callback error: {e}")

    def _on_param_changed(self) -> None:
        """参数变更时的处理。"""
        self._notify_param_changed()
        # 自动触发预览更新
        self.preview_update()

    # =========================================================================
    # 命令：设置目标
    # =========================================================================

    def use_selection(self) -> bool:
        """
        从当前选择设置目标路径。

        Returns:
            bool: 是否成功设置
        """
        selection = get_selection_paths()
        path = first_curve_from_selection(selection)

        self._target_path = path
        self.set_status(f"Target = {path}")
        self._notify_param_changed()

        # 立即预览
        self.preview_update(force=True)
        return bool(path)

    # =========================================================================
    # 内部辅助方法
    # =========================================================================

    def _get_all_curves(self):
        """获取目标下的所有曲线。"""
        if not self._target_path:
            return []
        return collect_curves(self._target_path)

    def _get_preview_curves(self):
        """获取预览用的曲线子集。"""
        all_curves = self._get_all_curves()
        n = max(1, self._preview_count)
        return all_curves[:min(n, len(all_curves))]

    def _is_throttled(self) -> bool:
        """检查是否需要节流。"""
        min_dt = 1.0 / PREVIEW_FPS
        current_time = time.time()

        if current_time - self._last_preview_time >= min_dt:
            self._last_preview_time = current_time
            return False
        return True

    # =========================================================================
    # 命令：预览更新
    # =========================================================================

    def preview_update(self, force: bool = False) -> None:
        """
        更新预览效果。

        Args:
            force: 是否强制更新（忽略节流）
        """
        # 如果正在应用，跳过预览
        if self._is_applying:
            return

        # 节流控制
        if not force and self._is_throttled():
            return

        # 检查目标
        if not self._target_path:
            self.set_status("No target.")
            return

        preview_curves = self._get_preview_curves()
        if not preview_curves:
            self.set_status("No BasisCurves under target.")
            return

        # 控制可见性
        if self._solo_preview:
            keep_paths = [c.GetPath().pathString for c in preview_curves]
            session_hide_non_preview_curves(self._target_path, keep_paths)
        else:
            session_clear_visibility(self._target_path)

        # 应用宽度到预览曲线
        wrote, elems = author_ramp_to_curves(
            preview_curves,
            self._root_width,
            self._tip_width,
            self._scale
        )

        total = len(self._get_all_curves())
        self.set_status(
            f"Preview: wrote {wrote} prim(s), elems≈{elems}; total={total}"
        )

    # =========================================================================
    # 命令：应用/重置
    # =========================================================================

    def apply_all(self) -> Tuple[int, int]:
        """
        将宽度应用到所有曲线。

        Returns:
            Tuple[int, int]: (写入的 Prim 数量, 写入的元素数量)
        """
        self._is_applying = True

        try:
            if not self._target_path:
                self.set_status("No target.")
                return 0, 0

            # 清除可见性并强制显示所有曲线
            session_clear_visibility(self._target_path)
            session_force_show_all_curves(self._target_path)

            all_curves = self._get_all_curves()
            if not all_curves:
                self.set_status("No BasisCurves under target.")
                return 0, 0

            # 应用宽度
            wrote, elems = author_ramp_to_curves(
                all_curves,
                self._root_width,
                self._tip_width,
                self._scale
            )

            # 确保所有曲线可见
            session_force_show_all_curves(self._target_path)

            self.set_status(
                f"Apply ALL: wrote {wrote} prim(s), elems≈{elems} (ALL curves visible)"
            )
            return wrote, elems

        finally:
            self._is_applying = False

    def reset_all(self) -> int:
        """
        重置所有曲线的宽度属性。

        Returns:
            int: 清除的曲线数量
        """
        self._is_applying = True

        try:
            if not self._target_path:
                self.set_status("No target.")
                return 0

            # 清除可见性
            session_clear_visibility(self._target_path)

            all_curves = self._get_all_curves()
            if not all_curves:
                self.set_status("No BasisCurves under target.")
                return 0

            # 清除宽度
            n = clear_widths(all_curves)

            # 确保所有曲线可见
            session_force_show_all_curves(self._target_path)

            self.set_status(f"Reset: cleared widths on {n} prim(s); ALL curves visible.")
            return n

        finally:
            self._is_applying = False

    # =========================================================================
    # 生命周期
    # =========================================================================

    def dispose(self) -> None:
        """清理资源。"""
        self._param_changed_callbacks.clear()
        self._target_path = ""
        super().dispose()
