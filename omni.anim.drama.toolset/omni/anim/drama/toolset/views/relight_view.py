# -*- coding: utf-8 -*-
"""
Relight View
============

AI Relight view for animation relighting.

Provides UI for:
    - Gemini API configuration (for analysis)
    - Image Generation API configuration (for relit image generation)
    - Image selection (original/relit)
    - Relit image generation
    - Analysis control
    - Operation preview and execution
"""

import os
from typing import Optional, Dict, Any
import omni.ui as ui

from .base_view import BaseView
from .styles import Styles, Sizes, Colors
from ..viewmodels.relight_vm import RelightViewModel


class RelightView(BaseView):
    """
    Relight view.
    """

    def __init__(self, viewmodel: RelightViewModel):
        """
        Initialize view.

        Args:
            viewmodel: RelightViewModel instance
        """
        super().__init__(viewmodel)
        self._vm: RelightViewModel = viewmodel

        # UI component references - Gemini API
        self._api_key_field: Optional[ui.StringField] = None
        self._model_field: Optional[ui.StringField] = None
        self._base_url_field: Optional[ui.StringField] = None
        self._connection_status_label: Optional[ui.Label] = None
        
        # UI component references - Image Generation API
        self._img_api_key_field: Optional[ui.StringField] = None
        self._img_model_field: Optional[ui.StringField] = None
        self._img_base_url_field: Optional[ui.StringField] = None
        self._img_connection_status_label: Optional[ui.Label] = None
        
        # UI component references - Image Generation
        self._lighting_desc_field: Optional[ui.StringField] = None
        self._generate_button: Optional[ui.Button] = None
        
        # UI component references - Images
        self._original_path_label: Optional[ui.Label] = None
        self._relit_path_label: Optional[ui.Label] = None
        
        # UI component references - Analysis
        self._analyze_button: Optional[ui.Button] = None
        self._execute_button: Optional[ui.Button] = None
        self._operations_preview: Optional[ui.StringField] = None
        self._reasoning_label: Optional[ui.Label] = None
        self._custom_prompt_field: Optional[ui.StringField] = None

        # Bind ViewModel callbacks
        self._vm.add_images_changed_callback(self._on_images_changed)
        self._vm.add_analysis_complete_callback(self._on_analysis_complete)
        self._vm.add_connection_status_callback(self._on_connection_status_changed)
        self._vm.add_img_connection_status_callback(self._on_img_connection_status_changed)
        self._vm.add_image_generation_callback(self._on_image_generation_complete)

    def build(self) -> None:
        """Build UI."""
        with ui.VStack(spacing=Sizes.SPACING_MEDIUM):
            # API config sections in collapsable frames
            with ui.CollapsableFrame("Gemini API (Analysis)", collapsed=False):
                self._build_gemini_api_section()

            with ui.CollapsableFrame("Relight Image Generation API", collapsed=True):
                self._build_img_gen_api_section()

            ui.Separator(height=8)

            # Image selection section
            self._build_image_section()

            ui.Separator(height=8)

            # Analysis control section
            self._build_analysis_section()

            ui.Separator(height=8)

            # Operations preview section
            self._build_operations_section()

            # Log section
            self._create_log_section(height=100)

    # =========================================================================
    # Gemini API Config (Analysis)
    # =========================================================================

    def _build_gemini_api_section(self) -> None:
        """Build Gemini API configuration section."""
        with ui.VStack(spacing=Sizes.SPACING_SMALL):
            # API Key
            with ui.HStack(height=26):
                ui.Label("API Key:", width=80)
                self._api_key_field = ui.StringField(
                    password_mode=True,
                    tooltip="Enter Gemini API Key"
                )
                if self._vm.saved_api_key:
                    self._api_key_field.model.set_value(self._vm.saved_api_key)
                self._api_key_field.model.add_value_changed_fn(
                    lambda m: self._vm.set_api_key(m.get_value_as_string())
                )

            # Model selection
            with ui.HStack(height=26):
                ui.Label("Model:", width=80)
                self._model_field = ui.StringField()
                self._model_field.model.set_value(self._vm.saved_model or "gemini-2.0-flash")
                self._model_field.model.add_value_changed_fn(
                    lambda m: self._vm.set_model(m.get_value_as_string())
                )

            # Custom API URL (optional)
            with ui.HStack(height=26):
                ui.Label("API URL:", width=80)
                self._base_url_field = ui.StringField(
                    tooltip="Optional, for proxy or custom endpoint"
                )
                if self._vm.saved_base_url:
                    self._base_url_field.model.set_value(self._vm.saved_base_url)
                self._base_url_field.model.add_value_changed_fn(
                    lambda m: self._vm.set_base_url(m.get_value_as_string())
                )

            # Test connection button and status
            with ui.HStack(height=26):
                ui.Spacer(width=80)
                ui.Button(
                    "Test Connection",
                    clicked_fn=self._on_test_connection,
                    width=120,
                    tooltip="Test Gemini API connection"
                )

            with ui.HStack(height=22):
                ui.Spacer(width=80)
                self._connection_status_label = ui.Label(
                    "",
                    word_wrap=True,
                    style={"color": Colors.TEXT_SECONDARY}
                )

    # =========================================================================
    # Image Generation API Config
    # =========================================================================

    def _build_img_gen_api_section(self) -> None:
        """Build Image Generation API configuration section."""
        with ui.VStack(spacing=Sizes.SPACING_SMALL):
            # Info label
            ui.Label("Use same API Key as above, or enter a different one", style=Styles.LABEL_SECONDARY)
            
            # API Key
            with ui.HStack(height=26):
                ui.Label("API Key:", width=80)
                self._img_api_key_field = ui.StringField(
                    password_mode=True,
                    tooltip="Enter API Key (GPTSapi or Gemini)"
                )
                if self._vm.saved_img_api_key:
                    self._img_api_key_field.model.set_value(self._vm.saved_img_api_key)
                self._img_api_key_field.model.add_value_changed_fn(
                    lambda m: self._vm.set_img_api_key(m.get_value_as_string())
                )

            # Model selection
            with ui.HStack(height=26):
                ui.Label("Model:", width=80)
                self._img_model_field = ui.StringField(
                    tooltip="e.g. gemini-3-pro-image-preview"
                )
                self._img_model_field.model.set_value(self._vm.saved_img_model or "gemini-3-pro-image-preview")
                self._img_model_field.model.add_value_changed_fn(
                    lambda m: self._vm.set_img_model(m.get_value_as_string())
                )

            # Custom API URL (optional)
            with ui.HStack(height=26):
                ui.Label("API URL:", width=80)
                self._img_base_url_field = ui.StringField(
                    tooltip="Default: https://api.gptsapi.net"
                )
                if self._vm.saved_img_base_url:
                    self._img_base_url_field.model.set_value(self._vm.saved_img_base_url)
                self._img_base_url_field.model.add_value_changed_fn(
                    lambda m: self._vm.set_img_base_url(m.get_value_as_string())
                )

            # Test connection button and status
            with ui.HStack(height=26):
                ui.Spacer(width=80)
                ui.Button(
                    "Test Connection",
                    clicked_fn=self._on_test_img_connection,
                    width=120,
                    tooltip="Test API connection"
                )

            with ui.HStack(height=22):
                ui.Spacer(width=80)
                self._img_connection_status_label = ui.Label(
                    "",
                    word_wrap=True,
                    style={"color": Colors.TEXT_SECONDARY}
                )

    # =========================================================================
    # Image Selection
    # =========================================================================

    def _build_image_section(self) -> None:
        """Build image selection section."""
        ui.Label("Images", style=Styles.LABEL_HEADER)

        with ui.VStack(spacing=Sizes.SPACING_SMALL):
            # Original image
            ui.Label("Original Render:", style=Styles.LABEL_SECONDARY)
            
            with ui.HStack(height=22):
                self._original_path_label = ui.Label(
                    "Not selected",
                    word_wrap=True,
                    style={"color": Colors.TEXT_SECONDARY}
                )

            with ui.HStack(height=26, spacing=4):
                ui.Button(
                    "Capture Viewport",
                    clicked_fn=self._on_capture_original,
                    tooltip="Capture current viewport as original image"
                )
                ui.Button(
                    "Select File...",
                    clicked_fn=self._on_select_original,
                    tooltip="Select original image from file"
                )

            ui.Separator(height=8)

            # Relit image generation section
            ui.Label("Generate Relit Reference:", style=Styles.LABEL_SECONDARY)
            
            self._lighting_desc_field = ui.StringField(
                multiline=True,
                height=50,
                tooltip="Describe the desired lighting effect.\nExample: 'warm sunset lighting from left', 'cool blue rim light', 'dramatic top light with dark shadows'"
            )
            self._lighting_desc_field.model.set_value("")

            with ui.HStack(height=30, spacing=4):
                self._generate_button = ui.Button(
                    "Generate Relit Image",
                    clicked_fn=self._on_generate_relit,
                    style={"background_color": 0xFF6B5B95},
                    tooltip="Generate relit reference image using AI"
                )

            ui.Separator(height=8)

            # Relit image (manual selection or generated)
            ui.Label("Relit Target Image:", style=Styles.LABEL_SECONDARY)
            
            with ui.HStack(height=22):
                self._relit_path_label = ui.Label(
                    "Not selected",
                    word_wrap=True,
                    style={"color": Colors.TEXT_SECONDARY}
                )

            with ui.HStack(height=26):
                ui.Button(
                    "Select File...",
                    clicked_fn=self._on_select_relit,
                    tooltip="Select relit target image from file"
                )
                ui.Spacer(width=8)
                ui.Button(
                    "Clear All",
                    clicked_fn=self._on_clear_images,
                    tooltip="Clear all selected images"
                )

    # =========================================================================
    # Analysis Control
    # =========================================================================

    def _build_analysis_section(self) -> None:
        """Build analysis control section."""
        ui.Label("Analysis", style=Styles.LABEL_HEADER)

        with ui.VStack(spacing=Sizes.SPACING_SMALL):
            # Custom prompt for fine-tuning
            ui.Label("Custom Prompt (Optional):", style=Styles.LABEL_SECONDARY)
            self._custom_prompt_field = ui.StringField(
                multiline=True,
                height=60,
                tooltip="Add custom instructions to fine-tune the analysis.\nExample: 'Make shadows darker', 'Use warmer colors', 'Focus on rim lighting'"
            )
            self._custom_prompt_field.model.set_value("")
            
            ui.Spacer(height=4)

            # Scene info preview
            with ui.CollapsableFrame("Scene Info Preview", collapsed=True):
                with ui.VStack():
                    scene_info = ui.StringField(
                        multiline=True,
                        height=100,
                        read_only=True
                    )
                    ui.Button(
                        "Refresh Scene Info",
                        clicked_fn=lambda: scene_info.model.set_value(
                            self._vm.get_scene_info()
                        )
                    )

            # Analyze button
            with ui.HStack(height=40, spacing=8):
                self._analyze_button = ui.Button(
                    "Start Analysis",
                    clicked_fn=self._on_analyze,
                    style={"background_color": Colors.PRIMARY},
                    tooltip="Analyze lighting difference between two images"
                )

    # =========================================================================
    # Operations Preview
    # =========================================================================

    def _build_operations_section(self) -> None:
        """Build operations preview section."""
        ui.Label("Light Operations", style=Styles.LABEL_HEADER)

        with ui.VStack(spacing=Sizes.SPACING_SMALL):
            # Reasoning
            ui.Label("AI Analysis:", style=Styles.LABEL_SECONDARY)
            self._reasoning_label = ui.Label(
                "Waiting for analysis...",
                word_wrap=True,
                style={"color": Colors.TEXT_SECONDARY}
            )

            ui.Spacer(height=4)

            # Operations preview
            ui.Label("Pending Operations:", style=Styles.LABEL_SECONDARY)
            self._operations_preview = ui.StringField(
                multiline=True,
                height=120,
                read_only=True
            )
            self._operations_preview.model.set_value("Waiting for analysis result...")

            # Execute buttons
            with ui.HStack(height=40, spacing=8):
                self._execute_button = ui.Button(
                    "Execute Light Operations",
                    clicked_fn=self._on_execute,
                    style={"background_color": 0xFF228B22},
                    enabled=False,
                    tooltip="Execute light adjustments in scene"
                )
                ui.Button(
                    "Clear",
                    clicked_fn=self._on_clear_operations,
                    width=80,
                    tooltip="Clear pending operations"
                )

    # =========================================================================
    # Event Handlers
    # =========================================================================

    def _on_test_connection(self) -> None:
        """Test connection button clicked."""
        # Show testing status
        if self._connection_status_label:
            self._connection_status_label.text = "Testing..."
            self._connection_status_label.style = {"color": Colors.TEXT_SECONDARY}
        self._vm.test_connection()

    def _on_connection_status_changed(self, success: bool, message: str) -> None:
        """Connection status changed callback."""
        if self._connection_status_label:
            if success:
                self._connection_status_label.text = f"✓ {message}"
                self._connection_status_label.style = {"color": 0xFF00AA00}  # Green
            else:
                self._connection_status_label.text = f"✗ {message}"
                self._connection_status_label.style = {"color": 0xFFFF4444}  # Red

    def _on_test_img_connection(self) -> None:
        """Test Image Gen connection button clicked."""
        if self._img_connection_status_label:
            self._img_connection_status_label.text = "Testing..."
            self._img_connection_status_label.style = {"color": Colors.TEXT_SECONDARY}
        self._vm.test_img_connection()

    def _on_img_connection_status_changed(self, success: bool, message: str) -> None:
        """Image Gen connection status changed callback."""
        if self._img_connection_status_label:
            if success:
                self._img_connection_status_label.text = f"✓ {message}"
                self._img_connection_status_label.style = {"color": 0xFF00AA00}  # Green
            else:
                self._img_connection_status_label.text = f"✗ {message}"
                self._img_connection_status_label.style = {"color": 0xFFFF4444}  # Red

    def _on_generate_relit(self) -> None:
        """Generate relit image button clicked."""
        if self._vm.is_generating_image:
            return
        
        # Get lighting description
        lighting_desc = ""
        if self._lighting_desc_field:
            lighting_desc = self._lighting_desc_field.model.get_value_as_string().strip()
        
        if not lighting_desc:
            return
        
        # Disable button and show progress
        if self._generate_button:
            self._generate_button.enabled = False
            self._generate_button.text = "Generating..."
        
        self._vm.generate_relit_image(lighting_desc)

    def _on_image_generation_complete(self, success: bool, message: str, path: Optional[str]) -> None:
        """Image generation complete callback."""
        # Restore generate button
        if self._generate_button:
            self._generate_button.enabled = True
            self._generate_button.text = "Generate Relit Image"

    def _on_capture_original(self) -> None:
        """Capture original image button clicked."""
        self._vm.capture_original_image()

    def _on_select_original(self) -> None:
        """Select original image file."""
        self._open_file_dialog(
            title="Select Original Render",
            callback=self._vm.set_original_image
        )

    def _on_select_relit(self) -> None:
        """Select relit image file."""
        self._open_file_dialog(
            title="Select Relit Target Image",
            callback=self._vm.set_relit_image
        )

    def _on_clear_images(self) -> None:
        """Clear images button clicked."""
        self._vm.clear_images()

    def _on_analyze(self) -> None:
        """Start analysis button clicked."""
        if self._vm.is_analyzing:
            return
        
        # Disable button
        if self._analyze_button:
            self._analyze_button.enabled = False
            self._analyze_button.text = "Analyzing..."

        # Get custom prompt if provided
        custom_prompt = ""
        if self._custom_prompt_field:
            custom_prompt = self._custom_prompt_field.model.get_value_as_string().strip()

        self._vm.analyze_relight(custom_prompt=custom_prompt if custom_prompt else None)

    def _on_execute(self) -> None:
        """Execute operations button clicked."""
        self._vm.execute_operations()
        self._update_operations_ui()

    def _on_clear_operations(self) -> None:
        """Clear operations button clicked."""
        self._vm.clear_pending_operations()
        self._update_operations_ui()

    # =========================================================================
    # File Dialog
    # =========================================================================

    def _open_file_dialog(self, title: str, callback) -> None:
        """
        Open file selection dialog.

        Args:
            title: Dialog title
            callback: Callback when file is selected
        """
        try:
            from omni.kit.window.filepicker import FilePickerDialog
            
            def on_click(filename: str, dirname: str):
                if filename:
                    full_path = os.path.join(dirname, filename)
                    callback(full_path)
                dialog.hide()

            def on_cancel(a, b):
                dialog.hide()

            dialog = FilePickerDialog(
                title,
                apply_button_label="Select",
                click_apply_handler=on_click,
                click_cancel_handler=on_cancel,
                file_extension_options=[
                    ("*.png", "PNG Image"),
                    ("*.jpg;*.jpeg", "JPEG Image"),
                    ("*.*", "All Files"),
                ]
            )
            dialog.show()

        except ImportError:
            # Fallback: use simple input dialog
            self._show_path_input_dialog(title, callback)

    def _show_path_input_dialog(self, title: str, callback) -> None:
        """Show simple path input dialog."""
        window = ui.Window(title, width=400, height=100)
        
        with window.frame:
            with ui.VStack(spacing=8, margin=10):
                ui.Label("Enter file path:")
                path_field = ui.StringField()
                
                with ui.HStack():
                    def on_ok():
                        path = path_field.model.get_value_as_string()
                        if path:
                            callback(path)
                        window.visible = False

                    ui.Button("OK", clicked_fn=on_ok)
                    ui.Button("Cancel", clicked_fn=lambda: setattr(window, 'visible', False))

    # =========================================================================
    # ViewModel Callbacks
    # =========================================================================

    def _on_images_changed(self) -> None:
        """Image changed callback."""
        # Update original image path display
        if self._original_path_label:
            path = self._vm.original_image_path
            if path:
                self._original_path_label.text = os.path.basename(path)
                self._original_path_label.tooltip = path
            else:
                self._original_path_label.text = "Not selected"

        # Update relit image path display
        if self._relit_path_label:
            path = self._vm.relit_image_path
            if path:
                self._relit_path_label.text = os.path.basename(path)
                self._relit_path_label.tooltip = path
            else:
                self._relit_path_label.text = "Not selected"

    def _on_analysis_complete(self, success: bool, result: Optional[Dict]) -> None:
        """Analysis complete callback."""
        # Restore analyze button
        if self._analyze_button:
            self._analyze_button.enabled = True
            self._analyze_button.text = "Start Analysis"

        if success and result:
            # Update reasoning
            if self._reasoning_label:
                reasoning = result.get("reasoning", "None")
                self._reasoning_label.text = reasoning if reasoning else "No detailed explanation"

        self._update_operations_ui()

    def _update_operations_ui(self) -> None:
        """Update operations UI."""
        # Update operations preview
        if self._operations_preview:
            preview = self._vm.preview_operations()
            self._operations_preview.model.set_value(preview)

        # Update execute button state
        if self._execute_button:
            self._execute_button.enabled = self._vm.has_pending_operations

    # =========================================================================
    # Lifecycle
    # =========================================================================

    def dispose(self) -> None:
        """Cleanup resources."""
        self._vm.remove_images_changed_callback(self._on_images_changed)
        self._vm.remove_analysis_complete_callback(self._on_analysis_complete)
        self._vm.remove_connection_status_callback(self._on_connection_status_changed)
        self._vm.remove_img_connection_status_callback(self._on_img_connection_status_changed)
        self._vm.remove_image_generation_callback(self._on_image_generation_complete)
        super().dispose()
