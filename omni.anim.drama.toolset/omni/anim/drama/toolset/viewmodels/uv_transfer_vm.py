# -*- coding: utf-8 -*-
"""
UV 传输 ViewModel
=================

管理 UV 数据传输功能的 UI 状态和业务逻辑调用。

功能:
    - 设置源曲线和目标根路径
    - 配置 Primvar 名称和输出路径
    - 执行 UV 烘焙操作
    - 批量处理多对 Source-Target
"""

import os
from typing import Optional, Tuple, List, Dict

from .base_viewmodel import BaseViewModel
from ..core.stage_utils import get_stage, get_selection_paths
from ..core.uv_transfer import bake_uv_to_file, bake_uv_to_standalone_file


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
        pairs_list: 批量处理的 Source-Target 对列表
    """

    def __init__(self):
        """初始化 UVTransferViewModel。"""
        super().__init__()

        self._source_curve: str = ""
        self._target_root: str = ""
        self._primvar_name: str = "st1"
        self._output_path: str = ""

        # 批量处理列表: [{"source": str, "target": str}, ...]
        self._pairs_list: List[Dict[str, str]] = []

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

    @property
    def pairs_list(self) -> List[Dict[str, str]]:
        """获取批量处理列表。"""
        return self._pairs_list

    @property
    def pairs_count(self) -> int:
        """获取批量处理列表中的对数。"""
        return len(self._pairs_list)

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

    def run_bake_standalone(self) -> Tuple[bool, str]:
        """
        执行独立 UV 烘焙操作（生成不依赖原文件的独立文件）。

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
            output = self.get_default_output_path().replace("final_hair", "standalone_hair")
            self._output_path = output
            self._notify_data_changed()

        # 确保正确的文件扩展名
        root, ext = os.path.splitext(output)
        if ext.lower() not in (".usda", ".usd", ".usdc"):
            output = root + ".usda"
            self._output_path = output
            self._notify_data_changed()

        # 执行独立烘焙
        success, message = bake_uv_to_standalone_file(
            source_curve_path=self._source_curve,
            target_root_path=self._target_root,
            primvar_name=self._primvar_name,
            output_file_path=output,
            on_log=self.log
        )

        return success, message

    # =========================================================================
    # 批量处理：列表管理
    # =========================================================================

    def add_current_pair(self) -> bool:
        """
        将当前 Source-Target 对添加到批量处理列表。

        Returns:
            bool: 是否成功添加
        """
        if not self._source_curve:
            self.log("Please set Source first.")
            return False

        if not self._target_root:
            self.log("Please set Target first.")
            return False

        # 检查是否已存在
        for pair in self._pairs_list:
            if pair["source"] == self._source_curve and pair["target"] == self._target_root:
                self.log("This pair already exists in the list.")
                return False

        # 添加到列表
        self._pairs_list.append({
            "source": self._source_curve,
            "target": self._target_root
        })

        self.log(f"Added pair #{len(self._pairs_list)}: {self._source_curve} → {self._target_root}")
        self._notify_data_changed()
        return True

    def remove_pair(self, index: int) -> bool:
        """
        从批量处理列表中移除指定索引的对。

        Args:
            index: 要移除的对的索引

        Returns:
            bool: 是否成功移除
        """
        if 0 <= index < len(self._pairs_list):
            removed = self._pairs_list.pop(index)
            self.log(f"Removed pair: {removed['source']} → {removed['target']}")
            self._notify_data_changed()
            return True
        return False

    def clear_pairs_list(self) -> None:
        """清空批量处理列表。"""
        self._pairs_list.clear()
        self.log("Pairs list cleared.")
        self._notify_data_changed()

    def get_pairs_display_list(self) -> List[str]:
        """
        获取用于显示的对列表字符串。

        Returns:
            List[str]: 格式化的字符串列表
        """
        result = []
        for i, pair in enumerate(self._pairs_list):
            # 简化路径显示
            src_name = pair["source"].split("/")[-1] if "/" in pair["source"] else pair["source"]
            tgt_name = pair["target"].split("/")[-1] if "/" in pair["target"] else pair["target"]
            result.append(f"{i+1}. {src_name} → {tgt_name}")
        return result

    # =========================================================================
    # 批量处理：执行烘焙
    # =========================================================================

    def run_batch_bake(self, standalone: bool = False) -> Tuple[int, int, List[str]]:
        """
        批量执行 UV 烘焙。

        Args:
            standalone: 是否生成独立文件

        Returns:
            Tuple[int, int, List[str]]: (成功数, 失败数, 错误消息列表)
        """
        if not self._pairs_list:
            self.log("No pairs in the list. Add pairs first.")
            return 0, 0, ["No pairs in the list"]

        # 确定输出目录
        output_dir = self._output_path
        if output_dir:
            # 如果是文件路径，取其目录
            if os.path.splitext(output_dir)[1]:
                output_dir = os.path.dirname(output_dir)
        if not output_dir:
            output_dir = self.get_stage_base_dir()

        self.log(f"═══ Batch Bake Start ═══")
        self.log(f"Total pairs: {len(self._pairs_list)}")
        self.log(f"Output directory: {output_dir}")
        self.log(f"Mode: {'Standalone' if standalone else 'Reloc-safe'}")

        success_count = 0
        fail_count = 0
        errors = []

        bake_func = bake_uv_to_standalone_file if standalone else bake_uv_to_file

        for i, pair in enumerate(self._pairs_list):
            source = pair["source"]
            target = pair["target"]

            # 生成输出文件名
            target_name = target.split("/")[-1] if "/" in target else target
            output_file = os.path.join(
                output_dir,
                f"{target_name}_uv.usda"
            ).replace("\\", "/")

            self.log(f"[{i+1}/{len(self._pairs_list)}] Processing: {target_name}")

            try:
                success, message = bake_func(
                    source_curve_path=source,
                    target_root_path=target,
                    primvar_name=self._primvar_name,
                    output_file_path=output_file,
                    on_log=self.log
                )

                if success:
                    success_count += 1
                else:
                    fail_count += 1
                    errors.append(f"Pair {i+1}: {message}")

            except Exception as e:
                fail_count += 1
                errors.append(f"Pair {i+1}: {str(e)}")
                self.log(f"Error: {e}")

        self.log(f"═══ Batch Bake Complete ═══")
        self.log(f"Success: {success_count}, Failed: {fail_count}")

        return success_count, fail_count, errors

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
        self._pairs_list.clear()
        super().dispose()
