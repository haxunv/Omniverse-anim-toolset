# -*- coding: utf-8 -*-
"""
AI Camera View
==============

AI 镜头生成功能的用户界面。
"""

import omni.ui as ui

from .base_view import BaseView
from .styles import Styles, Sizes, Colors
from ..viewmodels.ai_camera_vm import AICameraViewModel


class AICameraView(BaseView):
    """
    AI 镜头生成的视图
    
    提供自然语言描述输入、AI 生成、相机创建的界面。
    """
    
    def __init__(self, viewmodel: AICameraViewModel):
        super().__init__(viewmodel)
        self._vm: AICameraViewModel = viewmodel
        
        # UI components
        self._prompt_field = None
        self._prompt_display = None
        self._target_label = None
        self._size_label = None  # Show detected object size
        self._status_label = None
        self._params_field = None
        self._camera_label = None
        self._generate_btn = None
        
        # 绑定数据变更
        self._vm.add_data_changed_callback(self._refresh_display)
    
    def build(self) -> None:
        """构建 UI"""
        with ui.VStack(spacing=Sizes.SPACING_MEDIUM):
            self._build_header()
            ui.Separator(height=2)
            self._build_ai_status()
            self._build_target_section()
            self._build_prompt_section()
            self._build_presets_section()
            ui.Separator(height=2)
            self._build_action_section()
            self._build_result_section()
            self._create_log_section()
    
    # =========================================================================
    # UI 构建
    # =========================================================================
    
    def _build_header(self) -> None:
        """构建标题"""
        ui.Label(
            "🎬 AI Camera Shot Generator",
            style={"font_size": 16, "color": Colors.TEXT_PRIMARY}
        )
        ui.Label(
            "Describe your shot in natural language, AI will generate camera animation",
            style={"color": Colors.TEXT_SECONDARY}
        )
    
    def _build_ai_status(self) -> None:
        """构建 AI 状态显示"""
        with ui.HStack(height=24):
            ui.Label("AI Backend:", width=80)
            self._status_label = ui.Label(
                self._vm.ai_backend,
                style={"color": Colors.SUCCESS if self._vm.is_ai_available else Colors.ERROR}
            )
    
    def _build_target_section(self) -> None:
        """Build target selection section"""
        with ui.CollapsableFrame("Target Object", collapsed=False):
            with ui.VStack(spacing=Sizes.SPACING_SMALL):
                ui.Label(
                    "Select the object for camera to orbit around:",
                    style={"color": Colors.TEXT_SECONDARY}
                )
                
                with ui.HStack(height=24):
                    ui.Label("Target:", width=60)
                    self._target_label = ui.Label(
                        self._vm.target_path or "Not Set",
                        word_wrap=True,
                        style={"color": Colors.WARNING if not self._vm.target_path else Colors.SUCCESS}
                    )
                
                with ui.HStack(height=24):
                    ui.Label("Size:", width=60)
                    self._size_label = ui.Label(
                        f"{self._vm.target_size:.2f} units" if self._vm.target_path else "N/A",
                        style={"color": Colors.TEXT_SECONDARY}
                    )
                
                ui.Button(
                    "Set Target from Selection",
                    height=Sizes.BUTTON_HEIGHT,
                    clicked_fn=self._on_set_target_clicked
                )
    
    def _build_prompt_section(self) -> None:
        """Build prompt input section"""
        with ui.CollapsableFrame("Shot Description", collapsed=False):
            with ui.VStack(spacing=Sizes.SPACING_SMALL):
                ui.Label(
                    "Describe your shot in natural language:",
                    style={"color": Colors.TEXT_SECONDARY}
                )
                
                # Input field
                self._prompt_field = ui.StringField(
                    multiline=True,
                    height=80
                )
                self._prompt_field.model.set_value(self._vm.prompt)
                self._prompt_field.model.add_value_changed_fn(self._on_prompt_changed)
                
                # Helper buttons
                with ui.HStack(spacing=4, height=28):
                    ui.Button(
                        "Open Input Dialog",
                        clicked_fn=self._on_open_input_dialog,
                        tooltip="Open system input dialog"
                    )
                    ui.Button(
                        "Paste",
                        clicked_fn=self._on_paste_clicked,
                        tooltip="Paste from clipboard"
                    )
                    ui.Button(
                        "Clear",
                        width=50,
                        clicked_fn=self._on_clear_prompt_clicked
                    )
                
                # Current input display
                with ui.HStack(height=24):
                    ui.Label("Current:", width=60, style={"color": Colors.TEXT_SECONDARY})
                    self._prompt_display = ui.Label(
                        self._vm.prompt or "(empty)",
                        word_wrap=True,
                        style={"color": Colors.SUCCESS if self._vm.prompt else Colors.TEXT_SECONDARY}
                    )
                
                # Examples
                ui.Label(
                    "Examples: 'epic orbit shot' | 'dolly in close-up' | 'crane up reveal'",
                    style={"color": Colors.TEXT_SECONDARY, "font_size": 11}
                )
    
    def _build_presets_section(self) -> None:
        """Build presets section"""
        with ui.CollapsableFrame("Quick Presets (Click to Use)", collapsed=False):
            with ui.VStack(spacing=Sizes.SPACING_SMALL):
                ui.Label(
                    "Click a preset to use (no typing needed):",
                    style={"color": Colors.TEXT_SECONDARY}
                )
                
                presets = self._vm.get_preset_names()
                
                # Row 1: Orbit shots
                ui.Label("Orbit Shots:", style={"color": Colors.TEXT_SECONDARY, "font_size": 11})
                with ui.HStack(spacing=4):
                    for preset_id, preset_name in presets[:4]:
                        ui.Button(
                            preset_name,
                            height=26,
                            clicked_fn=lambda pid=preset_id: self._on_preset_clicked(pid)
                        )
                
                # Row 2: Dolly shots
                ui.Label("Dolly Shots:", style={"color": Colors.TEXT_SECONDARY, "font_size": 11})
                with ui.HStack(spacing=4):
                    for preset_id, preset_name in presets[4:7]:
                        ui.Button(
                            preset_name,
                            height=26,
                            clicked_fn=lambda pid=preset_id: self._on_preset_clicked(pid)
                        )
                
                # Row 3: Crane & Other
                ui.Label("Crane & Other:", style={"color": Colors.TEXT_SECONDARY, "font_size": 11})
                with ui.HStack(spacing=4):
                    for preset_id, preset_name in presets[7:]:
                        ui.Button(
                            preset_name,
                            height=26,
                            clicked_fn=lambda pid=preset_id: self._on_preset_clicked(pid)
                        )
    
    def _build_action_section(self) -> None:
        """构建操作按钮区域"""
        with ui.CollapsableFrame("Generate", collapsed=False):
            with ui.VStack(spacing=Sizes.SPACING_SMALL):
                # 一键生成按钮
                self._generate_btn = ui.Button(
                    "🚀 Generate Camera Animation",
                    height=Sizes.BUTTON_HEIGHT_LARGE,
                    style=Styles.BUTTON_SUCCESS,
                    clicked_fn=self._on_generate_clicked
                )
                
                # 分步按钮
                with ui.HStack(spacing=Sizes.SPACING_SMALL):
                    ui.Button(
                        "1. Generate Params",
                        height=Sizes.BUTTON_HEIGHT,
                        clicked_fn=self._on_generate_params_clicked,
                        tooltip="Only generate JSON params"
                    )
                    ui.Button(
                        "2. Create Camera",
                        height=Sizes.BUTTON_HEIGHT,
                        clicked_fn=self._on_create_camera_clicked,
                        tooltip="Create camera with generated params"
                    )
                
                # 清除按钮
                ui.Button(
                    "Clear All",
                    height=Sizes.BUTTON_HEIGHT,
                    clicked_fn=self._on_clear_clicked
                )
    
    def _build_result_section(self) -> None:
        """构建结果显示区域"""
        with ui.CollapsableFrame("Result & Playback", collapsed=False):
            with ui.VStack(spacing=Sizes.SPACING_SMALL):
                # 相机路径显示
                with ui.HStack(height=24):
                    ui.Label("Created Camera:", width=100)
                    self._camera_label = ui.Label(
                        "None",
                        style={"color": Colors.TEXT_SECONDARY}
                    )
                
                # 播放控制按钮
                ui.Label("Playback Controls:", style={"color": Colors.TEXT_SECONDARY})
                with ui.HStack(spacing=4, height=32):
                    ui.Button(
                        "📷 Activate Camera",
                        clicked_fn=self._on_activate_camera,
                        tooltip="Set generated camera as active viewport camera"
                    )
                    ui.Button(
                        "▶ Play",
                        width=60,
                        clicked_fn=self._on_play,
                        tooltip="Play animation"
                    )
                    ui.Button(
                        "⏸ Pause",
                        width=60,
                        clicked_fn=self._on_pause,
                        tooltip="Pause animation"
                    )
                    ui.Button(
                        "⏹ Stop",
                        width=60,
                        clicked_fn=self._on_stop,
                        tooltip="Stop and reset"
                    )
                
                ui.Separator(height=4)
                
                # 参数 JSON 显示
                ui.Label("Generated Parameters:", style={"color": Colors.TEXT_SECONDARY})
                self._params_field = ui.StringField(
                    multiline=True,
                    height=120,
                    read_only=True
                )
    
    # =========================================================================
    # 事件处理
    # =========================================================================
    
    def _on_set_target_clicked(self) -> None:
        """设置目标点击"""
        self._vm.set_target_from_selection()
    
    def _on_prompt_changed(self, model) -> None:
        """描述输入变化"""
        self._vm.prompt = model.get_value_as_string()
    
    def _on_paste_clicked(self) -> None:
        """从剪贴板粘贴"""
        try:
            import subprocess
            # Windows: 使用 PowerShell 获取剪贴板内容
            result = subprocess.run(
                ["powershell", "-command", "Get-Clipboard"],
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
            if result.returncode == 0:
                text = result.stdout.strip()
                if text:
                    self._vm.prompt = text
                    if self._prompt_field:
                        self._prompt_field.model.set_value(text)
                    self._vm.log(f"✓ Pasted: {text[:50]}...")
                else:
                    self._vm.log("⚠ Clipboard is empty")
            else:
                self._vm.log("⚠ Failed to read clipboard")
        except Exception as e:
            self._vm.log(f"⚠ Paste error: {e}")
    
    def _on_clear_prompt_clicked(self) -> None:
        """清空输入框"""
        self._vm.prompt = ""
        if self._prompt_field:
            self._prompt_field.model.set_value("")
    
    def _on_open_input_dialog(self) -> None:
        """Open system input dialog"""
        import threading
        
        def show_dialog():
            try:
                import tkinter as tk
                from tkinter import simpledialog
                
                # Create hidden root window
                root = tk.Tk()
                root.withdraw()
                root.attributes('-topmost', True)
                
                # Set initial value
                initial_value = self._vm.prompt or ""
                
                # Show input dialog
                result = simpledialog.askstring(
                    "Shot Description",
                    "Enter your shot description:",
                    initialvalue=initial_value,
                    parent=root
                )
                
                root.destroy()
                
                if result is not None:
                    # Use async callback to update UI
                    import omni.kit.app
                    async def update_ui():
                        self._vm.prompt = result
                        if self._prompt_field:
                            self._prompt_field.model.set_value(result)
                        self._vm.log(f"Input set: {result[:50]}...")
                        self._refresh_display()
                    
                    omni.kit.app.get_app().run_coroutine(update_ui())
                    
            except ImportError:
                self._vm.log("tkinter not available, use clipboard method")
            except Exception as e:
                self._vm.log(f"Dialog error: {e}")
        
        # Run in new thread to avoid blocking UI
        thread = threading.Thread(target=show_dialog)
        thread.start()
    
    def _on_preset_clicked(self, preset_id: str) -> None:
        """预设点击"""
        self._vm.apply_preset(preset_id)
        # 更新输入框
        if self._prompt_field:
            self._prompt_field.model.set_value(self._vm.prompt)
    
    def _on_generate_clicked(self) -> None:
        """一键生成点击"""
        self._vm.generate_and_create()
    
    def _on_generate_params_clicked(self) -> None:
        """生成参数点击"""
        self._vm.generate_shot_params()
    
    def _on_create_camera_clicked(self) -> None:
        """创建相机点击"""
        self._vm.create_camera()
    
    def _on_clear_clicked(self) -> None:
        """清除点击"""
        self._vm.clear()
        if self._prompt_field:
            self._prompt_field.model.set_value("")
    
    def _on_activate_camera(self) -> None:
        """激活相机"""
        self._vm.activate_camera()
    
    def _on_play(self) -> None:
        """播放动画"""
        self._vm.play_animation()
    
    def _on_pause(self) -> None:
        """暂停动画"""
        self._vm.pause_animation()
    
    def _on_stop(self) -> None:
        """停止动画"""
        self._vm.stop_animation()
    
    # =========================================================================
    # 数据刷新
    # =========================================================================
    
    def _refresh_display(self) -> None:
        """Refresh display"""
        # Update target display
        if self._target_label:
            target = self._vm.target_path
            if target:
                # Show just the last part of the path
                short_path = target.split("/")[-1] if "/" in target else target
                self._target_label.text = short_path
                self._target_label.style = {"color": Colors.SUCCESS}
            else:
                self._target_label.text = "Not Set"
                self._target_label.style = {"color": Colors.WARNING}
        
        # Update size display
        if self._size_label:
            if self._vm.target_path:
                size = self._vm.target_size
                self._size_label.text = f"{size:.2f} units"
                # Warn if size seems unusual
                if size > 50:
                    self._size_label.style = {"color": Colors.WARNING}
                else:
                    self._size_label.style = {"color": Colors.SUCCESS}
            else:
                self._size_label.text = "N/A"
                self._size_label.style = {"color": Colors.TEXT_SECONDARY}
        
        # 更新 AI 状态
        if self._status_label:
            self._status_label.text = self._vm.ai_backend
            self._status_label.style = {
                "color": Colors.SUCCESS if self._vm.is_ai_available else Colors.ERROR
            }
        
        # 更新当前输入显示
        if self._prompt_display:
            prompt = self._vm.prompt
            if prompt:
                # 截断显示
                display_text = prompt if len(prompt) <= 100 else prompt[:100] + "..."
                self._prompt_display.text = display_text
                self._prompt_display.style = {"color": Colors.SUCCESS}
            else:
                self._prompt_display.text = "(empty)"
                self._prompt_display.style = {"color": Colors.TEXT_SECONDARY}
        
        # 更新生成的参数
        if self._params_field:
            params = self._vm.generated_params
            if params:
                import json
                self._params_field.model.set_value(
                    json.dumps(params, indent=2, ensure_ascii=False)
                )
            else:
                self._params_field.model.set_value("")
        
        # 更新相机路径
        if self._camera_label:
            camera = self._vm.last_camera_path
            if camera:
                self._camera_label.text = camera
                self._camera_label.style = {"color": Colors.SUCCESS}
            else:
                self._camera_label.text = "None"
                self._camera_label.style = {"color": Colors.TEXT_SECONDARY}
        
        # 更新生成按钮状态
        if self._generate_btn:
            if self._vm.is_generating:
                self._generate_btn.text = "⏳ Generating..."
                self._generate_btn.enabled = False
            else:
                self._generate_btn.text = "🚀 Generate Camera Animation"
                self._generate_btn.enabled = True
    
    # =========================================================================
    # 生命周期
    # =========================================================================
    
    def dispose(self) -> None:
        """Clean up resources"""
        self._vm.remove_data_changed_callback(self._refresh_display)
        self._prompt_field = None
        self._prompt_display = None
        self._target_label = None
        self._size_label = None
        self._status_label = None
        self._params_field = None
        self._camera_label = None
        self._generate_btn = None
        super().dispose()

