# -*- coding: utf-8 -*-
"""
ViewModels Module - 视图模型层 (ViewModel Layer)
================================================

本模块包含所有 ViewModel 类，作为 Model 和 View 之间的桥梁。
ViewModel 负责：
    - 管理 UI 状态
    - 调用 Core 层的业务逻辑
    - 提供 View 层可绑定的数据和命令

模块结构:
    - base_viewmodel: ViewModel 基类
    - load_manager_vm: 角色加载管理 ViewModel
    - curves_width_vm: 曲线宽度调整 ViewModel
    - uv_transfer_vm: UV 传输 ViewModel
    - light_link_vm: 灯光链接 ViewModel
    - relight_vm: 动画重打光 ViewModel
"""

from .base_viewmodel import BaseViewModel
from .load_manager_vm import LoadManagerViewModel
from .curves_width_vm import CurvesWidthViewModel
from .uv_transfer_vm import UVTransferViewModel
from .light_link_vm import LightLinkViewModel
from .relight_vm import RelightViewModel
from .render_setup_vm import RenderSetupViewModel
from .exr_merge_vm import ExrMergeViewModel

__all__ = [
    "BaseViewModel",
    "LoadManagerViewModel",
    "CurvesWidthViewModel",
    "UVTransferViewModel",
    "LightLinkViewModel",
    "RelightViewModel",
    "RenderSetupViewModel",
    "ExrMergeViewModel",
]
