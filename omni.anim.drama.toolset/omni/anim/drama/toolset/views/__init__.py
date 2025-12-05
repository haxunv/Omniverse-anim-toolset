# -*- coding: utf-8 -*-
"""
Views Module - 视图层 (View Layer)
==================================

本模块包含所有 UI 视图组件。
视图层负责：
    - 构建用户界面
    - 处理用户交互
    - 绑定 ViewModel 数据

模块结构:
    - styles: 统一的样式定义
    - base_view: View 基类
    - load_manager_view: 角色加载管理视图
    - curves_width_view: 曲线宽度调整视图
    - uv_transfer_view: UV 传输视图
    - main_window: 主窗口（标签页容器）
"""

from .styles import Styles
from .base_view import BaseView
from .load_manager_view import LoadManagerView
from .curves_width_view import CurvesWidthView
from .uv_transfer_view import UVTransferView
from .main_window import MainWindow

__all__ = [
    "Styles",
    "BaseView",
    "LoadManagerView",
    "CurvesWidthView",
    "UVTransferView",
    "MainWindow",
]
