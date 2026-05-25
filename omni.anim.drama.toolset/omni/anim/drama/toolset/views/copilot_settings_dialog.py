# -*- coding: utf-8 -*-
"""
Copilot 设置弹窗
================

一个独立的 ``ui.Window``，用于配置 LLM 后端、行为开关与安全选项。
"""

from __future__ import annotations

from typing import Optional

import omni.ui as ui

from .styles import Colors, Sizes
from ..viewmodels.copilot_vm import CopilotViewModel
from ..agent.backend.base import PROVIDER_PRESETS


# =============================================================================
# 预设 Provider 选项
# =============================================================================

PROVIDER_OPTIONS = [
    ("siliconflow", "SiliconFlow (default)"),
    ("kimi_official", "Kimi (Moonshot)"),
    ("openai", "OpenAI"),
    ("deepseek", "DeepSeek"),
    ("gemini", "Google Gemini"),
    ("custom", "Custom (OpenAI-compatible)"),
]


# =============================================================================
# CopilotSettingsDialog
# =============================================================================

class CopilotSettingsDialog:
    """设置弹窗。"""

    def __init__(self, vm: CopilotViewModel) -> None:
        self._vm = vm
        self._window: Optional[ui.Window] = None

        # UI refs
        self._provider_combo: Optional[ui.ComboBox] = None
        self._base_url_field: Optional[ui.StringField] = None
        self._api_key_field: Optional[ui.StringField] = None
        self._model_field: Optional[ui.StringField] = None
        self._temperature_field: Optional[ui.FloatField] = None
        self._max_tokens_field: Optional[ui.IntField] = None
        self._auto_ro_cb: Optional[ui.CheckBox] = None
        self._auto_mu_cb: Optional[ui.CheckBox] = None
        self._allow_de_cb: Optional[ui.CheckBox] = None
        self._show_cost_cb: Optional[ui.CheckBox] = None
        self._test_label: Optional[ui.Label] = None

    # ---------- 显示 / 隐藏 ----------

    def show(self) -> None:
        if self._window is None:
            self._build()
        if self._window:
            self._window.visible = True
            self._sync_from_vm()

    def hide(self) -> None:
        if self._window:
            self._window.visible = False

    def destroy(self) -> None:
        if self._window:
            try:
                self._window.destroy()
            except Exception:
                pass
            self._window = None

    # ---------- 构建 ----------

    def _build(self) -> None:
        self._window = ui.Window(
            "Anime Agent Settings",
            width=520,
            height=560,
            flags=ui.WINDOW_FLAGS_NO_COLLAPSE,
        )
        with self._window.frame:
            with ui.ScrollingFrame(
                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
            ):
                with ui.VStack(
                    spacing=Sizes.SPACING_MEDIUM,
                    margin=Sizes.MARGIN_MEDIUM,
                ):
                    ui.Label(
                        "LLM Provider",
                        style={"font_size": 14, "color": Colors.TEXT_PRIMARY},
                        height=18,
                    )

                    self._provider_combo = ui.ComboBox(
                        0, *[label for _, label in PROVIDER_OPTIONS]
                    )
                    self._provider_combo.model.add_item_changed_fn(self._on_provider_changed)

                    ui.Separator(height=2)

                    self._build_field("Base URL", "_base_url_field")
                    self._build_field("API Key", "_api_key_field", password=True)
                    self._build_field("Model", "_model_field")

                    with ui.HStack(spacing=Sizes.SPACING_MEDIUM, height=Sizes.INPUT_HEIGHT):
                        ui.Label("Temperature", width=Sizes.LABEL_WIDTH_SMALL,
                                 style={"color": Colors.TEXT_SECONDARY})
                        self._temperature_field = ui.FloatField(height=Sizes.INPUT_HEIGHT, width=80)
                        ui.Spacer()
                        ui.Label("Max Tokens", width=Sizes.LABEL_WIDTH_SMALL,
                                 style={"color": Colors.TEXT_SECONDARY})
                        self._max_tokens_field = ui.IntField(height=Sizes.INPUT_HEIGHT, width=100)

                    ui.Separator(height=4)
                    ui.Label(
                        "Behavior",
                        style={"font_size": 14, "color": Colors.TEXT_PRIMARY},
                        height=18,
                    )

                    self._auto_ro_cb = self._build_checkbox(
                        "Auto-run read_only tools (recommended)"
                    )
                    self._auto_mu_cb = self._build_checkbox(
                        "Auto-approve mutate tools (use with caution)"
                    )
                    self._allow_de_cb = self._build_checkbox(
                        "Allow destructive tools (irreversible operations)"
                    )
                    self._show_cost_cb = self._build_checkbox(
                        "Show token / cost info"
                    )

                    ui.Separator(height=4)

                    with ui.HStack(spacing=Sizes.SPACING_MEDIUM, height=Sizes.BUTTON_HEIGHT):
                        ui.Button(
                            "Test Connection",
                            clicked_fn=self._on_test_clicked,
                            height=Sizes.BUTTON_HEIGHT,
                            width=120,
                        )
                        self._test_label = ui.Label(
                            "",
                            style={"color": Colors.TEXT_SECONDARY},
                        )

                    ui.Spacer(height=4)

                    with ui.HStack(spacing=Sizes.SPACING_MEDIUM, height=Sizes.BUTTON_HEIGHT):
                        ui.Button(
                            "Save",
                            clicked_fn=self._on_save_clicked,
                            style={"background_color": Colors.PRIMARY, "color": Colors.TEXT_PRIMARY},
                            height=Sizes.BUTTON_HEIGHT,
                        )
                        ui.Button(
                            "Apply Preset",
                            clicked_fn=self._on_apply_preset_clicked,
                            height=Sizes.BUTTON_HEIGHT,
                        )
                        ui.Button(
                            "Close",
                            clicked_fn=self.hide,
                            height=Sizes.BUTTON_HEIGHT,
                        )

    def _build_field(self, label: str, attr_name: str, password: bool = False) -> None:
        with ui.HStack(spacing=Sizes.SPACING_MEDIUM, height=Sizes.INPUT_HEIGHT):
            ui.Label(label, width=Sizes.LABEL_WIDTH_SMALL, style={"color": Colors.TEXT_SECONDARY})
            kwargs = {"height": Sizes.INPUT_HEIGHT}
            if password:
                kwargs["password_mode"] = True
            field = ui.StringField(**kwargs)
            setattr(self, attr_name, field)

    def _build_checkbox(self, label: str) -> ui.CheckBox:
        with ui.HStack(spacing=Sizes.SPACING_MEDIUM, height=22):
            cb = ui.CheckBox(width=18)
            ui.Label(label, style={"color": Colors.TEXT_PRIMARY})
            ui.Spacer()
        return cb

    # ---------- 同步 ----------

    def _sync_from_vm(self) -> None:
        # provider combo
        if self._provider_combo:
            idx = 0
            for i, (key, _label) in enumerate(PROVIDER_OPTIONS):
                if key == self._vm.provider:
                    idx = i
                    break
            try:
                self._provider_combo.model.get_item_value_model().set_value(idx)
            except Exception:
                pass

        if self._base_url_field:
            self._base_url_field.model.set_value(self._vm.base_url)
        if self._api_key_field:
            self._api_key_field.model.set_value(self._vm.api_key)
        if self._model_field:
            self._model_field.model.set_value(self._vm.model)
        if self._temperature_field:
            self._temperature_field.model.set_value(float(self._vm.temperature))
        if self._max_tokens_field:
            self._max_tokens_field.model.set_value(int(self._vm.max_tokens))
        if self._auto_ro_cb:
            self._auto_ro_cb.model.set_value(bool(self._vm.auto_run_read_only))
        if self._auto_mu_cb:
            self._auto_mu_cb.model.set_value(bool(self._vm.auto_approve_mutate))
        if self._allow_de_cb:
            self._allow_de_cb.model.set_value(bool(self._vm.allow_destructive))
        if self._show_cost_cb:
            self._show_cost_cb.model.set_value(bool(self._vm.show_cost))
        if self._test_label:
            self._test_label.text = ""

    def _flush_to_vm(self) -> None:
        if self._base_url_field:
            self._vm.set_base_url(self._base_url_field.model.get_value_as_string(), save=False)
        if self._api_key_field:
            self._vm.set_api_key(self._api_key_field.model.get_value_as_string(), save=False)
        if self._model_field:
            self._vm.set_model(self._model_field.model.get_value_as_string(), save=False)
        if self._temperature_field:
            self._vm.set_temperature(self._temperature_field.model.get_value_as_float(), save=False)
        if self._max_tokens_field:
            self._vm.set_max_tokens(self._max_tokens_field.model.get_value_as_int(), save=False)
        if self._auto_ro_cb:
            self._vm.set_auto_run_read_only(self._auto_ro_cb.model.get_value_as_bool(), save=False)
        if self._auto_mu_cb:
            self._vm.set_auto_approve_mutate(self._auto_mu_cb.model.get_value_as_bool(), save=False)
        if self._allow_de_cb:
            self._vm.set_allow_destructive(self._allow_de_cb.model.get_value_as_bool(), save=False)
        if self._show_cost_cb:
            self._vm.set_show_cost(self._show_cost_cb.model.get_value_as_bool(), save=False)

    # ---------- 事件 ----------

    def _on_provider_changed(self, *args, **kwargs) -> None:
        if not self._provider_combo:
            return
        try:
            idx = self._provider_combo.model.get_item_value_model().get_value_as_int()
        except Exception:
            return
        if idx < 0 or idx >= len(PROVIDER_OPTIONS):
            return
        key, _label = PROVIDER_OPTIONS[idx]
        self._vm.set_provider(key, use_preset=True, save=False)
        # 预设回填
        if self._base_url_field:
            self._base_url_field.model.set_value(self._vm.base_url)
        if self._model_field:
            self._model_field.model.set_value(self._vm.model)

    def _on_apply_preset_clicked(self) -> None:
        # 强制按当前 provider 回填
        self._on_provider_changed()

    def _on_test_clicked(self) -> None:
        self._flush_to_vm()
        if self._test_label:
            self._test_label.text = "Testing..."
            self._test_label.style = {"color": Colors.TEXT_SECONDARY}

        def on_result(success: bool, msg: str) -> None:
            # 此回调在 worker 线程，但 omni.ui Label 的 text 赋值一般安全
            if self._test_label:
                try:
                    self._test_label.text = msg
                    self._test_label.style = {
                        "color": Colors.SUCCESS if success else Colors.ERROR,
                    }
                except Exception:
                    pass

        self._vm.test_connection(on_result)

    def _on_save_clicked(self) -> None:
        self._flush_to_vm()
        self._vm.save_settings()
        if self._test_label:
            self._test_label.text = "Saved"
            self._test_label.style = {"color": Colors.SUCCESS}
