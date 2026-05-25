# -*- coding: utf-8 -*-
"""
Layout Tools - SceneGraph -> stage xforms
=========================================

This module turns the SceneGraph produced by ``describe_reference_image`` into
concrete USD operations. It deliberately splits decisions across three small
tools so each step is auditable in the agent's tool-call log:

- ``pick_best_asset``       READ_ONLY: commit one candidate per subject.
- ``propose_layout``        READ_ONLY: rule-based translate / rotate / scale
                            per subject, no LLM coordinate guesswork.
- ``create_camera_for_view`` MUTATE:   build a camera matching the SceneGraph
                            framing (with undo group support).

The SceneGraph schema is documented in ``vision_tools.describe_reference_image``.

Coordinate convention (forced, documented):

- Y-up stage: camera default at +Z looking towards origin. Forward (toward
  camera) = +Z, right = +X.
- Z-up stage: camera default at -Y looking towards origin. Forward (toward
  camera) = -Y, right = +X.
"""

from __future__ import annotations

import math
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from ..tool_registry import ToolPermission, tool
from ...core.scene_exporter import export_scene_bounds
from ...core.stage_utils import get_stage, run_on_main_thread


SETTINGS_PREFIX = "/exts/omni.anim.drama.toolset/agent/layout"

# 9-grid in (right_ratio, forward_ratio) where forward = "toward camera".
_GRID = {
    "front-left":   (-0.4, +0.4),
    "front-center": ( 0.0, +0.4),
    "front-right":  (+0.4, +0.4),
    "center-left":  (-0.4,  0.0),
    "center":       ( 0.0,  0.0),
    "center-right": (+0.4,  0.0),
    "back-left":    (-0.4, -0.4),
    "back-center":  ( 0.0, -0.4),
    "back-right":   (+0.4, -0.4),
}

_SCALE_FACTOR = {
    "small": 0.5,
    "human": 1.0,
    "large": 2.0,
    "xl": 4.0,
}

_FACING_YAW = {
    "camera": 0.0,
    "left":   +90.0,
    "right":  -90.0,
    "away":   180.0,
}

_FRAMING_DISTANCE = {
    "close":  0.7,
    "medium": 1.0,
    "wide":   1.3,
}


# =============================================================================
# Settings helpers
# =============================================================================

def _get_setting(path: str, default: Any = None) -> Any:
    try:
        import carb.settings  # type: ignore

        value = carb.settings.get_settings().get(path)
        return default if value in (None, "") else value
    except Exception:
        return default


def _get_layout_config() -> Dict[str, Any]:
    spacing_factor = _get_setting(f"{SETTINGS_PREFIX}/spacing_factor") or 1.2
    default_radius = _get_setting(f"{SETTINGS_PREFIX}/default_stage_radius") or 500.0
    up_axis_pref = (_get_setting(f"{SETTINGS_PREFIX}/up_axis") or "auto").upper()
    if up_axis_pref not in ("AUTO", "Y", "Z"):
        up_axis_pref = "AUTO"
    try:
        spacing_factor = float(spacing_factor)
    except Exception:
        spacing_factor = 1.2
    try:
        default_radius = float(default_radius)
    except Exception:
        default_radius = 500.0
    return {
        "spacing_factor": max(1.0, spacing_factor),
        "default_stage_radius": max(1.0, default_radius),
        "up_axis_pref": up_axis_pref,
    }


# =============================================================================
# Stage probing
# =============================================================================

def _detect_up_axis(pref: str) -> str:
    if pref in ("Y", "Z"):
        return pref
    try:
        from pxr import UsdGeom

        stage = get_stage()
        if stage is not None:
            axis = UsdGeom.GetStageUpAxis(stage)
            return "Z" if str(axis).upper() == "Z" else "Y"
    except Exception:
        pass
    return "Y"


def _stage_radius(default_radius: float) -> float:
    bounds = export_scene_bounds() or {}
    size = bounds.get("size") or []
    if isinstance(size, list) and len(size) == 3:
        try:
            half = max(float(size[0]), float(size[1]), float(size[2])) / 2.0
            if half > 0.5:
                return half
        except Exception:
            pass
    return default_radius


# =============================================================================
# Helpers
# =============================================================================

def _make_valid_identifier(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_]+", "_", name or "Subject").strip("_")
    if not name:
        name = "Subject"
    if name[0].isdigit():
        name = f"Subject_{name}"
    return name


def _grid_to_world(rough_position: str, up_axis: str, radius: float) -> Tuple[float, float, float]:
    right_ratio, forward_ratio = _GRID.get(rough_position, _GRID["center"])
    rx = right_ratio * radius
    fz = forward_ratio * radius
    if up_axis == "Y":
        return (rx, 0.0, fz)
    # Z-up: forward = -Y towards camera at -Y
    return (rx, -fz, 0.0)


def _yaw_axis(up_axis: str) -> str:
    return "Y" if up_axis == "Y" else "Z"


def _planar_components(translate: Tuple[float, float, float], up_axis: str) -> Tuple[float, float]:
    if up_axis == "Y":
        return (translate[0], translate[2])
    return (translate[0], translate[1])


def _set_planar(translate: Tuple[float, float, float], up_axis: str, x: float, y: float) -> Tuple[float, float, float]:
    if up_axis == "Y":
        return (x, translate[1], y)
    return (x, y, translate[2])


def _greedy_push(
    placements: List[Dict[str, Any]],
    up_axis: str,
    spacing_factor: float,
    iterations: int = 5,
) -> None:
    """In-place collision separation on the ground plane."""
    n = len(placements)
    if n < 2:
        return

    for _ in range(iterations):
        moved = False
        for i in range(n):
            for j in range(i + 1, n):
                ti = placements[i]["translate"]
                tj = placements[j]["translate"]
                xi, yi = _planar_components(ti, up_axis)
                xj, yj = _planar_components(tj, up_axis)
                dx = xi - xj
                dy = yi - yj
                d = math.sqrt(dx * dx + dy * dy)
                ri = placements[i]["radius"]
                rj = placements[j]["radius"]
                min_d = (ri + rj) * spacing_factor
                if d < min_d - 1e-3:
                    if d < 1e-4:
                        # Same spot: nudge along x.
                        ux, uy = 1.0, 0.0
                        d = 1e-4
                    else:
                        ux, uy = dx / d, dy / d
                    push = (min_d - d) / 2.0
                    placements[i]["translate"] = _set_planar(ti, up_axis, xi + ux * push, yi + uy * push)
                    placements[j]["translate"] = _set_planar(tj, up_axis, xj - ux * push, yj - uy * push)
                    moved = True
        if not moved:
            return


# =============================================================================
# pick_best_asset
# =============================================================================

@tool(
    description=(
        "Commit one asset candidate as the chosen pick for a subject. The agent "
        "passes the candidates returned by search_usd_assets together with "
        "chosen_index (or chosen_url) and a short reason. The tool just records "
        "the choice in a structured form so the tool-call log shows what was "
        "selected and why; downstream tools should use the returned chosen_url."
    ),
    permission=ToolPermission.READ_ONLY,
    category="layout",
    tags=["asset", "pick", "selector"],
    phase_hint="gather",
    parameters_schema={
        "type": "object",
        "properties": {
            "subject_label": {
                "type": "string",
                "description": "Subject label this pick is for (e.g. 'wooden chair').",
            },
            "candidates": {
                "type": "array",
                "items": {"type": "object"},
                "description": "List of candidate dicts (e.g. from search_usd_assets.results); each must have 'url'.",
            },
            "chosen_index": {
                "type": "integer",
                "description": "Index into candidates of the chosen one (default 0).",
            },
            "chosen_url": {
                "type": "string",
                "description": "Alternative to chosen_index: explicit asset URL. Must match a candidate.url.",
            },
            "reason": {
                "type": "string",
                "description": "One-line rationale shown in the tool-call log.",
            },
        },
        "required": ["subject_label", "candidates"],
    },
)
def pick_best_asset(
    subject_label: str,
    candidates: List[Dict[str, Any]],
    chosen_index: int = 0,
    chosen_url: str = "",
    reason: str = "",
) -> Dict[str, Any]:
    """Commit one candidate per subject, returning structured pick info."""
    if not isinstance(candidates, list) or not candidates:
        return {"ok": False, "error": "candidates must be a non-empty list"}

    chosen: Optional[Dict[str, Any]] = None
    chosen_url = (chosen_url or "").strip()

    if chosen_url:
        for item in candidates:
            if isinstance(item, dict) and str(item.get("url", "")) == chosen_url:
                chosen = item
                break
        if chosen is None:
            return {
                "ok": False,
                "error": f"chosen_url not found among {len(candidates)} candidates",
                "chosen_url": chosen_url,
            }
    else:
        try:
            idx = int(chosen_index)
        except Exception:
            idx = 0
        if idx < 0 or idx >= len(candidates):
            return {
                "ok": False,
                "error": f"chosen_index {idx} out of range [0..{len(candidates) - 1}]",
            }
        candidate = candidates[idx]
        if not isinstance(candidate, dict):
            return {"ok": False, "error": f"candidate at index {idx} is not an object"}
        chosen = candidate

    url = str(chosen.get("url", "")).strip()
    if not url:
        return {"ok": False, "error": "Chosen candidate has no 'url' field"}

    return {
        "ok": True,
        "subject_label": subject_label,
        "chosen_index": chosen_index,
        "chosen_url": url,
        "chosen": {k: chosen[k] for k in ("url", "name", "title", "description", "bbox_dimension") if k in chosen},
        "reason": reason,
        "candidate_count": len(candidates),
        "next_action_hint": (
            "Pass chosen_url into reference_usd_asset, together with the translate/rotate/scale "
            "from propose_layout for this subject."
        ),
    }


# =============================================================================
# propose_layout
# =============================================================================

@tool(
    description=(
        "Convert a SceneGraph (from describe_reference_image) into concrete "
        "translate / rotate_y / scale per subject, using a deterministic 9-grid "
        "rule plus a greedy AABB collision push. Read-only; does NOT touch the "
        "stage. Pass each item to reference_usd_asset(translation=..., "
        "rotation=..., scale=...). Honors current stage up-axis and meters. "
        "If the stage has no geometry, falls back to the configured default "
        "stage radius."
    ),
    permission=ToolPermission.READ_ONLY,
    category="layout",
    tags=["layout", "scene-graph", "xform", "deterministic"],
    phase_hint="gather",
    parameters_schema={
        "type": "object",
        "properties": {
            "scene_graph": {
                "type": "object",
                "description": "SceneGraph dict from describe_reference_image.scene_graph (subjects[*]).",
            },
            "stage_radius": {
                "type": "number",
                "description": "Optional override for stage radius (in stage units). Empty = auto detect from scene bounds.",
            },
            "prim_path_root": {
                "type": "string",
                "description": "Prefix for proposed prim paths. Default '/World/Assets'.",
            },
        },
        "required": ["scene_graph"],
    },
)
def propose_layout(
    scene_graph: Dict[str, Any],
    stage_radius: Optional[float] = None,
    prim_path_root: str = "/World/Assets",
) -> Dict[str, Any]:
    """Rule-based xform proposer for SceneGraph subjects."""
    cfg = _get_layout_config()
    up_axis = _detect_up_axis(cfg["up_axis_pref"])
    radius = float(stage_radius) if stage_radius is not None else _stage_radius(cfg["default_stage_radius"])
    if radius <= 0:
        radius = cfg["default_stage_radius"]

    if not isinstance(scene_graph, dict):
        return {"ok": False, "error": "scene_graph must be an object"}

    subjects = scene_graph.get("subjects") or []
    if not isinstance(subjects, list):
        subjects = []

    if not subjects:
        return {
            "ok": True,
            "up_axis": up_axis,
            "stage_radius": radius,
            "placements": [],
            "warning": "scene_graph.subjects is empty; nothing to lay out.",
        }

    yaw_axis = _yaw_axis(up_axis)
    prim_path_root = (prim_path_root or "/World/Assets").rstrip("/") or "/World/Assets"

    placements: List[Dict[str, Any]] = []
    used_paths: set = set()

    for index, subject in enumerate(subjects):
        if not isinstance(subject, dict):
            continue
        label = str(subject.get("label") or f"Subject_{index}")
        rough_position = str(subject.get("rough_position") or "center")
        rough_scale = str(subject.get("rough_scale") or "human")
        facing = str(subject.get("facing") or "camera")

        scale_mul = _SCALE_FACTOR.get(rough_scale, 1.0)
        translate = _grid_to_world(rough_position, up_axis, radius)

        rotation = [0.0, 0.0, 0.0]
        yaw = _FACING_YAW.get(facing, 0.0)
        if yaw_axis == "Y":
            rotation[1] = yaw
        else:
            rotation[2] = yaw

        scale = [scale_mul, scale_mul, scale_mul]

        # Heuristic radius: tie collision footprint to scene radius and the
        # subject's relative scale so xl objects push small ones out properly.
        bbox_radius = max(0.05 * radius, scale_mul * 0.15 * radius)

        base_id = _make_valid_identifier(label)
        prim_path = f"{prim_path_root}/{base_id}"
        suffix = 1
        while prim_path in used_paths:
            suffix += 1
            prim_path = f"{prim_path_root}/{base_id}_{suffix:02d}"
        used_paths.add(prim_path)

        placements.append(
            {
                "subject_index": index,
                "label": label,
                "prim_path": prim_path,
                "translate": translate,
                "rotation": rotation,
                "scale": scale,
                "rough_position": rough_position,
                "rough_scale": rough_scale,
                "facing": facing,
                "radius": bbox_radius,
            }
        )

    _greedy_push(placements, up_axis, cfg["spacing_factor"])

    out_placements: List[Dict[str, Any]] = []
    for p in placements:
        out_placements.append(
            {
                "subject_index": p["subject_index"],
                "label": p["label"],
                "prim_path": p["prim_path"],
                "translate": [round(float(v), 4) for v in p["translate"]],
                "rotation": [round(float(v), 4) for v in p["rotation"]],
                "scale": [round(float(v), 4) for v in p["scale"]],
                "rough_position": p["rough_position"],
                "rough_scale": p["rough_scale"],
                "facing": p["facing"],
            }
        )

    return {
        "ok": True,
        "up_axis": up_axis,
        "stage_radius": round(radius, 4),
        "spacing_factor": cfg["spacing_factor"],
        "placement_count": len(out_placements),
        "placements": out_placements,
        "next_action_hint": (
            "For each placement, call reference_usd_asset(asset_url=<chosen_url from pick_best_asset>, "
            "prim_path=placement.prim_path, translation=placement.translate, rotation=placement.rotation, "
            "scale=placement.scale)."
        ),
    }


# =============================================================================
# create_camera_for_view
# =============================================================================

def _build_lookat_matrix(eye, target, world_up):
    """Right-handed look-at: USD/OpenGL camera convention (forward = -Z, up = +Y)."""
    from pxr import Gf

    eye_v = Gf.Vec3d(*eye)
    target_v = Gf.Vec3d(*target)
    world_up_v = Gf.Vec3d(*world_up)

    forward = target_v - eye_v
    if forward.GetLength() < 1e-6:
        forward = Gf.Vec3d(0, 0, -1)
    forward.Normalize()

    right = Gf.Cross(forward, world_up_v)
    if right.GetLength() < 1e-6:
        # Pathological: forward parallel to world_up; pick an arbitrary right.
        right = Gf.Vec3d(1, 0, 0)
    right.Normalize()

    cam_up = Gf.Cross(right, forward)
    cam_up.Normalize()

    matrix = Gf.Matrix4d()
    matrix.SetIdentity()
    matrix.SetRow(0, Gf.Vec4d(right[0], right[1], right[2], 0))
    matrix.SetRow(1, Gf.Vec4d(cam_up[0], cam_up[1], cam_up[2], 0))
    matrix.SetRow(2, Gf.Vec4d(-forward[0], -forward[1], -forward[2], 0))
    matrix.SetTranslateOnly(eye_v)
    return matrix


def _ensure_xform_ancestors(stage, prim_path: str) -> None:
    from pxr import Sdf, UsdGeom

    path = Sdf.Path(prim_path)
    ancestors = []
    parent = path.GetParentPath()
    while parent and str(parent) not in ("", "/"):
        ancestors.append(parent)
        parent = parent.GetParentPath()
    for ancestor in reversed(ancestors):
        if not stage.GetPrimAtPath(ancestor).IsValid():
            UsdGeom.Xform.Define(stage, ancestor)


def _unique_camera_path(stage, base: str) -> str:
    if not stage.GetPrimAtPath(base).IsValid():
        return base
    index = 1
    while True:
        candidate = f"{base}_{index:02d}"
        if not stage.GetPrimAtPath(candidate).IsValid():
            return candidate
        index += 1
        if index > 999:
            return f"{base}_{os.getpid()}"


@tool(
    description=(
        "Create a USD camera matching a SceneGraph.camera spec (pitch / framing / "
        "fov_estimate_deg). The camera is positioned so the stage's bounds (or "
        "the configured default radius if the stage is empty) fits the framing, "
        "with the requested pitch, looking at the framing target's center. "
        "Wrapped in omni.kit.undo.group so Ctrl+Z reverts the whole creation."
    ),
    permission=ToolPermission.MUTATE,
    category="layout",
    tags=["camera", "view", "framing"],
    phase_hint="act",
    verify_with=["list_cameras", "inspect_prim"],
    parameters_schema={
        "type": "object",
        "properties": {
            "camera_spec": {
                "type": "object",
                "description": "Dict with optional angle_deg_pitch, framing (close|medium|wide), fov_estimate_deg.",
            },
            "framing_target_path": {
                "type": "string",
                "description": "Prim to frame on; if invalid, frames world center. Default '/World/Assets'.",
            },
            "camera_path": {
                "type": "string",
                "description": "Where to define the camera. Default '/World/Cameras/AnimeAgent_Camera'.",
            },
            "select_new": {
                "type": "boolean",
                "description": "Select the new camera in the viewport when created. Default true.",
            },
        },
    },
)
def create_camera_for_view(
    camera_spec: Optional[Dict[str, Any]] = None,
    framing_target_path: str = "/World/Assets",
    camera_path: str = "/World/Cameras/AnimeAgent_Camera",
    select_new: bool = True,
) -> Dict[str, Any]:
    """
    Create a UsdGeom.Camera matching a SceneGraph camera spec.
    """
    stage = get_stage()
    if stage is None:
        return {"ok": False, "error": "No USD stage is currently open."}

    cfg = _get_layout_config()
    up_axis = _detect_up_axis(cfg["up_axis_pref"])

    spec = camera_spec or {}
    try:
        pitch_deg = float(spec.get("angle_deg_pitch", 0.0))
    except Exception:
        pitch_deg = 0.0
    try:
        fov_deg = float(spec.get("fov_estimate_deg", 35.0))
    except Exception:
        fov_deg = 35.0
    framing = str(spec.get("framing", "medium")).lower()
    framing_mult = _FRAMING_DISTANCE.get(framing, _FRAMING_DISTANCE["medium"])

    # Decide framing target center.
    bounds = export_scene_bounds() or {}
    target_center = (0.0, 0.0, 0.0)
    radius = _stage_radius(cfg["default_stage_radius"])
    try:
        from pxr import Sdf, Usd, UsdGeom

        target_prim = stage.GetPrimAtPath(framing_target_path) if framing_target_path else None
        if target_prim and target_prim.IsValid():
            imageable = UsdGeom.Imageable(target_prim)
            target_bounds = imageable.ComputeWorldBound(Usd.TimeCode.Default(), UsdGeom.Tokens.default_)
            bbox = target_bounds.ComputeAlignedBox()
            if not bbox.IsEmpty():
                center = (bbox.GetMin() + bbox.GetMax()) / 2.0
                size = bbox.GetMax() - bbox.GetMin()
                target_center = (center[0], center[1], center[2])
                radius = max(0.5 * radius, max(size[0], size[1], size[2]) / 2.0)
        elif bounds:
            center = bounds.get("center")
            if isinstance(center, list) and len(center) == 3:
                target_center = (float(center[0]), float(center[1]), float(center[2]))
    except Exception:
        pass

    fov_rad = math.radians(max(5.0, min(fov_deg, 120.0)))
    distance = (radius / max(math.tan(fov_rad / 2.0), 1e-3)) * framing_mult
    if distance <= 0:
        distance = radius * 2.0

    pitch_rad = math.radians(pitch_deg)
    horiz = distance * math.cos(pitch_rad)
    height = -distance * math.sin(pitch_rad)  # negative pitch -> raised camera

    if up_axis == "Y":
        eye = (
            target_center[0],
            target_center[1] + height,
            target_center[2] + horiz,
        )
        world_up = (0.0, 1.0, 0.0)
    else:  # Z-up
        eye = (
            target_center[0],
            target_center[1] - horiz,
            target_center[2] + height,
        )
        world_up = (0.0, 0.0, 1.0)

    matrix = _build_lookat_matrix(eye, target_center, world_up)

    # Focal length from horizontal FOV, assuming 36mm sensor (matches USD default
    # horizontalAperture=20.955mm but Kit cameras default to 36mm aperture).
    sensor_mm = 36.0
    focal_length = (sensor_mm / 2.0) / math.tan(fov_rad / 2.0)

    # USD writes (Camera.Define / AddTransformOp / SetSelected) must run on
    # Kit's main thread; the worker thread blocks until done. See
    # run_on_main_thread docstring for why.
    def _do_create_camera() -> Dict[str, Any]:
        from pxr import Sdf, UsdGeom  # noqa: F401

        try:
            import omni.kit.undo as _undo  # type: ignore

            undo_ctx = _undo.group()
        except Exception:
            class _NullCtx:
                def __enter__(self):
                    return None

                def __exit__(self, *args):
                    return False

            undo_ctx = _NullCtx()

        with undo_ctx:
            target_path = Sdf.Path(camera_path)
            if not target_path.IsAbsolutePath():
                return {"ok": False, "error": f"camera_path must be absolute: {camera_path}"}

            _ensure_xform_ancestors(stage, str(target_path))
            final_path = _unique_camera_path(stage, str(target_path))
            camera = UsdGeom.Camera.Define(stage, final_path)
            camera.CreateFocalLengthAttr(float(focal_length))
            camera.CreateHorizontalApertureAttr(float(sensor_mm))
            camera.CreateVerticalApertureAttr(float(sensor_mm * 9.0 / 16.0))

            xformable = UsdGeom.Xformable(camera.GetPrim())
            xformable.ClearXformOpOrder()
            xformable.AddTransformOp().Set(matrix)

            if select_new:
                try:
                    from ...core.stage_utils import get_context

                    get_context().get_selection().set_selected_prim_paths([final_path], True)
                except Exception:
                    pass

        return {
            "ok": True,
            "camera_path": final_path,
            "up_axis": up_axis,
            "eye": [round(float(v), 4) for v in eye],
            "target_center": [round(float(v), 4) for v in target_center],
            "focal_length_mm": round(focal_length, 3),
            "fov_estimate_deg": round(fov_deg, 3),
            "framing": framing,
            "pitch_deg": round(pitch_deg, 3),
            "verify_hint": (
                f"Call list_cameras() and inspect_prim('{final_path}') to confirm. "
                "Set this camera as the active viewport camera in Kit if you want to preview."
            ),
            "undo_hint": "This call is wrapped in omni.kit.undo.group; Ctrl+Z reverts it.",
        }

    try:
        return run_on_main_thread(_do_create_camera, timeout=120.0)
    except Exception as e:
        return {"ok": False, "error": f"Failed to create camera: {e}", "camera_path": camera_path}
