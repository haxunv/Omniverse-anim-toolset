# -*- coding: utf-8 -*-
"""
View 基类
=========

提供所有视图的通用功能，包括：
    - ViewModel 绑定
    - 日志显示
    - 生命周期管理
"""

from typing import Optional, TYPE_CHECKING
import omni.ui as ui

from .styles import Styles, Sizes, Colors

if TYPE_CHECKING:
    from ..viewmodels.base_viewmodel import BaseViewModel


class BaseView:
    """
    View 基类，提供通用的 UI 构建和数据绑定功能。

    所有具体的 View 都应继承此类。

    Attributes:
        _viewmodel: 绑定的 ViewModel
        _log_field: 日志显示组件
    """

    def __init__(self, viewmodel: "BaseViewModel"):
        """
        初始化 View 基类。

        Args:
            viewmodel: 要绑定的 ViewModel
        """
        self._viewmodel = viewmodel
        self._log_field: Optional[ui.StringField] = None
        self._status_field: Optional[ui.StringField] = None

        # 绑定 ViewModel 回调
        self._bind_viewmodel()

    # =========================================================================
    # ViewModel 绑定
    # =========================================================================

    def _bind_viewmodel(self) -> None:
        """绑定 ViewModel 的回调。"""
        self._viewmodel.add_log_callback(self._on_log)
        self._viewmodel.add_status_callback(self._on_status)

    def _unbind_viewmodel(self) -> None:
        """解绑 ViewModel 的回调。"""
        self._viewmodel.remove_log_callback(self._on_log)
        self._viewmodel.remove_status_callback(self._on_status)

    # =========================================================================
    # 回调处理
    # =========================================================================

    def _on_log(self, message: str) -> None:
        """
        日志回调处理。

        Args:
            message: 日志消息
        """
        if self._log_field:
            current = self._log_field.model.get_value_as_string()
            # 限制日志长度
            new_value = current + message + "\n"
            if len(new_value) > 50000:
                new_value = new_value[-40000:]
            self._log_field.model.set_value(new_value)

    def _on_status(self, status: str) -> None:
        """
        状态回调处理。

        Args:
            status: 状态消息
        """
        if self._status_field:
            self._status_field.model.set_value(status)

    # =========================================================================
    # UI 构建辅助方法
    # =========================================================================

    def _create_log_section(self, height: int = Sizes.LOG_HEIGHT) -> ui.StringField:
        """
        创建日志显示区域。

        Args:
            height: 日志区域高度

        Returns:
            ui.StringField: 日志显示组件
        """
        ui.Separator()
        ui.Label("Log:", style=Styles.LABEL_SECONDARY)
        self._log_field = ui.StringField(
            multiline=True,
            height=height,
            read_only=True
        )
        self._log_field.model.set_value("Log:\n")
        return self._log_field

    def _create_status_section(self, height: int = Sizes.STATUS_HEIGHT) -> ui.StringField:
        """
        创建状态显示区域。

        Args:
            height: 状态区域高度

        Returns:
            ui.StringField: 状态显示组件
        """
        ui.Label("Status:", style=Styles.LABEL_SECONDARY)
        self._status_field = ui.StringField(
            multiline=True,
            height=height,
            read_only=True
        )
        return self._status_field

    def _create_path_display(
        self,
        label_text: str,
        label_width: int = Sizes.LABEL_WIDTH
    ) -> ui.Label:
        """
        创建路径显示区域。

        Args:
            label_text: 标签文字
            label_width: 标签宽度

        Returns:
            ui.Label: 路径显示组件
        """
        with ui.HStack():
            ui.Label(label_text, width=label_width)
            path_label = ui.Label(
                "",
                word_wrap=True,
                style=Styles.get_path_label_style()
            )
        return path_label

    def _create_selection_button(
        self,
        button_text: str,
        clicked_fn,
        label_width: int = Sizes.LABEL_WIDTH
    ) -> ui.Button:
        """
        创建带缩进的选择按钮。

        Args:
            button_text: 按钮文字
            clicked_fn: 点击回调
            label_width: 左侧缩进宽度

        Returns:
            ui.Button: 按钮组件
        """
        with ui.HStack():
            ui.Spacer(width=label_width)
            button = ui.Button(button_text, clicked_fn=clicked_fn)
        return button

    # =========================================================================
    # 抽象方法
    # =========================================================================

    def build(self) -> None:
        """
        构建 UI。

        子类必须实现此方法。
        """
        raise NotImplementedError("Subclass must implement build()")

    # =========================================================================
    # 生命周期
    # =========================================================================

    def dispose(self) -> None:
        """清理资源。"""
        self._unbind_viewmodel()
        self._log_field = None
        self._status_field = None
