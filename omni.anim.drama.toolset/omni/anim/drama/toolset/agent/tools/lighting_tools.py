# -*- coding: utf-8 -*-
"""
Lighting 工具
=============

把 ``core.light_control`` 与 ``core.light_link`` 的操作暴露给 LLM。

权限等级约定：

- ``create_light`` / ``modify_light``：MUTATE（需审批）
- ``delete_light``：DESTRUCTIVE（默认禁用）
- ``create_light_link`` / ``remove_light_link``：MUTATE
- 查询类（``get_all_lights`` / ``get_light_link_info``）：READ_ONLY
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..tool_registry import tool, ToolPermission
from ...core.light_control import (
    create_light as _core_create_light,
    modify_light as _core_modify_light,
    delete_light as _core_delete_light,
    get_all_lights as _core_get_all_lights,
    get_light_info as _core_get_light_info,
    remove_relight_layer as _core_remove_relight_layer,
    toggle_relight_layer as _core_toggle_relight_layer,
    get_relight_layer_info as _core_get_relight_layer_info,
    LIGHT_TYPE_MAP,
)
from ...core.light_link import (
    create_light_link as _core_create_light_link,
    remove_light_link as _core_remove_light_link,
    get_light_link_targets as _core_get_light_link_targets,
    get_light_link_info as _core_get_light_link_info,
    create_shadow_link as _core_create_shadow_link,
)


_VALID_LIGHT_TYPES = list(LIGHT_TYPE_MAP.keys())


# =============================================================================
# 查询
# =============================================================================

@tool(
    description=(
        "Return all lights' structured info: path, type, position, and current effective "
        "attributes (intensity, color, temperature, exposure, radius/width/height/angle/length). "
        "Always returns the EFFECTIVE value of every attribute, including USD defaults that were "
        "never explicitly authored. Each attribute also has a `_<name>_authored` boolean field "
        "indicating whether the value was set explicitly. Note: a default-color light is white "
        "(color = [1.0, 1.0, 1.0]). Use this whenever you need to inspect lights before modifying."
    ),
    permission=ToolPermission.READ_ONLY,
    category="lighting",
    tags=["light", "query"],
)
def get_all_lights() -> List[Dict[str, Any]]:
    """Return all lights' info (effective values, including defaults)."""
    return _core_get_all_lights(include_defaults=True)


@tool(
    description=(
        "Get detailed info for a single light, including effective attribute values "
        "(intensity, color, temperature, exposure, transform). Defaults are included "
        "and each attribute carries a `_<name>_authored` flag."
    ),
    permission=ToolPermission.READ_ONLY,
    category="lighting",
    tags=["light", "query"],
)
def get_light_info(light_path: str) -> Dict[str, Any]:
    """
    Get one light's info (effective values, including defaults).

    Args:
        light_path: USD path of the light.
    """
    return _core_get_light_info(light_path, include_defaults=True)


# =============================================================================
# 创建 / 修改 / 删除
# =============================================================================

@tool(
    description=(
        "Create a new USD light. Writes into the active relight layer so it can be safely undone. "
        f"light_type must be one of: {', '.join(_VALID_LIGHT_TYPES)}."
    ),
    permission=ToolPermission.MUTATE,
    category="lighting",
    tags=["light", "create"],
    verify_with=["get_light_info", "list_lights"],
    phase_hint="act",
    parameters_schema={
        "type": "object",
        "properties": {
            "light_type": {
                "type": "string",
                "enum": _VALID_LIGHT_TYPES,
                "description": "USD light type.",
            },
            "name": {"type": "string", "description": "Light name (without path prefix)."},
            "parent_path": {
                "type": "string",
                "description": "Parent USD path. Default: /World/Lights",
                "default": "/World/Lights",
            },
            "intensity": {"type": "number", "description": "Light intensity (>=10 for most types)."},
            "color": {
                "type": "array",
                "items": {"type": "number"},
                "description": "RGB color, 3 floats in [0,1].",
            },
            "temperature": {"type": "number", "description": "Color temperature in Kelvin."},
            "exposure": {"type": "number", "description": "Exposure (EV stops)."},
            "translate": {
                "type": "array",
                "items": {"type": "number"},
                "description": "World-space translation [x, y, z].",
            },
            "rotate": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Euler rotation [rx, ry, rz] in degrees.",
            },
            "width": {"type": "number", "description": "Width (RectLight only)."},
            "height": {"type": "number", "description": "Height (RectLight only)."},
            "radius": {"type": "number", "description": "Radius (SphereLight / DiskLight / CylinderLight)."},
            "angle": {"type": "number", "description": "Cone angle (DistantLight)."},
            "length": {"type": "number", "description": "Length (CylinderLight)."},
        },
        "required": ["light_type", "name"],
    },
)
def create_light(
    light_type: str,
    name: str,
    parent_path: str = "/World/Lights",
    intensity: Optional[float] = None,
    color: Optional[List[float]] = None,
    temperature: Optional[float] = None,
    exposure: Optional[float] = None,
    translate: Optional[List[float]] = None,
    rotate: Optional[List[float]] = None,
    width: Optional[float] = None,
    height: Optional[float] = None,
    radius: Optional[float] = None,
    angle: Optional[float] = None,
    length: Optional[float] = None,
) -> Dict[str, Any]:
    """Create a new light."""
    attrs: Dict[str, Any] = {}
    for k, v in (
        ("intensity", intensity),
        ("color", color),
        ("temperature", temperature),
        ("exposure", exposure),
        ("width", width),
        ("height", height),
        ("radius", radius),
        ("angle", angle),
        ("length", length),
    ):
        if v is not None:
            attrs[k] = v

    transform: Dict[str, Any] = {}
    if translate is not None:
        transform["translate"] = translate
    if rotate is not None:
        transform["rotate"] = rotate

    success, msg, path = _core_create_light(
        light_type=light_type,
        name=name,
        parent_path=parent_path,
        transform=transform or None,
        attributes=attrs or None,
    )
    return {"success": success, "message": msg, "light_path": path}


@tool(
    description=(
        "Modify an existing light. Only provided fields will be changed. "
        "Writes into the active relight layer for safe undo."
    ),
    permission=ToolPermission.MUTATE,
    category="lighting",
    tags=["light", "modify"],
    verify_with=["get_light_info"],
    phase_hint="act",
    parameters_schema={
        "type": "object",
        "properties": {
            "light_path": {"type": "string", "description": "USD path of the light."},
            "intensity": {"type": "number"},
            "color": {"type": "array", "items": {"type": "number"}},
            "temperature": {"type": "number"},
            "exposure": {"type": "number"},
            "translate": {"type": "array", "items": {"type": "number"}},
            "rotate": {"type": "array", "items": {"type": "number"}},
            "width": {"type": "number"},
            "height": {"type": "number"},
            "radius": {"type": "number"},
            "angle": {"type": "number"},
            "length": {"type": "number"},
        },
        "required": ["light_path"],
    },
)
def modify_light(
    light_path: str,
    intensity: Optional[float] = None,
    color: Optional[List[float]] = None,
    temperature: Optional[float] = None,
    exposure: Optional[float] = None,
    translate: Optional[List[float]] = None,
    rotate: Optional[List[float]] = None,
    width: Optional[float] = None,
    height: Optional[float] = None,
    radius: Optional[float] = None,
    angle: Optional[float] = None,
    length: Optional[float] = None,
) -> Dict[str, Any]:
    """Modify an existing light."""
    attrs: Dict[str, Any] = {}
    for k, v in (
        ("intensity", intensity),
        ("color", color),
        ("temperature", temperature),
        ("exposure", exposure),
        ("width", width),
        ("height", height),
        ("radius", radius),
        ("angle", angle),
        ("length", length),
    ):
        if v is not None:
            attrs[k] = v

    transform: Dict[str, Any] = {}
    if translate is not None:
        transform["translate"] = translate
    if rotate is not None:
        transform["rotate"] = rotate

    if not attrs and not transform:
        return {"success": False, "message": "Nothing to modify; please specify at least one attribute or transform."}

    success, msg = _core_modify_light(
        light_path=light_path,
        transform=transform or None,
        attributes=attrs or None,
    )
    return {"success": success, "message": msg, "light_path": light_path}


@tool(
    description=(
        "Delete a light prim. This is IRREVERSIBLE at the stage level. "
        "Prefer modifying intensity/visibility if the user only wants to turn it off."
    ),
    permission=ToolPermission.DESTRUCTIVE,
    category="lighting",
    tags=["light", "delete"],
    verify_with=["list_lights", "inspect_prim"],
    phase_hint="act",
)
def delete_light(light_path: str) -> Dict[str, Any]:
    """
    Delete a light.

    Args:
        light_path: USD path of the light to delete.
    """
    success, msg = _core_delete_light(light_path)
    return {"success": success, "message": msg, "light_path": light_path}


# =============================================================================
# Relight Layer 管理
# =============================================================================

@tool(
    description=(
        "Get info about the current relight layer (whether exists, identifier). "
        "Light create/modify operations are written into this layer so they can be rolled back."
    ),
    permission=ToolPermission.READ_ONLY,
    category="lighting",
    tags=["relight", "layer"],
)
def get_relight_layer_info() -> Dict[str, Any]:
    """Relight layer info."""
    return _core_get_relight_layer_info()


@tool(
    description="Remove the current relight layer, restoring the original lighting.",
    permission=ToolPermission.MUTATE,
    category="lighting",
    tags=["relight", "layer"],
    verify_with=["get_relight_layer_info", "list_lights"],
    phase_hint="act",
)
def remove_relight_layer() -> Dict[str, Any]:
    """Remove relight layer, restoring original lights."""
    success, msg = _core_remove_relight_layer()
    return {"success": success, "message": msg}


@tool(
    description=(
        "Enable or disable (mute/unmute) the relight layer. "
        "Use this to A/B compare original vs. relit lighting without removing the layer."
    ),
    permission=ToolPermission.MUTATE,
    category="lighting",
    tags=["relight", "layer"],
    verify_with=["get_relight_layer_info"],
    phase_hint="act",
)
def toggle_relight_layer(enabled: bool) -> Dict[str, Any]:
    """
    Toggle the relight layer.

    Args:
        enabled: True to enable, False to mute.
    """
    success, msg = _core_toggle_relight_layer(bool(enabled))
    return {"success": success, "message": msg, "enabled": bool(enabled)}


# =============================================================================
# Light Link
# =============================================================================

@tool(
    description=(
        "Link (or un-link via excludes) a light to a geometry prim. "
        "include_mode=True means the geometry will be lit (added to includes). "
        "include_mode=False means the geometry will be excluded from this light."
    ),
    permission=ToolPermission.MUTATE,
    category="lighting",
    tags=["light-link"],
    verify_with=["get_light_link_info", "get_light_link_targets"],
    phase_hint="act",
)
def create_light_link(
    light_path: str,
    geometry_path: str,
    include_mode: bool = True,
) -> Dict[str, Any]:
    """
    Create light link.

    Args:
        light_path: USD path of the light.
        geometry_path: USD path of the geometry prim to include/exclude.
        include_mode: True = include, False = exclude.
    """
    success, msg = _core_create_light_link(
        light_path=light_path,
        geometry_path=geometry_path,
        include_mode=bool(include_mode),
    )
    return {"success": success, "message": msg}


@tool(
    description=(
        "Remove a light link (or all links if geometry_path is empty). "
        "When all links are cleared the light falls back to lighting everything."
    ),
    permission=ToolPermission.MUTATE,
    category="lighting",
    tags=["light-link"],
    verify_with=["get_light_link_info", "get_light_link_targets"],
    phase_hint="act",
)
def remove_light_link(
    light_path: str,
    geometry_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Remove light link.

    Args:
        light_path: USD path of the light.
        geometry_path: Specific geometry path to remove, or None to clear all.
    """
    success, msg = _core_remove_light_link(
        light_path=light_path,
        geometry_path=geometry_path or None,
    )
    return {"success": success, "message": msg}


@tool(
    description="List the includes and excludes geometry paths that the given light is linked to.",
    permission=ToolPermission.READ_ONLY,
    category="lighting",
    tags=["light-link", "query"],
)
def get_light_link_targets(light_path: str) -> Dict[str, Any]:
    """
    Light link targets.

    Args:
        light_path: USD path of the light.
    """
    includes, excludes = _core_get_light_link_targets(light_path)
    return {"light_path": light_path, "includes": list(includes), "excludes": list(excludes)}


@tool(
    description="Return full light-link collection info for a light (include_root, expansion_rule, includes, excludes).",
    permission=ToolPermission.READ_ONLY,
    category="lighting",
    tags=["light-link", "query"],
)
def get_light_link_info(light_path: str) -> Dict[str, Any]:
    """
    Light link info.

    Args:
        light_path: USD path of the light.
    """
    return _core_get_light_link_info(light_path)


@tool(
    description="Create a shadow-link between a light and a geometry prim (controls shadow casting).",
    permission=ToolPermission.MUTATE,
    category="lighting",
    tags=["shadow-link"],
    verify_with=["get_light_link_info"],
    phase_hint="act",
)
def create_shadow_link(
    light_path: str,
    geometry_path: str,
    include_mode: bool = True,
) -> Dict[str, Any]:
    """
    Create shadow link.

    Args:
        light_path: USD path of the light.
        geometry_path: USD path of the geometry.
        include_mode: True = cast shadow, False = no shadow.
    """
    success, msg = _core_create_shadow_link(
        light_path=light_path,
        geometry_path=geometry_path,
        include_mode=bool(include_mode),
    )
    return {"success": success, "message": msg}
