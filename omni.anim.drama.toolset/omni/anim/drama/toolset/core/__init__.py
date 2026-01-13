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
    - render_layer: 渲染层管理
    - render_collection: 渲染层 Collection 管理
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
from .render_layer import (
    create_render_layer,
    delete_render_layer,
    rename_render_layer,
    get_all_render_layers,
    get_render_layer_info,
    set_layer_visible,
    set_layer_solo,
    set_layer_renderable,
    move_layer_up,
    move_layer_down,
)
from .render_collection import (
    create_collection,
    delete_collection,
    add_members,
    remove_members,
    get_collection_members,
    get_collection_info,
    set_include_expression,
    get_include_expression,
)
from .render_override import (
    set_visibility_override,
    set_light_property,
    set_material_binding,
    apply_override_to_collection,
)
from .render_aov import (
    create_aov,
    delete_aov,
    get_all_aovs,
    get_aov_info,
    link_aov_to_layer,
)
from .aov_merge import (
    scan_aov_files,
    get_scan_summary,
    merge_aovs_external,
    auto_merge_aovs,
    check_openexr_available,
    ensure_openexr_available,
)
from .layer_state import (
    get_layer_state_manager,
    switch_to_layer,
    restore_original_states,
    enable_layer_state_management,
    is_layer_state_management_enabled,
    get_layer_state_info,
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
    # scene_exporter
    "export_scene_info",
    "export_scene_info_for_llm",
    "export_cameras_info",
    "export_lights_info",
    # render_capture
    "capture_viewport",
    "read_image_as_base64",
    # render_layer
    "create_render_layer",
    "delete_render_layer",
    "rename_render_layer",
    "get_all_render_layers",
    "get_render_layer_info",
    "set_layer_visible",
    "set_layer_solo",
    "set_layer_renderable",
    # render_collection
    "create_collection",
    "delete_collection",
    "add_members",
    "remove_members",
    "get_collection_members",
    "get_collection_info",
    "set_include_expression",
    "get_include_expression",
    # render_override
    "set_visibility_override",
    "set_light_property",
    "set_material_binding",
    "apply_override_to_collection",
    # render_aov
    "create_aov",
    "delete_aov",
    "get_all_aovs",
    "get_aov_info",
    "link_aov_to_layer",
    # aov_merge
    "scan_aov_files",
    "get_scan_summary",
    "merge_aovs_external",
    "auto_merge_aovs",
    "check_openexr_available",
    "ensure_openexr_available",
    # layer_state (Maya 风格)
    "get_layer_state_manager",
    "switch_to_layer",
    "restore_original_states",
    "enable_layer_state_management",
    "is_layer_state_management_enabled",
    "get_layer_state_info",
]
