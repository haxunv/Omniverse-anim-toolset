# -*- coding: utf-8 -*-
"""
模块结构:
    - stage_utils: Stage 相关的通用工具函数
    - load_manager: 角色加载/卸载管理核心逻辑
    - curves_width: BasisCurves 宽度调整核心逻辑
    - uv_transfer: UV 数据传输核心逻辑
"""

from .stage_utils import (
    get_stage,
    get_selection_paths,
    safe_log,
)
from .load_manager import (
    load_or_activate,
    unload_or_deactivate,
)
from .curves_width import (
    collect_curves,
    make_width_ramp,
    author_ramp_to_curves,
    clear_widths,
)
from .uv_transfer import (
    collect_curves_under,
    expand_primvar,
    bake_uv_to_file,
)

__all__ = [
    # stage_utils
    "get_stage",
    "get_selection_paths",
    "safe_log",
    # load_manager
    "load_or_activate",
    "unload_or_deactivate",
    # curves_width
    "collect_curves",
    "make_width_ramp",
    "author_ramp_to_curves",
    "clear_widths",
    # uv_transfer
    "collect_curves_under",
    "expand_primvar",
    "bake_uv_to_file",
]
