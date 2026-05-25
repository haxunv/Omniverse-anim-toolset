# -*- coding: utf-8 -*-
"""
USD Prim Introspection - USD 自省元工具
=======================================

让 Agent 在没有现成高层工具时，能直接"看见" USD stage 的真实状态：

- inspect_prim:           prim 的 type / schema / attributes / relationships / 子节点
- list_prims_by_type:     按类型筛选 prim（Mesh / Xform / Light / Camera / Skel...）
- list_animated_prims:    所有带 time samples 的 prim 与对应属性
- get_time_samples:       某个属性的关键帧采样列表（值 + 时间）
- get_stage_metadata:     stage 元信息（upAxis / metersPerUnit / timeCodesPerSecond / 时间区间）
- search_prim_paths:      按子串/通配符搜索 prim 路径

设计原则：
- 这些是 **READ_ONLY 元工具**，让 Agent 在面对未知场景结构时能自己探索；
- 返回值刻意做了截断（默认 50 条），避免一次塞爆 LLM context；
- 所有工具都对 stage 不存在 / prim 无效做了健壮处理，返回结构化错误而不是抛异常。
"""

from __future__ import annotations

import fnmatch
from typing import Any, Dict, List, Optional

from ..tool_registry import tool, ToolPermission
from ...core.stage_utils import get_stage, get_prim_at_path


# =============================================================================
# 内部工具
# =============================================================================

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 500


def _clamp_limit(limit: Optional[int]) -> int:
    if limit is None or limit <= 0:
        return _DEFAULT_LIMIT
    return min(int(limit), _MAX_LIMIT)


def _format_value(value: Any) -> Any:
    """把 USD 类型转成 JSON 可序列化的形式。"""
    try:
        from pxr import Gf, Vt, Sdf  # noqa: F401
    except Exception:
        return str(value)

    if value is None:
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    # Gf 向量类
    if hasattr(value, "__len__") and not isinstance(value, (bytes, bytearray)):
        try:
            return [_format_value(v) for v in value]
        except Exception:
            pass
    # 兜底
    return str(value)


def _summarize_attribute(attr) -> Dict[str, Any]:
    """概述单个 USD 属性。"""
    info: Dict[str, Any] = {
        "name": attr.GetName(),
        "type": str(attr.GetTypeName()),
        "authored": bool(attr.IsAuthored()),
        "has_time_samples": bool(attr.GetNumTimeSamples() > 0),
        "num_time_samples": int(attr.GetNumTimeSamples()),
    }
    try:
        if not info["has_time_samples"]:
            info["value"] = _format_value(attr.Get())
        else:
            info["value_at_default"] = _format_value(attr.Get())
    except Exception as e:
        info["value_error"] = str(e)
    return info


# =============================================================================
# inspect_prim
# =============================================================================

@tool(
    description=(
        "Deeply inspect a single USD prim: its type, applied schemas, all properties "
        "(attributes + relationships) with current values and authoring state, and a "
        "preview of its children. Use this whenever you need to understand a specific "
        "prim before reading or modifying it. Prefer this over guessing attribute names."
    ),
    permission=ToolPermission.READ_ONLY,
    category="introspection",
    tags=["usd", "prim", "meta"],
    phase_hint="gather",
)
def inspect_prim(
    prim_path: str,
    include_inherited: bool = True,
    max_attributes: int = 60,
    max_children: int = 20,
) -> Dict[str, Any]:
    """
    Inspect a USD prim at the given path.

    Args:
        prim_path: USD path, e.g. ``/World/Cameras/MainCam``.
        include_inherited: If False, only show authored attributes.
        max_attributes: Truncate attribute list to this many (default 60).
        max_children: Truncate children list to this many (default 20).
    """
    stage = get_stage()
    if stage is None:
        return {"error": "No stage is currently open."}

    prim = get_prim_at_path(prim_path)
    if prim is None:
        return {"error": f"Prim not found: {prim_path}"}

    # 基本信息
    info: Dict[str, Any] = {
        "path": prim_path,
        "type": prim.GetTypeName(),
        "is_active": bool(prim.IsActive()),
        "is_loaded": bool(prim.IsLoaded()),
        "is_instance": bool(prim.IsInstance()),
        "is_instanceable": bool(prim.IsInstanceable()),
        "applied_schemas": list(prim.GetAppliedSchemas()),
        "kind": "",
    }
    try:
        from pxr import Usd, UsdGeom  # noqa
        model_api = Usd.ModelAPI(prim)
        info["kind"] = str(model_api.GetKind() or "")
    except Exception:
        pass

    # variants
    try:
        vsets = prim.GetVariantSets()
        names = list(vsets.GetNames())
        if names:
            info["variant_sets"] = {
                n: {
                    "selection": vsets.GetVariantSet(n).GetVariantSelection(),
                    "options": list(vsets.GetVariantSet(n).GetVariantNames()),
                }
                for n in names
            }
    except Exception:
        pass

    # 属性
    attrs = []
    try:
        all_attrs = prim.GetAttributes() if include_inherited else prim.GetAuthoredAttributes()
    except Exception:
        all_attrs = []
    for a in all_attrs[:max_attributes]:
        try:
            attrs.append(_summarize_attribute(a))
        except Exception as e:
            attrs.append({"name": a.GetName(), "error": str(e)})
    info["attributes"] = attrs
    info["attributes_truncated"] = len(all_attrs) > max_attributes
    info["total_attributes"] = len(all_attrs)

    # relationships
    rels: List[Dict[str, Any]] = []
    try:
        for rel in prim.GetRelationships():
            try:
                targets = [str(t) for t in rel.GetTargets()]
            except Exception:
                targets = []
            rels.append({"name": rel.GetName(), "targets": targets})
    except Exception:
        pass
    info["relationships"] = rels

    # 子节点
    try:
        children = list(prim.GetChildren())
    except Exception:
        children = []
    info["num_children"] = len(children)
    info["children"] = [
        {"path": str(c.GetPath()), "type": c.GetTypeName()} for c in children[:max_children]
    ]
    info["children_truncated"] = len(children) > max_children

    return info


# =============================================================================
# list_prims_by_type
# =============================================================================

@tool(
    description=(
        "List all prims in the current stage that match a given USD type. "
        "Common types: 'Mesh', 'Xform', 'Camera', 'SphereLight', 'RectLight', "
        "'DistantLight', 'DomeLight', 'DiskLight', 'CylinderLight', 'Scope', "
        "'SkelRoot', 'Skeleton', 'Material', 'Shader'. Use this to discover what "
        "the scene contains before deciding which prims to act on."
    ),
    permission=ToolPermission.READ_ONLY,
    category="introspection",
    tags=["usd", "prim", "meta"],
    phase_hint="gather",
)
def list_prims_by_type(
    type_name: str,
    under_path: str = "/",
    limit: int = _DEFAULT_LIMIT,
) -> Dict[str, Any]:
    """
    List prims by type.

    Args:
        type_name: USD prim type (e.g. 'Mesh', 'RectLight', 'Camera').
        under_path: Only search under this prim path (default '/').
        limit: Max results to return (default 50, hard cap 500).
    """
    stage = get_stage()
    if stage is None:
        return {"error": "No stage is currently open."}

    cap = _clamp_limit(limit)
    root = stage.GetPrimAtPath(under_path) if under_path and under_path != "/" else stage.GetPseudoRoot()
    if not root or not root.IsValid():
        return {"error": f"Prim not found at under_path: {under_path}"}

    matches: List[Dict[str, Any]] = []
    try:
        from pxr import Usd
        it = iter(Usd.PrimRange(root))
        for p in it:
            if p.IsPseudoRoot():
                continue
            if p.GetTypeName() == type_name:
                matches.append({"path": str(p.GetPath()), "name": p.GetName()})
                if len(matches) >= cap:
                    break
    except Exception as e:
        return {"error": f"Failed to traverse stage: {e}"}

    return {
        "type": type_name,
        "under_path": under_path,
        "count": len(matches),
        "truncated": len(matches) >= cap,
        "prims": matches,
    }


# =============================================================================
# list_animated_prims
# =============================================================================

@tool(
    description=(
        "List all prims in the stage that have at least one attribute with USD time "
        "samples (i.e. real animation, not constant values). Returns each prim's path, "
        "type, the animated attribute names, and per-attribute number of samples and "
        "min/max time. Use this to understand what is animated in the current scene."
    ),
    permission=ToolPermission.READ_ONLY,
    category="introspection",
    tags=["usd", "animation", "meta"],
    phase_hint="gather",
)
def list_animated_prims(
    under_path: str = "/",
    limit: int = _DEFAULT_LIMIT,
) -> Dict[str, Any]:
    """
    List animated prims.

    Args:
        under_path: Only search under this prim path (default '/').
        limit: Max prims to return (default 50, hard cap 500).
    """
    stage = get_stage()
    if stage is None:
        return {"error": "No stage is currently open."}

    cap = _clamp_limit(limit)
    root = stage.GetPrimAtPath(under_path) if under_path and under_path != "/" else stage.GetPseudoRoot()
    if not root or not root.IsValid():
        return {"error": f"Prim not found at under_path: {under_path}"}

    animated: List[Dict[str, Any]] = []
    try:
        from pxr import Usd
        for p in Usd.PrimRange(root):
            if p.IsPseudoRoot():
                continue
            anim_attrs = []
            for a in p.GetAuthoredAttributes():
                try:
                    n = a.GetNumTimeSamples()
                except Exception:
                    n = 0
                if n <= 0:
                    continue
                samples = a.GetTimeSamples() or []
                anim_attrs.append({
                    "name": a.GetName(),
                    "type": str(a.GetTypeName()),
                    "num_samples": int(n),
                    "first_time": float(samples[0]) if samples else None,
                    "last_time": float(samples[-1]) if samples else None,
                })
            if anim_attrs:
                animated.append({
                    "path": str(p.GetPath()),
                    "type": p.GetTypeName(),
                    "animated_attributes": anim_attrs,
                })
            if len(animated) >= cap:
                break
    except Exception as e:
        return {"error": f"Failed to scan stage: {e}"}

    return {
        "under_path": under_path,
        "count": len(animated),
        "truncated": len(animated) >= cap,
        "prims": animated,
    }


# =============================================================================
# get_time_samples
# =============================================================================

@tool(
    description=(
        "Get the time-sample list of a single attribute on a prim: every authored "
        "(time, value) pair plus interpolation info. Use this to understand the "
        "exact animation curve before retiming or editing keyframes. Returns at most "
        "200 samples by default; if more exist, sets `truncated=true`."
    ),
    permission=ToolPermission.READ_ONLY,
    category="introspection",
    tags=["usd", "animation", "meta"],
    phase_hint="gather",
)
def get_time_samples(
    prim_path: str,
    attribute_name: str,
    max_samples: int = 200,
) -> Dict[str, Any]:
    """
    Get time samples for an attribute.

    Args:
        prim_path: USD prim path.
        attribute_name: Attribute name (e.g. 'xformOp:translate', 'intensity').
        max_samples: Max samples to return (default 200, hard cap 2000).
    """
    stage = get_stage()
    if stage is None:
        return {"error": "No stage is currently open."}

    prim = get_prim_at_path(prim_path)
    if prim is None:
        return {"error": f"Prim not found: {prim_path}"}

    attr = prim.GetAttribute(attribute_name)
    if not attr or not attr.IsValid():
        return {"error": f"Attribute not found: {prim_path}.{attribute_name}"}

    cap = max(1, min(int(max_samples), 2000))

    try:
        times = list(attr.GetTimeSamples() or [])
    except Exception as e:
        return {"error": f"GetTimeSamples failed: {e}"}

    truncated = len(times) > cap
    times = times[:cap]

    samples: List[Dict[str, Any]] = []
    for t in times:
        try:
            v = attr.Get(t)
            samples.append({"time": float(t), "value": _format_value(v)})
        except Exception as e:
            samples.append({"time": float(t), "error": str(e)})

    return {
        "path": prim_path,
        "attribute": attribute_name,
        "type": str(attr.GetTypeName()),
        "num_total_samples": int(attr.GetNumTimeSamples()),
        "num_returned": len(samples),
        "truncated": truncated,
        "samples": samples,
    }


# =============================================================================
# get_stage_metadata
# =============================================================================

@tool(
    description=(
        "Return stage-level metadata: upAxis (Y/Z), metersPerUnit, "
        "timeCodesPerSecond, framesPerSecond, startTimeCode, endTimeCode, "
        "default prim path, and the list of layers in the layer stack with their "
        "identifier and mute state. Always call this near the start of any task "
        "involving units, frame ranges, or coordinate conventions."
    ),
    permission=ToolPermission.READ_ONLY,
    category="introspection",
    tags=["usd", "stage", "meta"],
    phase_hint="gather",
)
def get_stage_metadata() -> Dict[str, Any]:
    """Return stage-level metadata + layer stack overview."""
    stage = get_stage()
    if stage is None:
        return {"error": "No stage is currently open."}

    info: Dict[str, Any] = {}
    try:
        from pxr import UsdGeom
        info["up_axis"] = UsdGeom.GetStageUpAxis(stage)
        info["meters_per_unit"] = float(UsdGeom.GetStageMetersPerUnit(stage))
    except Exception:
        pass

    try:
        info["time_codes_per_second"] = float(stage.GetTimeCodesPerSecond())
    except Exception:
        pass
    try:
        info["frames_per_second"] = float(stage.GetFramesPerSecond())
    except Exception:
        pass
    try:
        info["start_time_code"] = float(stage.GetStartTimeCode())
        info["end_time_code"] = float(stage.GetEndTimeCode())
    except Exception:
        pass

    try:
        default_prim = stage.GetDefaultPrim()
        info["default_prim"] = str(default_prim.GetPath()) if default_prim and default_prim.IsValid() else ""
    except Exception:
        info["default_prim"] = ""

    layers: List[Dict[str, Any]] = []
    try:
        root_layer = stage.GetRootLayer()
        for sublayer_id in (root_layer.subLayerPaths or []):
            try:
                from pxr import Sdf
                sub = Sdf.Layer.FindOrOpen(sublayer_id)
                layers.append({
                    "identifier": sublayer_id,
                    "muted": bool(stage.IsLayerMuted(sublayer_id)),
                    "anonymous": bool(sub.anonymous) if sub else None,
                })
            except Exception:
                layers.append({"identifier": sublayer_id, "muted": None})
        info["root_layer"] = root_layer.identifier
        info["sublayers"] = layers
    except Exception as e:
        info["layer_stack_error"] = str(e)

    try:
        session = stage.GetSessionLayer()
        info["session_layer"] = session.identifier if session else ""
    except Exception:
        pass

    return info


# =============================================================================
# search_prim_paths
# =============================================================================

@tool(
    description=(
        "Search prim paths in the stage by case-insensitive substring or shell-style "
        "wildcard (?, *, [seq]). Use this when the user names a prim partially "
        "(e.g. 'main camera', '*Light*'). Returns matching paths plus their types."
    ),
    permission=ToolPermission.READ_ONLY,
    category="introspection",
    tags=["usd", "prim", "search"],
    phase_hint="gather",
)
def search_prim_paths(
    query: str,
    use_wildcard: bool = False,
    under_path: str = "/",
    limit: int = _DEFAULT_LIMIT,
) -> Dict[str, Any]:
    """
    Search prim paths.

    Args:
        query: Substring or wildcard pattern to match against the prim PATH.
        use_wildcard: If True, treat `query` as fnmatch pattern; else case-insensitive substring.
        under_path: Only search under this prim path (default '/').
        limit: Max results to return.
    """
    stage = get_stage()
    if stage is None:
        return {"error": "No stage is currently open."}

    if not query:
        return {"error": "query must be non-empty."}

    cap = _clamp_limit(limit)
    root = stage.GetPrimAtPath(under_path) if under_path and under_path != "/" else stage.GetPseudoRoot()
    if not root or not root.IsValid():
        return {"error": f"Prim not found at under_path: {under_path}"}

    needle = query.lower()
    matches: List[Dict[str, Any]] = []
    try:
        from pxr import Usd
        for p in Usd.PrimRange(root):
            if p.IsPseudoRoot():
                continue
            path_str = str(p.GetPath())
            hit = (
                fnmatch.fnmatchcase(path_str, query) if use_wildcard
                else (needle in path_str.lower())
            )
            if hit:
                matches.append({"path": path_str, "type": p.GetTypeName()})
                if len(matches) >= cap:
                    break
    except Exception as e:
        return {"error": f"Failed to traverse stage: {e}"}

    return {
        "query": query,
        "use_wildcard": bool(use_wildcard),
        "count": len(matches),
        "truncated": len(matches) >= cap,
        "matches": matches,
    }
