# -*- coding: utf-8 -*-
"""
角色加载管理视图
================

提供角色加载/卸载功能的用户界面。

功能:
    - 设置工作角色
    - 管理其他角色列表
    - 执行加载/卸载操作
"""

import omni.ui as ui

from .base_view import BaseView
from .styles import Styles, Sizes, Colors
from ..viewmodels.load_manager_vm import LoadManagerViewModel


class LoadManagerView(BaseView):
    """
    角色加载管理的视图。

    提供完整的 UI 界面来管理角色的加载和卸载。
    """

    def __init__(self, viewmodel: LoadManagerViewModel):
        """
        初始化视图。

        Args:
            viewmodel: LoadManagerViewModel 实例
        """
        super().__init__(viewmodel)
        self._vm: LoadManagerViewModel = viewmodel

        # UI 组件引用
        self._work_label = None
        self._other_label = None
        self._manual_field = None

        # 绑定数据变更
        self._vm.add_data_changed_callback(self._refresh_display)

    def build(self) -> None:
        """构建 UI。"""
        with ui.VStack(spacing=Sizes.SPACING_MEDIUM):
            self._build_work_character_section()
            ui.Separator()
            self._build_other_characters_section()
            ui.Separator()
            self._build_action_buttons()
            self._create_log_section()

    # =========================================================================
    # UI 构建：工作角色部分
    # =========================================================================

    def _build_work_character_section(self) -> None:
        """构建工作角色设置区域。"""
        # 工作角色显示
        with ui.HStack():
            ui.Label("Working Character Root:", width=Sizes.LABEL_WIDTH)
            self._work_label = ui.Label(
                "",
                word_wrap=True,
                style=Styles.get_path_label_style()
            )

        # 设置按钮
        with ui.HStack():
            ui.Spacer(width=Sizes.LABEL_WIDTH)
            ui.Button(
                "Set Working Character from Selection",
                clicked_fn=self._on_set_work_clicked
            )

    # =========================================================================
    # UI 构建：其他角色部分
    # =========================================================================

    def _build_other_characters_section(self) -> None:
        """构建其他角色管理区域。"""
        # 其他角色列表（带滚动条）
        with ui.HStack():
            ui.Label("Other Characters (one per line):", width=Sizes.LABEL_WIDTH)

            with ui.ScrollingFrame(
                height=100,
                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED
            ):
                with ui.VStack():
                    self._other_label = ui.Label("", word_wrap=True)

        # 手动输入路径
        with ui.HStack():
            ui.Label("Add by Path:", width=Sizes.LABEL_WIDTH_SMALL)
            self._manual_field = ui.StringField(height=Sizes.INPUT_HEIGHT)
            ui.Button(
                "Add Path to Others",
                clicked_fn=self._on_add_by_path_clicked,
                width=140
            )

        # 选择添加和清空按钮
        with ui.HStack():
            ui.Spacer(width=Sizes.LABEL_WIDTH)
            ui.Button(
                "Add Other Characters from Selection",
                clicked_fn=self._on_add_others_clicked
            )
            ui.Button(
                "Clear List",
                clicked_fn=self._on_clear_clicked
            )

    # =========================================================================
    # UI 构建：操作按钮部分
    # =========================================================================

    def _build_action_buttons(self) -> None:
        """构建操作按钮区域。"""
        # 主要操作：加载工作角色/卸载其他角色
        ui.Button(
            "Load Working / Unload Others",
            height=Sizes.BUTTON_HEIGHT_LARGE,
            style=Styles.BUTTON_SUCCESS,
            clicked_fn=self._on_load_work_unload_others_clicked
        )

        # 对其他角色列表的操作
        with ui.HStack():
            ui.Label("By Others List:", width=Sizes.LABEL_WIDTH_SMALL)
            ui.Button(
                "Load Selected",
                clicked_fn=self._on_load_others_clicked
            )
            ui.Button(
                "Unload Selected",
                clicked_fn=self._on_unload_others_clicked
            )

        # 全部操作
        with ui.HStack():
            ui.Button(
                "Load All (Work + Others)",
                clicked_fn=self._on_load_all_clicked
            )
            ui.Button(
                "Unload All (Work + Others)",
                clicked_fn=self._on_unload_all_clicked
            )

    # =========================================================================
    # 事件处理
    # =========================================================================

    def _on_set_work_clicked(self) -> None:
        """设置工作角色按钮点击。"""
        self._vm.set_work_from_selection()

    def _on_add_others_clicked(self) -> None:
        """从选择添加其他角色按钮点击。"""
        self._vm.add_others_from_selection()

    def _on_add_by_path_clicked(self) -> None:
        """通过路径添加按钮点击。"""
        path = self._manual_field.model.get_value_as_string()
        self._vm.add_by_path(path)

    def _on_clear_clicked(self) -> None:
        """清空列表按钮点击。"""
        self._vm.clear_others()

    def _on_load_work_unload_others_clicked(self) -> None:
        """加载工作角色/卸载其他按钮点击。"""
        self._vm.load_work_unload_others()

    def _on_load_others_clicked(self) -> None:
        """加载其他角色按钮点击。"""
        self._vm.load_others()

    def _on_unload_others_clicked(self) -> None:
        """卸载其他角色按钮点击。"""
        self._vm.unload_others()

    def _on_load_all_clicked(self) -> None:
        """加载全部按钮点击。"""
        self._vm.load_all()

    def _on_unload_all_clicked(self) -> None:
        """卸载全部按钮点击。"""
        self._vm.unload_all()

    # =========================================================================
    # 数据刷新
    # =========================================================================

    def _refresh_display(self) -> None:
        """刷新显示数据。"""
        if self._work_label:
            self._work_label.text = self._vm.work_character

        if self._other_label:
            self._other_label.text = "\n".join(self._vm.other_characters)

    # =========================================================================
    # 生命周期
    # =========================================================================

    def dispose(self) -> None:
        """清理资源。"""
        self._vm.remove_data_changed_callback(self._refresh_display)
        self._work_label = None
        self._other_label = None
        self._manual_field = None
        super().dispose()
