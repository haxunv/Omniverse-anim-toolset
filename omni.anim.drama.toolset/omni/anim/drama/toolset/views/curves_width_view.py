# -*- coding: utf-8 -*-
"""
曲线宽度调整视图
================

提供 BasisCurves 宽度调整功能的用户界面。

功能:
    - 设置目标路径
    - 调整宽度参数（支持实时预览）
    - 应用/重置宽度
"""

import omni.ui as ui

from .base_view import BaseView
from .styles import Styles, Sizes, Colors
from ..viewmodels.curves_width_vm import CurvesWidthViewModel


class CurvesWidthView(BaseView):
    """
    曲线宽度调整的视图。

    提供完整的 UI 界面来调整 BasisCurves 的宽度。
    """

    def __init__(self, viewmodel: CurvesWidthViewModel):
        """
        初始化视图。

        Args:
            viewmodel: CurvesWidthViewModel 实例
        """
        super().__init__(viewmodel)
        self._vm: CurvesWidthViewModel = viewmodel

        # UI 模型引用
        self._path_model = None
        self._scale_model = None
        self._root_model = None
        self._tip_model = None
        self._preview_n_model = None
        self._solo_model = None

    def build(self) -> None:
        """构建 UI。"""
        with ui.VStack(spacing=Sizes.SPACING_MEDIUM):
            self._build_target_section()
            ui.Separator()
            self._build_width_params_section()
            self._build_preview_section()
            self._create_status_section()
            self._create_log_section()

    # =========================================================================
    # UI 构建：目标设置部分
    # =========================================================================

    def _build_target_section(self) -> None:
        """构建目标路径设置区域。"""
        ui.Label("Target path (Xform/Scope or a Curves):")

        with ui.HStack():
            self._path_model = ui.SimpleStringModel(self._vm.target_path)
            ui.StringField(model=self._path_model)
            ui.Button(
                "Use Selection",
                width=120,
                clicked_fn=self._on_use_selection_clicked
            )

        # 监听路径变化
        self._path_model.add_value_changed_fn(self._on_path_changed)

    # =========================================================================
    # UI 构建：宽度参数部分
    # =========================================================================

    def _build_width_params_section(self) -> None:
        """构建宽度参数调整区域。"""
        # 整体厚度
        ui.Label("Overall thickness")
        with ui.HStack():
            self._scale_model = ui.SimpleFloatModel(self._vm.scale)
            ui.FloatSlider(model=self._scale_model, min=0.0, max=2.0, step=0.001)
            ui.FloatField(model=self._scale_model, width=80)

        # 根部/尖端宽度
        ui.Label("Root / Tip")
        with ui.HStack():
            self._root_model = ui.SimpleFloatModel(self._vm.root_width)
            ui.FloatSlider(model=self._root_model, min=0.0, max=1.0, step=0.0005)
            ui.FloatField(model=self._root_model, width=80)

            ui.Spacer(width=12)

            self._tip_model = ui.SimpleFloatModel(self._vm.tip_width)
            ui.FloatSlider(model=self._tip_model, min=0.0, max=1.0, step=0.0005)
            ui.FloatField(model=self._tip_model, width=80)

        # 绑定参数变化监听
        self._scale_model.add_value_changed_fn(self._on_scale_changed)
        self._root_model.add_value_changed_fn(self._on_root_changed)
        self._tip_model.add_value_changed_fn(self._on_tip_changed)

    # =========================================================================
    # UI 构建：预览设置部分
    # =========================================================================

    def _build_preview_section(self) -> None:
        """构建预览设置和操作按钮区域。"""
        with ui.HStack():
            ui.Label("Preview N:", width=80)

            self._preview_n_model = ui.SimpleIntModel(self._vm.preview_count)
            ui.IntField(model=self._preview_n_model, width=80)

            self._solo_model = ui.SimpleBoolModel(self._vm.solo_preview)
            ui.CheckBox(model=self._solo_model)
            ui.Label("Solo preview (hide others)")

            ui.Spacer()

            ui.Button(
                "Apply All",
                width=120,
                clicked_fn=self._on_apply_clicked
            )
            ui.Button(
                "Reset",
                width=90,
                clicked_fn=self._on_reset_clicked
            )

        # 绑定预览参数变化监听
        self._preview_n_model.add_value_changed_fn(self._on_preview_n_changed)
        self._solo_model.add_value_changed_fn(self._on_solo_changed)

    # =========================================================================
    # 事件处理
    # =========================================================================

    def _on_use_selection_clicked(self) -> None:
        """使用选择按钮点击。"""
        self._vm.use_selection()
        # 同步路径到 UI
        if self._path_model:
            self._path_model.set_value(self._vm.target_path)

    def _on_path_changed(self, model) -> None:
        """路径变化处理。"""
        self._vm.target_path = model.get_value_as_string()

    def _on_scale_changed(self, model) -> None:
        """缩放系数变化处理。"""
        self._vm.scale = model.get_value_as_float()

    def _on_root_changed(self, model) -> None:
        """根部宽度变化处理。"""
        self._vm.root_width = model.get_value_as_float()

    def _on_tip_changed(self, model) -> None:
        """尖端宽度变化处理。"""
        self._vm.tip_width = model.get_value_as_float()

    def _on_preview_n_changed(self, model) -> None:
        """预览数量变化处理。"""
        self._vm.preview_count = model.get_value_as_int()

    def _on_solo_changed(self, model) -> None:
        """独奏预览变化处理。"""
        self._vm.solo_preview = model.get_value_as_bool()

    def _on_apply_clicked(self) -> None:
        """应用按钮点击。"""
        self._vm.apply_all()

    def _on_reset_clicked(self) -> None:
        """重置按钮点击。"""
        self._vm.reset_all()

    # =========================================================================
    # 生命周期
    # =========================================================================

    def dispose(self) -> None:
        """清理资源。"""
        self._path_model = None
        self._scale_model = None
        self._root_model = None
        self._tip_model = None
        self._preview_n_model = None
        self._solo_model = None
        super().dispose()
