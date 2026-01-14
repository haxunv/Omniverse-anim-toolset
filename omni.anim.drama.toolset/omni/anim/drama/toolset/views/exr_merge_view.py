# -*- coding: utf-8 -*-
"""
EXR Merge View
==============

EXR AOV 合并功能的视图。
"""

from typing import Optional
import omni.ui as ui

from .base_view import BaseView
from .styles import Styles, Sizes, Colors
from ..viewmodels.exr_merge_vm import ExrMergeViewModel


class ExrMergeView(BaseView):
    """
    EXR Merge 视图。
    
    提供 EXR AOV 合并功能的用户界面。
    """
    
    def __init__(self, viewmodel: ExrMergeViewModel):
        """
        初始化视图。
        
        Args:
            viewmodel: ExrMergeViewModel 实例
        """
        super().__init__(viewmodel)
        self._vm: ExrMergeViewModel = viewmodel
        
        # UI Models
        self._src_model: Optional[ui.SimpleStringModel] = None
        self._out_model: Optional[ui.SimpleStringModel] = None
        self._shot_model: Optional[ui.SimpleStringModel] = None
        self._keep_model: Optional[ui.SimpleBoolModel] = None
        self._dtype_model: Optional[ui.SimpleStringModel] = None
        self._workers_model: Optional[ui.SimpleIntModel] = None
        self._scan_result_model: Optional[ui.SimpleStringModel] = None
    
    def build(self) -> None:
        """构建 UI。"""
        with ui.VStack(spacing=Sizes.SPACING_MEDIUM):
            # 标题
            ui.Label(
                "EXR AOV Auto-Merge",
                style=Styles.LABEL_HEADER,
                height=30
            )
            ui.Label(
                "Merge multiple AOV EXR files into multi-layer EXR",
                style=Styles.LABEL_SECONDARY
            )
            
            ui.Separator(height=8)
            
            # 依赖检查按钮
            with ui.HStack(height=30):
                ui.Button(
                    "Install / Check OpenEXR & Imath",
                    width=280,
                    clicked_fn=self._on_check_deps
                )
                ui.Spacer()
            
            ui.Separator(height=8)
            
            # 源文件夹
            self._src_model = ui.SimpleStringModel(self._vm.src_dir)
            with ui.HStack(height=26):
                ui.Label("Source folder:", width=Sizes.LABEL_WIDTH)
                ui.StringField(model=self._src_model)
                ui.Button(
                    "Browse",
                    width=80,
                    clicked_fn=lambda: self._pick_dir(self._src_model, "src")
                )
            
            # 输出文件夹
            self._out_model = ui.SimpleStringModel(self._vm.out_dir)
            with ui.HStack(height=26):
                ui.Label("Output folder:", width=Sizes.LABEL_WIDTH)
                ui.StringField(model=self._out_model)
                ui.Button(
                    "Browse",
                    width=80,
                    clicked_fn=lambda: self._pick_dir(self._out_model, "out")
                )
            
            # Shot code
            self._shot_model = ui.SimpleStringModel(self._vm.shot_name)
            with ui.HStack(height=26):
                ui.Label("Shot code:", width=Sizes.LABEL_WIDTH)
                ui.StringField(model=self._shot_model, width=220)
                ui.Spacer()
            
            # Keep singles checkbox
            self._keep_model = ui.SimpleBoolModel(self._vm.keep_singles)
            with ui.HStack(height=26):
                ui.Spacer(width=Sizes.LABEL_WIDTH)
                ui.CheckBox(model=self._keep_model, width=20)
                ui.Label("Keep AOV singles after merge", width=200)
                ui.Spacer()
            
            # Channel type & Workers
            self._dtype_model = ui.SimpleStringModel(self._vm.dtype)
            self._workers_model = ui.SimpleIntModel(self._vm.workers)
            with ui.HStack(height=26):
                ui.Label("Channel type:", width=Sizes.LABEL_WIDTH)
                ui.ComboBox(
                    0,
                    "HALF", "FLOAT",
                    width=100
                )
                ui.Spacer(width=20)
                ui.Label("Workers (0=auto):", width=120)
                ui.IntField(model=self._workers_model, width=80)
                ui.Spacer()
            
            ui.Separator(height=8)
            
            # 扫描按钮和结果
            self._scan_result_model = ui.SimpleStringModel("")
            with ui.HStack(height=26):
                ui.Button(
                    "Scan",
                    width=100,
                    clicked_fn=self._on_scan
                )
                ui.Spacer(width=10)
                ui.Button(
                    "Auto-Merge (External, Parallel)",
                    width=260,
                    clicked_fn=self._on_merge,
                    style=Styles.BUTTON_PRIMARY
                )
                ui.Spacer()
            
            # 扫描结果显示
            with ui.HStack(height=50):
                ui.Label("Scan result:", width=Sizes.LABEL_WIDTH)
                ui.StringField(
                    model=self._scan_result_model,
                    multiline=True,
                    read_only=True
                )
            
            # 日志区域
            self._create_log_section(height=200)
    
    def _pick_dir(self, model: ui.SimpleStringModel, target: str) -> None:
        """打开文件夹选择器。"""
        try:
            from omni.kit.window.filepicker import FilePickerDialog
        except ImportError:
            self._vm.log("FilePickerDialog not available.")
            return
        
        dlg_holder = {}
        
        def _assign_path(*args, **kwargs):
            path = None
            for a in args:
                if isinstance(a, str):
                    path = a
                elif isinstance(a, (list, tuple)) and a and isinstance(a[0], str):
                    path = a[0]
            if not path:
                path = kwargs.get('path') or kwargs.get('dirname') or kwargs.get('filename')
            if path:
                model.set_value(path)
                # 同步到 ViewModel
                if target == "src":
                    self._vm.src_dir = path
                elif target == "out":
                    self._vm.out_dir = path
            
            # 关闭对话框
            for a in args:
                try:
                    a.hide()
                    return
                except Exception:
                    pass
            try:
                dlg_holder['dlg'].hide()
            except Exception:
                pass
        
        dlg = FilePickerDialog(
            title="Choose Folder",
            click_apply_handler=_assign_path,
            select_folder=True,
            allow_multiple=False,
        )
        dlg_holder['dlg'] = dlg
        dlg.show()
    
    def _on_check_deps(self) -> None:
        """检查依赖。"""
        self._vm.check_dependencies()
    
    def _on_scan(self) -> None:
        """扫描源文件夹。"""
        # 同步 UI 值到 ViewModel
        self._sync_ui_to_vm()
        
        result = self._vm.scan_source()
        self._scan_result_model.set_value(result)
    
    def _on_merge(self) -> None:
        """执行合并。"""
        # 同步 UI 值到 ViewModel
        self._sync_ui_to_vm()
        
        self._vm.run_merge()
    
    def _sync_ui_to_vm(self) -> None:
        """将 UI 值同步到 ViewModel。"""
        if self._src_model:
            self._vm.src_dir = self._src_model.get_value_as_string()
        if self._out_model:
            self._vm.out_dir = self._out_model.get_value_as_string()
        if self._shot_model:
            self._vm.shot_name = self._shot_model.get_value_as_string()
        if self._keep_model:
            self._vm.keep_singles = self._keep_model.get_value_as_bool()
        if self._workers_model:
            self._vm.workers = self._workers_model.get_value_as_int()
        # dtype 从 ComboBox 获取比较复杂，暂时使用默认值
    
    def dispose(self) -> None:
        """清理资源。"""
        super().dispose()
        self._src_model = None
        self._out_model = None
        self._shot_model = None
        self._keep_model = None
        self._dtype_model = None
        self._workers_model = None
        self._scan_result_model = None

