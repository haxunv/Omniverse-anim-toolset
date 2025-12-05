# -*- coding: utf-8 -*-
"""
UV 传输 ViewModel
=================

管理 UV 数据传输功能的 UI 状态和业务逻辑调用。

功能:
    - 设置源曲线和目标根路径
    - 配置 Primvar 名称和输出路径
    - 执行 UV 烘焙操作
"""

import os
from typing import Optional, Tuple

from .base_viewmodel import BaseViewModel
from ..core.stage_utils import get_stage, get_selection_paths
from ..core.uv_transfer import bake_uv_to_file


class UVTransferViewModel(BaseViewModel):
    """
    UV 传输的 ViewModel。

    管理源曲线路径、目标路径、Primvar 名称等状态，
    并提供 UV 烘焙操作的命令。

    Attributes:
        source_curve: 源 BasisCurves 路径（包含 UV）
        target_root: 目标根路径或 BasisCurves
        primvar_name: Primvar 名称
        output_path: 输出文件路径
    """

    def __init__(self):
        """初始化 UVTransferViewModel。"""
        super().__init__()

        self._source_curve: str = ""
        self._target_root: str = ""
        self._primvar_name: str = "st1"
        self._output_path: str = ""

        # 数据变更回调
        self._data_changed_callbacks = []

    # =========================================================================
    # 属性
    # =========================================================================

    @property
    def source_curve(self) -> str:
        """获取源曲线路径。"""
        return self._source_curve

    @source_curve.setter
    def source_curve(self, value: str) -> None:
        """设置源曲线路径。"""
        self._source_curve = value
        self._notify_data_changed()

    @property
    def target_root(self) -> str:
        """获取目标根路径。"""
        return self._target_root

    @target_root.setter
    def target_root(self, value: str) -> None:
        """设置目标根路径。"""
        self._target_root = value
        self._notify_data_changed()

    @property
    def primvar_name(self) -> str:
        """获取 Primvar 名称。"""
        return self._primvar_name

    @primvar_name.setter
    def primvar_name(self, value: str) -> None:
        """设置 Primvar 名称。"""
        self._primvar_name = value.strip() or "st1"
        self._notify_data_changed()

    @property
    def output_path(self) -> str:
        """获取输出文件路径。"""
        return self._output_path

    @output_path.setter
    def output_path(self, value: str) -> None:
        """设置输出文件路径。"""
        self._output_path = value
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
                print(f"[UVTransferVM] Data changed callback error: {e}")

    # =========================================================================
    # 命令：设置源和目标
    # =========================================================================

    def set_source_from_selection(self) -> bool:
        """
        从当前选择设置源曲线。

        Returns:
            bool: 是否成功设置
        """
        selection = get_selection_paths()
        if not selection:
            self.log("Select a source BasisCurves first.")
            return False

        self._source_curve = selection[0]
        self.log(f"Source = {self._source_curve}")
        self._notify_data_changed()
        return True

    def set_target_from_selection(self) -> bool:
        """
        从当前选择设置目标根路径。

        Returns:
            bool: 是否成功设置
        """
        selection = get_selection_paths()
        if not selection:
            self.log("Select a target root or BasisCurves (ABC).")
            return False

        self._target_root = selection[0]
        self.log(f"Target = {self._target_root}")
        self._notify_data_changed()
        return True

    # =========================================================================
    # 命令：设置输出路径
    # =========================================================================

    def set_output_path(self, path: str) -> None:
        """
        设置输出文件路径。

        Args:
            path: 文件路径
        """
        self._output_path = path.replace("\\", "/")
        self.log(f"Output path = {self._output_path}")
        self._notify_data_changed()

    def get_default_output_path(self) -> str:
        """
        获取默认输出路径。

        基于当前 Stage 的位置生成默认输出路径。

        Returns:
            str: 默认输出路径
        """
        stage = get_stage()
        if stage:
            root_layer = stage.GetRootLayer()
            if root_layer and root_layer.realPath:
                base_dir = os.path.dirname(root_layer.realPath)
                return os.path.join(base_dir, "final_hair.usda").replace("\\", "/")

        return os.path.join(os.path.expanduser("~"), "final_hair.usda").replace("\\", "/")

    def get_stage_base_dir(self) -> str:
        """
        获取当前 Stage 的基础目录。

        用于文件选择对话框的起始目录。

        Returns:
            str: 基础目录路径
        """
        stage = get_stage()
        if stage:
            root_layer = stage.GetRootLayer()
            if root_layer and root_layer.realPath:
                return os.path.dirname(root_layer.realPath)
        return os.path.expanduser("~")

    # =========================================================================
    # 命令：执行烘焙
    # =========================================================================

    def run_bake(self) -> Tuple[bool, str]:
        """
        执行 UV 烘焙操作。

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        # 验证输入
        if not self._source_curve:
            msg = "Please set Source first."
            self.log(msg)
            return False, msg

        if not self._target_root:
            msg = "Please set Target first."
            self.log(msg)
            return False, msg

        # 确保有输出路径
        output = self._output_path
        if not output:
            output = self.get_default_output_path()
            self._output_path = output
            self._notify_data_changed()

        # 确保正确的文件扩展名
        root, ext = os.path.splitext(output)
        if ext.lower() not in (".usda", ".usd", ".usdc"):
            output = root + ".usda"
            self._output_path = output
            self._notify_data_changed()

        # 执行烘焙
        success, message = bake_uv_to_file(
            source_curve_path=self._source_curve,
            target_root_path=self._target_root,
            primvar_name=self._primvar_name,
            output_file_path=output,
            on_log=self.log
        )

        return success, message

    # =========================================================================
    # 验证
    # =========================================================================

    def validate(self) -> Tuple[bool, str]:
        """
        验证当前配置是否可以执行烘焙。

        Returns:
            Tuple[bool, str]: (是否有效, 错误消息)
        """
        if not self._source_curve:
            return False, "Source curve not set."

        if not self._target_root:
            return False, "Target root not set."

        return True, "Ready to bake."

    # =========================================================================
    # 生命周期
    # =========================================================================

    def dispose(self) -> None:
        """清理资源。"""
        self._data_changed_callbacks.clear()
        self._source_curve = ""
        self._target_root = ""
        self._output_path = ""
        super().dispose()
