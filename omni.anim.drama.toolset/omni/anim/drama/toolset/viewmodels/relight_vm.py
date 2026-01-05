# -*- coding: utf-8 -*-
"""
Relight ViewModel
=================

ViewModel for AI Relight functionality.

Features:
    - Capture viewport render
    - Import relit images
    - Call Gemini API for analysis
    - Execute light operations
    - Save/load API configuration
"""

import os
import base64
from typing import Optional, List, Dict, Any, Callable
from concurrent.futures import ThreadPoolExecutor

from .base_viewmodel import BaseViewModel
from ..ai import GeminiClient, LightPrimitiveParser
from ..core.scene_exporter import export_scene_info_for_llm
from ..core.render_capture import capture_viewport, read_image_as_base64
from ..core.light_control import (
    execute_light_operations,
    get_all_lights,
    get_lights_summary,
)


# Settings keys for persistent storage
SETTINGS_PREFIX = "/exts/omni.anim.drama.toolset/relight/"
SETTINGS_API_KEY = SETTINGS_PREFIX + "api_key"
SETTINGS_MODEL = SETTINGS_PREFIX + "model"
SETTINGS_BASE_URL = SETTINGS_PREFIX + "base_url"


class RelightViewModel(BaseViewModel):
    """
    Relight ViewModel.
    """

    def __init__(self):
        """Initialize ViewModel."""
        super().__init__()

        # Gemini client
        self._gemini_client: Optional[GeminiClient] = None
        
        # Image paths
        self._original_image_path: Optional[str] = None
        self._relit_image_path: Optional[str] = None
        
        # Analysis result
        self._last_analysis_result: Optional[Dict] = None
        self._pending_operations: List[Dict] = []
        
        # Configuration (will be loaded from settings)
        self._api_key: str = ""
        self._model: str = "gemini-2.0-flash"
        self._base_url: str = ""
        
        # State
        self._is_analyzing: bool = False
        
        # Thread pool
        self._executor = ThreadPoolExecutor(max_workers=2)
        
        # Change callbacks
        self._on_images_changed_callbacks: List[Callable] = []
        self._on_analysis_complete_callbacks: List[Callable] = []
        
        # Load saved configuration
        self._load_settings()

    # =========================================================================
    # Configuration
    # =========================================================================

    def set_api_key(self, api_key: str, save: bool = False) -> None:
        """Set API Key."""
        self._api_key = api_key
        if self._gemini_client:
            self._gemini_client.set_api_key(api_key)
        self.log(f"API Key set (length: {len(api_key)})")
        if save:
            self._save_settings()

    def set_model(self, model: str, save: bool = False) -> None:
        """Set model name."""
        self._model = model
        if self._gemini_client:
            self._gemini_client.set_model(model)
        self.log(f"Model set: {model}")
        if save:
            self._save_settings()

    def set_base_url(self, base_url: str, save: bool = False) -> None:
        """Set custom API URL."""
        self._base_url = base_url
        if self._gemini_client:
            self._gemini_client.set_base_url(base_url)
        if base_url:
            self.log(f"API URL set: {base_url}")
        if save:
            self._save_settings()

    # =========================================================================
    # Settings Persistence
    # =========================================================================

    def _get_settings(self):
        """Get carb settings interface."""
        try:
            import carb.settings
            return carb.settings.get_settings()
        except Exception:
            return None

    def _encode_key(self, key: str) -> str:
        """Simple encoding for API key (not secure, just obfuscation)."""
        if not key:
            return ""
        try:
            return base64.b64encode(key.encode()).decode()
        except Exception:
            return ""

    def _decode_key(self, encoded: str) -> str:
        """Decode API key."""
        if not encoded:
            return ""
        try:
            return base64.b64decode(encoded.encode()).decode()
        except Exception:
            return ""

    def _load_settings(self) -> None:
        """Load saved settings."""
        settings = self._get_settings()
        if not settings:
            return

        try:
            # Load API key (encoded)
            encoded_key = settings.get(SETTINGS_API_KEY)
            if encoded_key:
                self._api_key = self._decode_key(encoded_key)

            # Load model
            model = settings.get(SETTINGS_MODEL)
            if model:
                self._model = model

            # Load base URL
            base_url = settings.get(SETTINGS_BASE_URL)
            if base_url:
                self._base_url = base_url

            if self._api_key:
                self.log("Loaded saved API configuration")

        except Exception as e:
            self.log(f"Failed to load settings: {e}")

    def _save_settings(self) -> None:
        """Save current settings."""
        settings = self._get_settings()
        if not settings:
            return

        try:
            # Save API key (encoded)
            settings.set(SETTINGS_API_KEY, self._encode_key(self._api_key))
            
            # Save model
            settings.set(SETTINGS_MODEL, self._model)
            
            # Save base URL
            settings.set(SETTINGS_BASE_URL, self._base_url)

            self.log("API configuration saved")

        except Exception as e:
            self.log(f"Failed to save settings: {e}")

    def save_current_config(self) -> None:
        """Manually save current configuration."""
        self._save_settings()

    @property
    def saved_api_key(self) -> str:
        """Get saved API key."""
        return self._api_key

    @property
    def saved_model(self) -> str:
        """Get saved model."""
        return self._model

    @property
    def saved_base_url(self) -> str:
        """Get saved base URL."""
        return self._base_url

    def _get_or_create_client(self) -> GeminiClient:
        """Get or create Gemini client."""
        if not self._gemini_client:
            self._gemini_client = GeminiClient(
                api_key=self._api_key,
                model=self._model,
                base_url=self._base_url if self._base_url else None
            )
        return self._gemini_client

    @property
    def is_configured(self) -> bool:
        """Check if API is configured."""
        return bool(self._api_key)

    # =========================================================================
    # Image Management
    # =========================================================================

    @property
    def original_image_path(self) -> Optional[str]:
        """Get original image path."""
        return self._original_image_path

    @property
    def relit_image_path(self) -> Optional[str]:
        """Get relit image path."""
        return self._relit_image_path

    def capture_original_image(self, output_path: Optional[str] = None) -> bool:
        """
        Capture current viewport as original image.

        Args:
            output_path: Output path, auto-generated if None

        Returns:
            bool: Success
        """
        self.set_status("Capturing viewport...")
        
        success, msg, path = capture_viewport(output_path)
        
        if success and path:
            self._original_image_path = path
            self.log(f"Original image captured: {path}")
            self.set_status("Original image captured")
            self._notify_images_changed()
            return True
        else:
            self.log(f"Capture failed: {msg}")
            self.set_status("Capture failed")
            return False

    def set_original_image(self, path: str) -> bool:
        """
        Set original image path.

        Args:
            path: Image file path

        Returns:
            bool: Success
        """
        if not os.path.exists(path):
            self.log(f"File not found: {path}")
            return False

        self._original_image_path = path
        self.log(f"Original image set: {path}")
        self._notify_images_changed()
        return True

    def set_relit_image(self, path: str) -> bool:
        """
        Set relit image path.

        Args:
            path: Image file path

        Returns:
            bool: Success
        """
        if not os.path.exists(path):
            self.log(f"File not found: {path}")
            return False

        self._relit_image_path = path
        self.log(f"Relit image set: {path}")
        self._notify_images_changed()
        return True

    def clear_images(self) -> None:
        """Clear all images."""
        self._original_image_path = None
        self._relit_image_path = None
        self.log("Images cleared")
        self._notify_images_changed()

    # =========================================================================
    # Scene Info
    # =========================================================================

    def get_scene_info(self) -> str:
        """Get current scene info."""
        return export_scene_info_for_llm()

    def get_lights_info(self) -> str:
        """Get scene lights info."""
        return get_lights_summary()

    # =========================================================================
    # AI Analysis
    # =========================================================================

    @property
    def is_analyzing(self) -> bool:
        """Whether analysis is in progress."""
        return self._is_analyzing

    def analyze_relight(self, custom_prompt: Optional[str] = None) -> None:
        """
        Analyze relit image difference (async).

        Args:
            custom_prompt: Custom prompt
        """
        # Check prerequisites
        if not self.is_configured:
            self.log("Error: Please set API Key first")
            self.set_status("Please set API Key first")
            return

        if not self._original_image_path:
            self.log("Error: Please set original image first")
            self.set_status("Please set original image first")
            return

        if not self._relit_image_path:
            self.log("Error: Please set relit image first")
            self.set_status("Please set relit image first")
            return

        if self._is_analyzing:
            self.log("Warning: Analysis already in progress")
            return

        self._is_analyzing = True
        self.set_status("Analyzing image difference...")
        self.log("Starting relight analysis...")

        # Get scene info
        scene_info = self.get_scene_info()

        # Async analysis
        def do_analysis():
            try:
                client = self._get_or_create_client()
                result = client.analyze_relight(
                    original_image_path=self._original_image_path,
                    relit_image_path=self._relit_image_path,
                    scene_info=scene_info,
                    custom_prompt=custom_prompt,
                )
                self._on_analysis_complete(True, result)
            except Exception as e:
                self._on_analysis_complete(False, {"error": str(e)})

        self._executor.submit(do_analysis)

    def _on_analysis_complete(self, success: bool, result: Optional[Dict]) -> None:
        """Analysis complete callback."""
        self._is_analyzing = False
        self._last_analysis_result = result

        if success and result and result.get("success"):
            operations = result.get("operations", [])
            self._pending_operations = operations
            
            reasoning = result.get("reasoning", "")
            
            self.log(f"Analysis complete, generated {len(operations)} light operations")
            if reasoning:
                self.log(f"Reasoning: {reasoning}")
            
            # Show operations summary
            summary = LightPrimitiveParser.get_operations_summary(operations)
            self.log(summary)
            
            self.set_status(f"Analysis complete, {len(operations)} operations pending")
        else:
            error = result.get("error", "Unknown error") if result else "Unknown error"
            self.log(f"Analysis failed: {error}")
            self.set_status("Analysis failed")

        self._notify_analysis_complete(success, result)

    # =========================================================================
    # Light Operations
    # =========================================================================

    @property
    def pending_operations(self) -> List[Dict]:
        """Get pending operations list."""
        return self._pending_operations.copy()

    @property
    def has_pending_operations(self) -> bool:
        """Whether there are pending operations."""
        return len(self._pending_operations) > 0

    def execute_operations(self) -> bool:
        """
        Execute pending light operations.

        Returns:
            bool: Success
        """
        if not self._pending_operations:
            self.log("No pending operations")
            return False

        self.set_status("Executing light operations...")
        self.log(f"Executing {len(self._pending_operations)} light operations...")

        success_count, fail_count, messages = execute_light_operations(
            self._pending_operations
        )

        for msg in messages:
            self.log(msg)

        self.log(f"Execution complete: {success_count} succeeded, {fail_count} failed")
        self.set_status(f"Complete: {success_count} succeeded, {fail_count} failed")

        # Clear pending operations
        self._pending_operations.clear()

        return fail_count == 0

    def preview_operations(self) -> str:
        """
        Preview pending operations.

        Returns:
            str: Operations preview text
        """
        if not self._pending_operations:
            return "No pending operations"

        return LightPrimitiveParser.get_operations_summary(self._pending_operations)

    def clear_pending_operations(self) -> None:
        """Clear pending operations."""
        self._pending_operations.clear()
        self.log("Pending operations cleared")
        self.set_status("Operations cleared")

    # =========================================================================
    # Callback Management
    # =========================================================================

    def add_images_changed_callback(self, callback: Callable) -> None:
        """Add image changed callback."""
        if callback not in self._on_images_changed_callbacks:
            self._on_images_changed_callbacks.append(callback)

    def remove_images_changed_callback(self, callback: Callable) -> None:
        """Remove image changed callback."""
        if callback in self._on_images_changed_callbacks:
            self._on_images_changed_callbacks.remove(callback)

    def _notify_images_changed(self) -> None:
        """Notify image changed."""
        for callback in self._on_images_changed_callbacks:
            try:
                callback()
            except Exception as e:
                self.log(f"Image changed callback error: {e}")

    def add_analysis_complete_callback(self, callback: Callable) -> None:
        """Add analysis complete callback."""
        if callback not in self._on_analysis_complete_callbacks:
            self._on_analysis_complete_callbacks.append(callback)

    def remove_analysis_complete_callback(self, callback: Callable) -> None:
        """Remove analysis complete callback."""
        if callback in self._on_analysis_complete_callbacks:
            self._on_analysis_complete_callbacks.remove(callback)

    def _notify_analysis_complete(self, success: bool, result: Optional[Dict]) -> None:
        """Notify analysis complete."""
        for callback in self._on_analysis_complete_callbacks:
            try:
                callback(success, result)
            except Exception as e:
                self.log(f"Analysis complete callback error: {e}")

    # =========================================================================
    # Test Connection
    # =========================================================================

    def test_connection(self) -> None:
        """Test API connection (async)."""
        if not self.is_configured:
            self.log("Error: Please set API Key first")
            return

        self.set_status("Testing connection...")
        self.log("Testing API connection...")

        def do_test():
            try:
                client = self._get_or_create_client()
                success, msg = client.test_connection()
                if success:
                    self.log(f"Connection successful: {msg}")
                    self.set_status("Connection successful")
                    # Auto-save configuration on successful connection
                    self._save_settings()
                else:
                    self.log(f"Connection failed: {msg}")
                    self.set_status("Connection failed")
            except Exception as e:
                self.log(f"Connection error: {e}")
                self.set_status("Connection error")

        self._executor.submit(do_test)

    # =========================================================================
    # Lifecycle
    # =========================================================================

    def dispose(self) -> None:
        """Cleanup resources."""
        super().dispose()

        if self._gemini_client:
            self._gemini_client.dispose()
            self._gemini_client = None

        if self._executor:
            self._executor.shutdown(wait=False)

        self._on_images_changed_callbacks.clear()
        self._on_analysis_complete_callbacks.clear()
