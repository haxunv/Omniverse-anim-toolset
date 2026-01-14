# -*- coding: utf-8 -*-
"""
Core Module - 核心业务逻辑层
============================

模块结构:
    - stage_utils: Stage 相关的通用工具函数
    - load_manager: 角色加载/卸载管理核心逻辑
    - curves_width: BasisCurves 宽度调整核心逻辑
    - uv_transfer: UV 数据传输核心逻辑
    - light_link: 灯光链接核心逻辑
    - light_control: 灯光创建/修改核心逻辑
    - scene_exporter: 场景信息导出
    - render_capture: 渲染图采集
    - render_setup: Maya-like render setup (layers, collections, overrides)
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
from .light_link import (
    is_light_prim,
    is_geometry_prim,
    create_light_link,
    remove_light_link,
    get_light_link_targets,
)
from .light_control import (
    create_light,
    modify_light,
    delete_light,
    execute_light_operations,
    get_all_lights,
    get_light_info,
    get_lights_summary,
    # Relight Layer 管理
    remove_relight_layer,
    toggle_relight_layer,
    get_relight_layer_info,
)
from .scene_exporter import (
    export_scene_info,
    export_scene_info_for_llm,
    export_cameras_info,
    export_lights_info,
)
from .render_capture import (
    capture_viewport,
    read_image_as_base64,
)
from .render_setup import (
    RenderSetupManager,
    get_render_setup_manager,
    reset_render_setup_manager,
    RenderLayer,
    Collection,
    Override,
    FilterType,
    OverrideType,
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
    # light_link
    "is_light_prim",
    "is_geometry_prim",
    "create_light_link",
    "remove_light_link",
    "get_light_link_targets",
    # light_control
    "create_light",
    "modify_light",
    "delete_light",
    "execute_light_operations",
    "get_all_lights",
    "get_light_info",
    "get_lights_summary",
    "remove_relight_layer",
    "toggle_relight_layer",
    "get_relight_layer_info",
    # scene_exporter
    "export_scene_info",
    "export_scene_info_for_llm",
    "export_cameras_info",
    "export_lights_info",
    # render_capture
    "capture_viewport",
    "read_image_as_base64",
    # render_setup
    "RenderSetupManager",
    "get_render_setup_manager",
    "reset_render_setup_manager",
    "RenderLayer",
    "Collection",
    "Override",
    "FilterType",
    "OverrideType",
]
