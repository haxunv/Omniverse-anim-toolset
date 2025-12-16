# -*- coding: utf-8 -*-
"""
UV 传输视图
===========

提供 UV 数据传输功能的用户界面。

功能:
    - 设置源曲线和目标路径
    - 配置 Primvar 名称和输出路径
    - 执行 UV 烘焙
"""

import omni.ui as ui

from .base_view import BaseView
from .styles import Styles, Sizes, Colors
from ..viewmodels.uv_transfer_vm import UVTransferViewModel


class UVTransferView(BaseView):
    """
    UV 传输的视图。

    提供完整的 UI 界面来执行 UV 数据传输操作。
    """

    def __init__(self, viewmodel: UVTransferViewModel):
        """
        初始化视图。

        Args:
            viewmodel: UVTransferViewModel 实例
        """
        super().__init__(viewmodel)
        self._vm: UVTransferViewModel = viewmodel

        # UI 组件引用
        self._src_label = None
        self._tgt_field = None
        self._pv_field = None
        self._out_field = None
        self._picker = None

        # 批量处理 UI 组件
        self._pairs_list_field = None
        self._pairs_count_label = None

        # 绑定数据变更
        self._vm.add_data_changed_callback(self._refresh_display)

    def build(self) -> None:
        """构建 UI。"""
        with ui.VStack(spacing=Sizes.SPACING_MEDIUM):
            self._build_source_section()
            self._build_target_section()
            self._build_primvar_section()
            self._build_output_section()
            ui.Separator()
            self._build_action_button()
            ui.Separator()
            self._build_batch_section()
            self._create_log_section()

    # =========================================================================
    # UI 构建：源曲线部分
    # =========================================================================

    def _build_source_section(self) -> None:
        """构建源曲线设置区域。"""
        with ui.HStack():
            ui.Label("Source BasisCurves (has UV):", width=Sizes.LABEL_WIDTH + 60)
            self._src_label = ui.Label(
                "",
                word_wrap=True,
                style=Styles.get_path_label_style(40)
            )

        with ui.HStack():
            ui.Spacer(width=Sizes.LABEL_WIDTH + 60)
            ui.Button(
                "Set Source from Selection",
                clicked_fn=self._on_set_source_clicked
            )

    # =========================================================================
    # UI 构建：目标部分
    # =========================================================================

    def _build_target_section(self) -> None:
        """构建目标设置区域。"""
        with ui.HStack():
            ui.Label("Target Root or BasisCurves (ABC):", width=Sizes.LABEL_WIDTH + 60)
            self._tgt_field = ui.StringField()

        with ui.HStack():
            ui.Spacer(width=Sizes.LABEL_WIDTH + 60)
            ui.Button(
                "Set Target from Selection",
                clicked_fn=self._on_set_target_clicked
            )

    # =========================================================================
    # UI 构建：Primvar 部分
    # =========================================================================

    def _build_primvar_section(self) -> None:
        """构建 Primvar 名称设置区域。"""
        with ui.HStack():
            ui.Label("Primvar name:", width=Sizes.LABEL_WIDTH + 60)
            self._pv_field = ui.StringField()
            self._pv_field.model.set_value(self._vm.primvar_name)

        # 监听变化
        self._pv_field.model.add_value_changed_fn(self._on_primvar_changed)

    # =========================================================================
    # UI 构建：输出文件部分
    # =========================================================================

    def _build_output_section(self) -> None:
        """构建输出文件设置区域。"""
        with ui.HStack():
            ui.Label("Output file:", width=Sizes.LABEL_WIDTH + 60)
            self._out_field = ui.StringField()
            ui.Button(
                "Browse…",
                width=90,
                clicked_fn=self._on_browse_clicked
            )

    # =========================================================================
    # UI 构建：操作按钮部分
    # =========================================================================

    def _build_action_button(self) -> None:
        """构建操作按钮区域。"""
        ui.Label("Single Bake:", style={"color": Colors.TEXT_SECONDARY})
        ui.Button(
            "Bake (reloc-safe) → final.usd[a/c]",
            height=Sizes.BUTTON_HEIGHT_LARGE,
            style=Styles.BUTTON_SUCCESS,
            clicked_fn=self._on_bake_clicked
        )
        ui.Spacer(height=4)
        ui.Button(
            "Bake (standalone) → No Dependencies",
            height=Sizes.BUTTON_HEIGHT_LARGE,
            style={"color": Colors.INFO},
            clicked_fn=self._on_bake_standalone_clicked
        )

    # =========================================================================
    # UI 构建：批量处理部分
    # =========================================================================

    def _build_batch_section(self) -> None:
        """构建批量处理区域。"""
        with ui.CollapsableFrame("Batch Processing", collapsed=True):
            with ui.VStack(spacing=Sizes.SPACING_SMALL):
                # 说明
                ui.Label(
                    "Add multiple Source-Target pairs to process in batch",
                    style={"color": Colors.TEXT_SECONDARY}
                )

                # 添加按钮
                with ui.HStack(height=Sizes.BUTTON_HEIGHT):
                    ui.Button(
                        "Add Current Pair to List",
                        clicked_fn=self._on_add_pair_clicked
                    )
                    ui.Button(
                        "Clear List",
                        width=100,
                        clicked_fn=self._on_clear_pairs_clicked
                    )

                # 对数显示
                with ui.HStack(height=24):
                    ui.Label("Pairs in list:", width=100)
                    self._pairs_count_label = ui.Label(
                        "0",
                        style={"color": Colors.WARNING}
                    )

                # 列表显示
                ui.Label("Pairs List:", style={"color": Colors.TEXT_SECONDARY})
                self._pairs_list_field = ui.StringField(
                    multiline=True,
                    height=80,
                    read_only=True
                )
                self._pairs_list_field.model.set_value("(empty)")

                ui.Spacer(height=4)

                # 批量执行按钮
                ui.Label("Batch Bake:", style={"color": Colors.TEXT_SECONDARY})
                ui.Button(
                    "Batch Bake All (reloc-safe)",
                    height=Sizes.BUTTON_HEIGHT_LARGE,
                    style=Styles.BUTTON_SUCCESS,
                    clicked_fn=self._on_batch_bake_clicked
                )
                ui.Spacer(height=4)
                ui.Button(
                    "Batch Bake All (standalone)",
                    height=Sizes.BUTTON_HEIGHT_LARGE,
                    style={"color": Colors.INFO},
                    clicked_fn=self._on_batch_bake_standalone_clicked
                )

    # =========================================================================
    # 事件处理
    # =========================================================================

    def _on_set_source_clicked(self) -> None:
        """设置源曲线按钮点击。"""
        self._vm.set_source_from_selection()

    def _on_set_target_clicked(self) -> None:
        """设置目标按钮点击。"""
        self._vm.set_target_from_selection()
        # 同步到 UI
        if self._tgt_field:
            self._tgt_field.model.set_value(self._vm.target_root)

    def _on_primvar_changed(self, model) -> None:
        """Primvar 名称变化处理。"""
        self._vm.primvar_name = model.get_value_as_string()

    def _on_browse_clicked(self) -> None:
        """浏览按钮点击，打开文件选择对话框。"""
        try:
            base_dir = self._vm.get_stage_base_dir()
            default_name = "final_hair.usda"

            def _apply(filename, dirname):
                try:
                    if not filename.lower().endswith((".usda", ".usd", ".usdc")):
                        filename += ".usda"
                    path = f"{dirname}/{filename}".replace("\\", "/")
                    self._vm.set_output_path(path)
                    if self._out_field:
                        self._out_field.model.set_value(path)
                finally:
                    self._close_picker()

            # 尝试使用 FilePickerDialog
            try:
                from omni.kit.window.filepicker import FilePickerDialog
                self._picker = FilePickerDialog(
                    "Save Final USD",
                    click_apply_handler=_apply,
                    apply_button_label="Save",
                    enable_directory_change=True,
                    starting_path=base_dir,
                    default_filename=default_name,
                    file_extension_options=[
                        ("USD ASCII (.usda)", ".usda"),
                        ("USD Binary (.usd)", ".usd"),
                        ("USD Crate (.usdc)", ".usdc"),
                    ],
                )
                return
            except ImportError:
                self._picker = None

            # 回退到简单文件对话框
            try:
                import omni.kit.window.file as file_dlg
                dlg = file_dlg.FileDialog(
                    title="Save Final USD",
                    allow_multi_selection=False,
                    apply_button_label="Save"
                )
                dlg.show(lambda path: self._on_file_selected(path))
            except Exception as e:
                self._vm.log(f"File dialog unavailable, please type path manually. ({e})")

        except Exception as e:
            self._vm.log(f"Browse error: {e}")

    def _close_picker(self) -> None:
        """关闭文件选择器。"""
        if self._picker:
            try:
                self._picker.hide()
            except Exception:
                pass
            try:
                self._picker.destroy()
            except Exception:
                pass
            self._picker = None

    def _on_file_selected(self, path: str) -> None:
        """文件选择完成处理。"""
        path = path.replace("\\", "/")
        self._vm.set_output_path(path)
        if self._out_field:
            self._out_field.model.set_value(path)

    def _on_bake_clicked(self) -> None:
        """烘焙按钮点击。"""
        # 获取输出路径
        if self._out_field:
            self._vm.output_path = self._out_field.model.get_value_as_string()

        # 执行烘焙
        self._vm.run_bake()

    def _on_bake_standalone_clicked(self) -> None:
        """独立烘焙按钮点击。"""
        # 获取输出路径
        if self._out_field:
            self._vm.output_path = self._out_field.model.get_value_as_string()

        # 执行独立烘焙
        self._vm.run_bake_standalone()

    def _on_add_pair_clicked(self) -> None:
        """添加对到列表按钮点击。"""
        self._vm.add_current_pair()

    def _on_clear_pairs_clicked(self) -> None:
        """清空列表按钮点击。"""
        self._vm.clear_pairs_list()

    def _on_batch_bake_clicked(self) -> None:
        """批量烘焙按钮点击。"""
        # 获取输出路径
        if self._out_field:
            self._vm.output_path = self._out_field.model.get_value_as_string()

        # 执行批量烘焙
        success, fail, errors = self._vm.run_batch_bake(standalone=False)
        if errors:
            for err in errors:
                self._vm.log(f"Error: {err}")

    def _on_batch_bake_standalone_clicked(self) -> None:
        """批量独立烘焙按钮点击。"""
        # 获取输出路径
        if self._out_field:
            self._vm.output_path = self._out_field.model.get_value_as_string()

        # 执行批量独立烘焙
        success, fail, errors = self._vm.run_batch_bake(standalone=True)
        if errors:
            for err in errors:
                self._vm.log(f"Error: {err}")

    # =========================================================================
    # 数据刷新
    # =========================================================================

    def _refresh_display(self) -> None:
        """刷新显示数据。"""
        if self._src_label:
            self._src_label.text = self._vm.source_curve

        if self._tgt_field:
            self._tgt_field.model.set_value(self._vm.target_root)

        if self._out_field:
            self._out_field.model.set_value(self._vm.output_path)

        # 更新批量处理列表显示
        if self._pairs_count_label:
            count = self._vm.pairs_count
            self._pairs_count_label.text = str(count)
            if count > 0:
                self._pairs_count_label.style = {"color": Colors.SUCCESS}
            else:
                self._pairs_count_label.style = {"color": Colors.WARNING}

        if self._pairs_list_field:
            display_list = self._vm.get_pairs_display_list()
            if display_list:
                self._pairs_list_field.model.set_value("\n".join(display_list))
            else:
                self._pairs_list_field.model.set_value("(empty)")

    # =========================================================================
    # 生命周期
    # =========================================================================

    def dispose(self) -> None:
        """清理资源。"""
        self._vm.remove_data_changed_callback(self._refresh_display)
        self._close_picker()
        self._src_label = None
        self._tgt_field = None
        self._pv_field = None
        self._out_field = None
        self._pairs_list_field = None
        self._pairs_count_label = None
        super().dispose()
