# -*- coding: utf-8 -*-
"""
Light Link 视图
===============

提供 Light Link 功能的用户界面。

功能:
    - 选择几何体并设置
    - 选择灯光并设置
    - 创建 Light Link
    - 查看和管理 Light Link
"""

import omni.ui as ui

from .base_view import BaseView
from .styles import Styles, Sizes, Colors
from ..viewmodels.light_link_vm import LightLinkViewModel


class LightLinkView(BaseView):
    """
    Light Link 的视图。

    提供完整的 UI 界面来创建和管理灯光链接。
    操作流程：
    1. 选择一个几何体，点击"设置几何体"
    2. 选择一个灯光，点击"设置灯光"
    3. 点击"创建 Light Link"完成关联
    """

    def __init__(self, viewmodel: LightLinkViewModel):
        """
        初始化视图。

        Args:
            viewmodel: LightLinkViewModel 实例
        """
        super().__init__(viewmodel)
        self._vm: LightLinkViewModel = viewmodel

        # UI 组件引用
        self._geo_label = None
        self._light_label = None
        self._shadow_checkbox = None
        self._info_field = None

        # 绑定数据变更
        self._vm.add_data_changed_callback(self._refresh_display)

    def build(self) -> None:
        """构建 UI。"""
        with ui.VStack(spacing=Sizes.SPACING_MEDIUM):
            self._build_header()
            ui.Separator(height=2)
            self._build_step1_geometry()
            self._build_step2_light()
            self._build_options()
            ui.Separator(height=2)
            self._build_step3_action()
            ui.Separator(height=2)
            self._build_info_section()
            self._create_log_section()

    # =========================================================================
    # UI 构建：标题
    # =========================================================================

    def _build_header(self) -> None:
        """构建标题区域。"""
        ui.Label(
            "Light Link Tool",
            style={"font_size": 16, "color": Colors.TEXT_PRIMARY}
        )
        ui.Label(
            "Link lights to specific geometry for precise lighting control",
            style={"color": Colors.TEXT_SECONDARY}
        )

    # =========================================================================
    # UI 构建：步骤1 - 设置几何体
    # =========================================================================

    def _build_step1_geometry(self) -> None:
        """构建几何体设置区域。"""
        with ui.CollapsableFrame("Select Geometry", collapsed=False):
            with ui.VStack(spacing=Sizes.SPACING_SMALL):
                ui.Label(
                    "Select the object to be illuminated, then click the button below",
                    style={"color": Colors.TEXT_SECONDARY}
                )

                with ui.HStack(height=30):
                    ui.Label("Geometry:", width=80)
                    self._geo_label = ui.Label(
                        "Not Set",
                        word_wrap=True,
                        style={"color": Colors.WARNING}
                    )

                ui.Button(
                    "Set Geometry (from Selection)",
                    height=Sizes.BUTTON_HEIGHT,
                    clicked_fn=self._on_set_geometry_clicked
                )

    # =========================================================================
    # UI 构建：步骤2 - 设置灯光
    # =========================================================================

    def _build_step2_light(self) -> None:
        """构建灯光设置区域。"""
        with ui.CollapsableFrame("Select Light", collapsed=False):
            with ui.VStack(spacing=Sizes.SPACING_SMALL):
                ui.Label(
                    "Select the light to link, then click the button below",
                    style={"color": Colors.TEXT_SECONDARY}
                )

                with ui.HStack(height=30):
                    ui.Label("Light:", width=80)
                    self._light_label = ui.Label(
                        "Not Set",
                        word_wrap=True,
                        style={"color": Colors.WARNING}
                    )

                ui.Button(
                    "Set Light (from Selection)",
                    height=Sizes.BUTTON_HEIGHT,
                    clicked_fn=self._on_set_light_clicked
                )

    # =========================================================================
    # UI 构建：选项
    # =========================================================================

    def _build_options(self) -> None:
        """构建选项区域。"""
        with ui.HStack(height=24):
            ui.Label("Options:", width=80)
            self._shadow_checkbox = ui.CheckBox(width=20)
            self._shadow_checkbox.model.set_value(self._vm.include_shadow)
            self._shadow_checkbox.model.add_value_changed_fn(self._on_shadow_changed)
            ui.Label("Also create Shadow Link")

    # =========================================================================
    # UI 构建：步骤3 - 执行操作
    # =========================================================================

    def _build_step3_action(self) -> None:
        """构建操作按钮区域。"""
        with ui.CollapsableFrame("Step 3: Create Link", collapsed=False):
            with ui.VStack(spacing=Sizes.SPACING_SMALL):
                ui.Label(
                    "Confirm the settings above, then click to create Light Link",
                    style={"color": Colors.TEXT_SECONDARY}
                )

                ui.Button(
                    "Create Light Link",
                    height=Sizes.BUTTON_HEIGHT_LARGE,
                    style=Styles.BUTTON_SUCCESS,
                    clicked_fn=self._on_create_clicked
                )

                with ui.HStack(spacing=Sizes.SPACING_SMALL):
                    ui.Button(
                        "Remove Link",
                        height=Sizes.BUTTON_HEIGHT,
                        clicked_fn=self._on_remove_clicked
                    )
                    ui.Button(
                        "Clear Selection",
                        height=Sizes.BUTTON_HEIGHT,
                        clicked_fn=self._on_clear_clicked
                    )

    # =========================================================================
    # UI 构建：信息显示
    # =========================================================================

    def _build_info_section(self) -> None:
        """构建信息显示区域。"""
        with ui.CollapsableFrame("Light Link Info", collapsed=True):
            with ui.VStack(spacing=Sizes.SPACING_SMALL):
                ui.Button(
                    "Show Light Link Info",
                    height=Sizes.BUTTON_HEIGHT,
                    clicked_fn=self._on_show_info_clicked
                )

                self._info_field = ui.StringField(
                    multiline=True,
                    height=100,
                    read_only=True
                )

    # =========================================================================
    # 事件处理
    # =========================================================================

    def _on_set_geometry_clicked(self) -> None:
        """设置几何体按钮点击。"""
        self._vm.set_geometry_from_selection()

    def _on_set_light_clicked(self) -> None:
        """设置灯光按钮点击。"""
        self._vm.set_light_from_selection()

    def _on_shadow_changed(self, model) -> None:
        """阴影选项变化处理。"""
        self._vm.include_shadow = model.get_value_as_bool()

    def _on_create_clicked(self) -> None:
        """创建 Light Link 按钮点击。"""
        self._vm.create_link()

    def _on_remove_clicked(self) -> None:
        """移除 Light Link 按钮点击。"""
        self._vm.remove_link()

    def _on_clear_clicked(self) -> None:
        """清空选择按钮点击。"""
        self._vm.clear_selections()

    def _on_show_info_clicked(self) -> None:
        """显示信息按钮点击。"""
        info = self._vm.show_light_link_info()
        if self._info_field:
            self._info_field.model.set_value(info)

    # =========================================================================
    # 数据刷新
    # =========================================================================

    def _refresh_display(self) -> None:
        """刷新显示数据。"""
        # 更新几何体显示
        if self._geo_label:
            geo_path = self._vm.geometry_path
            if geo_path:
                self._geo_label.text = geo_path
                self._geo_label.style = {"color": Colors.SUCCESS}
            else:
                self._geo_label.text = "Not Set"
                self._geo_label.style = {"color": Colors.WARNING}

        # 更新灯光显示
        if self._light_label:
            light_path = self._vm.light_path
            if light_path:
                self._light_label.text = light_path
                self._light_label.style = {"color": Colors.SUCCESS}
            else:
                self._light_label.text = "Not Set"
                self._light_label.style = {"color": Colors.WARNING}

        # 更新阴影选项
        if self._shadow_checkbox:
            self._shadow_checkbox.model.set_value(self._vm.include_shadow)

    # =========================================================================
    # 生命周期
    # =========================================================================

    def dispose(self) -> None:
        """清理资源。"""
        self._vm.remove_data_changed_callback(self._refresh_display)
        self._geo_label = None
        self._light_label = None
        self._shadow_checkbox = None
        self._info_field = None
        super().dispose()

