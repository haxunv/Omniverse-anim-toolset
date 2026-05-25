# -*- coding: utf-8 -*-
"""
Scene 工具
===========

把 ``core.scene_exporter`` 和 ``core.stage_utils`` 里的查询函数暴露给 LLM。

所有工具均为 ``READ_ONLY``（默认自动执行，无需审批）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..tool_registry import tool, ToolPermission
from ...core.scene_exporter import (
    export_scene_info,
    export_scene_info_for_llm,
    export_cameras_info,
    export_camera_info,
    export_scene_bounds,
    export_geometry_prims_summary,
)
from ...core.light_control import (
    get_all_lights as _core_get_all_lights,
    get_light_info as _core_get_light_info,
)
from ...core.stage_utils import get_selection_paths


# =============================================================================
# 场景总览
# =============================================================================

@tool(
    description=(
        "Return a concise text summary of the current USD scene, including up-axis, time range, "
        "scene bounds, cameras and all lights with their current attributes. "
        "Call this whenever you need to understand the scene context before other operations."
    ),
    permission=ToolPermission.READ_ONLY,
    category="scene",
    tags=["scene", "overview"],
)
def get_scene_summary() -> str:
    """Get a human/LLM-readable summary string of the scene."""
    return export_scene_info_for_llm()


@tool(
    description=(
        "Return the full scene information as a structured dict (cameras, lights, bounds, stage metadata). "
        "Prefer get_scene_summary for a compact text version; use this when you need structured data."
    ),
    permission=ToolPermission.READ_ONLY,
    category="scene",
    tags=["scene", "overview", "structured"],
)
def get_scene_info() -> Dict[str, Any]:
    """Get structured scene info."""
    return export_scene_info()


# =============================================================================
# 相机
# =============================================================================

@tool(
    description="List all cameras in the scene with their paths, focal lengths and positions.",
    permission=ToolPermission.READ_ONLY,
    category="scene",
    tags=["camera"],
)
def list_cameras() -> List[Dict[str, Any]]:
    """Return all cameras info."""
    return export_cameras_info()


@tool(
    description="Get detailed info for a single camera by its USD path.",
    permission=ToolPermission.READ_ONLY,
    category="scene",
    tags=["camera"],
)
def get_camera_info(camera_path: str) -> Dict[str, Any]:
    """
    Get one camera's info.

    Args:
        camera_path: USD path of the camera, e.g. ``/World/Cameras/MainCam``.
    """
    info = export_camera_info(camera_path)
    if info is None:
        return {"error": f"Camera not found: {camera_path}"}
    return info


# =============================================================================
# 灯光（查询类）
# =============================================================================

@tool(
    description=(
        "List ALL lights in the scene with type / path / position / EFFECTIVE attributes "
        "(intensity, color, temperature, exposure, etc.). Effective values include USD "
        "defaults that were never explicitly authored, so a freshly created light still "
        "reports `color: [1.0, 1.0, 1.0]` (white). Each attribute carries a "
        "`_<name>_authored` boolean flag indicating whether the value was set by the user. "
        "Always call this (or lighting.get_all_lights) before modifying lights."
    ),
    permission=ToolPermission.READ_ONLY,
    category="scene",
    tags=["light", "query"],
)
def list_lights() -> List[Dict[str, Any]]:
    """Return all lights info (effective values)."""
    return _core_get_all_lights(include_defaults=True)


@tool(
    description=(
        "Get detailed info for a single light by its USD path. Returns effective "
        "values (including defaults). Each attribute has a `_<name>_authored` flag."
    ),
    permission=ToolPermission.READ_ONLY,
    category="scene",
    tags=["light", "query"],
)
def get_light_details(light_path: str) -> Dict[str, Any]:
    """
    Get one light's detailed info (effective values, including defaults).

    Args:
        light_path: USD path of the light.
    """
    info = _core_get_light_info(light_path, include_defaults=True)
    if info is None or "error" in info:
        return info or {"error": f"Light not found: {light_path}"}
    return info


# =============================================================================
# 场景边界 & 几何
# =============================================================================

@tool(
    description="Return the world-space axis-aligned bounding box of the whole scene.",
    permission=ToolPermission.READ_ONLY,
    category="scene",
    tags=["bounds", "geometry"],
)
def get_scene_bounds() -> Dict[str, Any]:
    """Return scene bounds dict."""
    return export_scene_bounds()


@tool(
    description=(
        "Return a compact text overview of the scene geometry (mesh / xform counts and "
        "the first few top-level mesh prims)."
    ),
    permission=ToolPermission.READ_ONLY,
    category="scene",
    tags=["geometry", "overview"],
)
def get_geometry_overview() -> str:
    """Text overview of scene geometry."""
    return export_geometry_prims_summary()


# =============================================================================
# 选中
# =============================================================================

@tool(
    description="Return the list of currently selected prim paths in the viewport.",
    permission=ToolPermission.READ_ONLY,
    category="scene",
    tags=["selection"],
)
def get_selection() -> List[str]:
    """Selected prim paths."""
    return list(get_selection_paths())
