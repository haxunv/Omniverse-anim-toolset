# -*- coding: utf-8 -*-
"""
主窗口
======

创建包含所有工具的主窗口。
"""

from typing import Optional, Callable
import omni.ui as ui

from .styles import Sizes
from .load_manager_view import LoadManagerView
from .curves_width_view import CurvesWidthView
from .uv_transfer_view import UVTransferView
from .light_link_view import LightLinkView
from .ai_camera_view import AICameraView
from ..viewmodels import (
    LoadManagerViewModel,
    CurvesWidthViewModel,
    UVTransferViewModel,
    LightLinkViewModel,
    AICameraViewModel,
)


# 窗口标题
WINDOW_TITLE = "Anim Drama Toolset"


class MainWindow:
    """
    主窗口类。
    """

    def __init__(self):
        """初始化主窗口。"""
        self._window: Optional[ui.Window] = None

        # ViewModels
        self._load_manager_vm: Optional[LoadManagerViewModel] = None
        self._curves_width_vm: Optional[CurvesWidthViewModel] = None
        self._uv_transfer_vm: Optional[UVTransferViewModel] = None
        self._light_link_vm: Optional[LightLinkViewModel] = None
        self._ai_camera_vm: Optional[AICameraViewModel] = None

        # Views
        self._load_manager_view: Optional[LoadManagerView] = None
        self._curves_width_view: Optional[CurvesWidthView] = None
        self._uv_transfer_view: Optional[UVTransferView] = None
        self._light_link_view: Optional[LightLinkView] = None
        self._ai_camera_view: Optional[AICameraView] = None

        # 当前激活的标签索引
        self._current_tab = 0
        self._tab_frames = []

        # 可见性变化回调
        self._visibility_changed_fn: Optional[Callable[[bool], None]] = None

        self._build()

    def _build(self) -> None:
        """构建主窗口。"""
        # 创建窗口
        self._window = ui.Window(
            WINDOW_TITLE,
            width=Sizes.WINDOW_WIDTH,
            height=Sizes.WINDOW_HEIGHT,
        )

        # 监听窗口可见性变化
        self._window.set_visibility_changed_fn(self._on_visibility_changed)

        # 创建 ViewModels
        self._load_manager_vm = LoadManagerViewModel()
        self._curves_width_vm = CurvesWidthViewModel()
        self._uv_transfer_vm = UVTransferViewModel()
        self._light_link_vm = LightLinkViewModel()
        self._ai_camera_vm = AICameraViewModel()

        # 构建 UI
        with self._window.frame:
            with ui.VStack(spacing=4):
                # 标签按钮行
                with ui.HStack(height=30):
                    self._tab_buttons = []

                    btn1 = ui.Button(
                        "Load Manager",
                        clicked_fn=lambda: self._switch_tab(0),
                        style={"background_color": 0xFF3A8EBA}
                    )
                    self._tab_buttons.append(btn1)

                    btn2 = ui.Button(
                        "Curves Width",
                        clicked_fn=lambda: self._switch_tab(1),
                    )
                    self._tab_buttons.append(btn2)

                    btn3 = ui.Button(
                        "UV Transfer",
                        clicked_fn=lambda: self._switch_tab(2),
                    )
                    self._tab_buttons.append(btn3)

                    btn4 = ui.Button(
                        "Light Link",
                        clicked_fn=lambda: self._switch_tab(3),
                    )
                    self._tab_buttons.append(btn4)

                    btn5 = ui.Button(
                        "🎬 AI Camera",
                        clicked_fn=lambda: self._switch_tab(4),
                    )
                    self._tab_buttons.append(btn5)

                ui.Separator(height=2)

                # 内容区域使用 ZStack 叠加
                with ui.ZStack():
                    # Load Manager 内容
                    self._frame1 = ui.Frame(visible=True)
                    with self._frame1:
                        with ui.ScrollingFrame(
                            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                            vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED
                        ):
                            with ui.VStack(
                                margin=Sizes.MARGIN_MEDIUM,
                                spacing=Sizes.SPACING_MEDIUM
                            ):
                                self._load_manager_view = LoadManagerView(
                                    self._load_manager_vm
                                )
                                self._load_manager_view.build()
                    self._tab_frames.append(self._frame1)

                    # Curves Width 内容
                    self._frame2 = ui.Frame(visible=False)
                    with self._frame2:
                        with ui.ScrollingFrame(
                            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                            vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED
                        ):
                            with ui.VStack(
                                margin=Sizes.MARGIN_MEDIUM,
                                spacing=Sizes.SPACING_MEDIUM
                            ):
                                self._curves_width_view = CurvesWidthView(
                                    self._curves_width_vm
                                )
                                self._curves_width_view.build()
                    self._tab_frames.append(self._frame2)

                    # UV Transfer 内容
                    self._frame3 = ui.Frame(visible=False)
                    with self._frame3:
                        with ui.ScrollingFrame(
                            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                            vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED
                        ):
                            with ui.VStack(
                                margin=Sizes.MARGIN_MEDIUM,
                                spacing=Sizes.SPACING_MEDIUM
                            ):
                                self._uv_transfer_view = UVTransferView(
                                    self._uv_transfer_vm
                                )
                                self._uv_transfer_view.build()
                    self._tab_frames.append(self._frame3)

                    # Light Link 内容
                    self._frame4 = ui.Frame(visible=False)
                    with self._frame4:
                        with ui.ScrollingFrame(
                            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                            vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED
                        ):
                            with ui.VStack(
                                margin=Sizes.MARGIN_MEDIUM,
                                spacing=Sizes.SPACING_MEDIUM
                            ):
                                self._light_link_view = LightLinkView(
                                    self._light_link_vm
                                )
                                self._light_link_view.build()
                    self._tab_frames.append(self._frame4)

                    # AI Camera 内容
                    self._frame5 = ui.Frame(visible=False)
                    with self._frame5:
                        with ui.ScrollingFrame(
                            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                            vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED
                        ):
                            with ui.VStack(
                                margin=Sizes.MARGIN_MEDIUM,
                                spacing=Sizes.SPACING_MEDIUM
                            ):
                                self._ai_camera_view = AICameraView(
                                    self._ai_camera_vm
                                )
                                self._ai_camera_view.build()
                    self._tab_frames.append(self._frame5)

    def _switch_tab(self, index: int) -> None:
        """切换标签页。"""
        self._current_tab = index

        # 更新按钮样式
        for i, btn in enumerate(self._tab_buttons):
            if i == index:
                btn.style = {"background_color": 0xFF3A8EBA}
            else:
                btn.style = {"background_color": 0xFF333333}

        # 更新内容可见性
        for i, frame in enumerate(self._tab_frames):
            frame.visible = (i == index)

    def _on_visibility_changed(self, visible: bool) -> None:
        """窗口可见性变化回调。"""
        if self._visibility_changed_fn:
            self._visibility_changed_fn(visible)

    def set_visibility_changed_fn(self, fn: Callable[[bool], None]) -> None:
        """设置窗口可见性变化的回调函数。"""
        self._visibility_changed_fn = fn

    # =========================================================================
    # 公共方法
    # =========================================================================

    def show(self) -> None:
        """显示窗口。"""
        if self._window:
            self._window.visible = True

    def hide(self) -> None:
        """隐藏窗口。"""
        if self._window:
            self._window.visible = False

    def toggle(self) -> None:
        """切换窗口可见性。"""
        if self._window:
            self._window.visible = not self._window.visible

    @property
    def visible(self) -> bool:
        """获取窗口可见性。"""
        return self._window.visible if self._window else False

    @visible.setter
    def visible(self, value: bool) -> None:
        """设置窗口可见性。"""
        if self._window:
            self._window.visible = value

    # =========================================================================
    # 生命周期
    # =========================================================================

    def destroy(self) -> None:
        """销毁窗口并清理资源。"""
        # 清理 Views
        if self._load_manager_view:
            self._load_manager_view.dispose()
            self._load_manager_view = None

        if self._curves_width_view:
            self._curves_width_view.dispose()
            self._curves_width_view = None

        if self._uv_transfer_view:
            self._uv_transfer_view.dispose()
            self._uv_transfer_view = None

        if self._light_link_view:
            self._light_link_view.dispose()
            self._light_link_view = None

        if self._ai_camera_view:
            self._ai_camera_view.dispose()
            self._ai_camera_view = None

        # 清理 ViewModels
        if self._load_manager_vm:
            self._load_manager_vm.dispose()
            self._load_manager_vm = None

        if self._curves_width_vm:
            self._curves_width_vm.dispose()
            self._curves_width_vm = None

        if self._uv_transfer_vm:
            self._uv_transfer_vm.dispose()
            self._uv_transfer_vm = None

        if self._light_link_vm:
            self._light_link_vm.dispose()
            self._light_link_vm = None

        if self._ai_camera_vm:
            self._ai_camera_vm.dispose()
            self._ai_camera_vm = None

        # 清理窗口
        if self._window:
            self._window.set_visibility_changed_fn(None)
            self._window.destroy()
            self._window = None
