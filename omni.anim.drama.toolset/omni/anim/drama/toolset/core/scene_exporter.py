# -*- coding: utf-8 -*-
"""
Scene Exporter 场景导出模块
===========================

导出 USD 场景的关键信息，用于 LLM 分析。

主要功能:
    - export_scene_info: 导出场景完整信息
    - export_camera_info: 导出相机信息
    - export_lights_info: 导出灯光信息
    - export_geometry_bounds: 导出几何体边界信息
"""

import json
from typing import Dict, List, Optional, Any
from pxr import Usd, UsdGeom, UsdLux, Gf

from .stage_utils import get_stage, safe_log
from .light_link import is_light_prim


# =============================================================================
# 场景信息导出
# =============================================================================

def export_scene_info() -> Dict[str, Any]:
    """
    导出场景的完整信息。

    Returns:
        Dict: 场景信息字典
    """
    stage = get_stage()
    if not stage:
        return {"error": "No stage available"}

    info = {
        "stage_path": str(stage.GetRootLayer().realPath) if stage.GetRootLayer() else "Unknown",
        "up_axis": str(UsdGeom.GetStageUpAxis(stage)),
        "meters_per_unit": UsdGeom.GetStageMetersPerUnit(stage),
        "time_codes_per_second": stage.GetTimeCodesPerSecond(),
        "start_time": stage.GetStartTimeCode(),
        "end_time": stage.GetEndTimeCode(),
        "cameras": export_cameras_info(),
        "lights": export_lights_info(),
        "bounds": export_scene_bounds(),
    }

    return info


def export_scene_info_for_llm() -> str:
    """
    导出场景信息的文本格式（用于 LLM）。

    Returns:
        str: 场景信息文本
    """
    info = export_scene_info()
    
    lines = ["=== Scene Info ===\n"]
    
    lines.append(f"Stage File: {info.get('stage_path', 'Unknown')}")
    lines.append(f"Up Axis: {info.get('up_axis', 'Y')}")
    lines.append(f"Meters Per Unit: {info.get('meters_per_unit', 0.01)}")
    lines.append(f"FPS: {info.get('time_codes_per_second', 24)}")
    lines.append(f"Time Range: {info.get('start_time', 0)} - {info.get('end_time', 0)}")
    
    # Scene bounds
    bounds = info.get("bounds", {})
    if bounds and "min" in bounds and "max" in bounds:
        lines.append(f"\nScene Bounds:")
        lines.append(f"  Min: ({bounds['min'][0]:.2f}, {bounds['min'][1]:.2f}, {bounds['min'][2]:.2f})")
        lines.append(f"  Max: ({bounds['max'][0]:.2f}, {bounds['max'][1]:.2f}, {bounds['max'][2]:.2f})")
        if "center" in bounds:
            lines.append(f"  Center: ({bounds['center'][0]:.2f}, {bounds['center'][1]:.2f}, {bounds['center'][2]:.2f})")
    
    # Camera info
    cameras = info.get("cameras", [])
    if cameras:
        lines.append(f"\n=== Cameras ({len(cameras)}) ===")
        for cam in cameras:
            lines.append(f"\n{cam.get('name', 'Unknown')}:")
            lines.append(f"  Path: {cam.get('path', 'Unknown')}")
            if "focal_length" in cam:
                lines.append(f"  Focal Length: {cam['focal_length']}mm")
            if "position" in cam:
                p = cam["position"]
                lines.append(f"  Position: ({p[0]:.2f}, {p[1]:.2f}, {p[2]:.2f})")
    
    # Light info - detailed for LLM to understand and modify each one
    lights = info.get("lights", [])
    if lights:
        lines.append(f"\n=== ALL SCENE LIGHTS ({len(lights)} total) - MODIFY EACH ONE ===")
        lines.append("(You must output a 'modify' operation for each light below)")
        
        for i, light in enumerate(lights, 1):
            light_type = light.get('type', 'Unknown')
            light_path = light.get('path', 'Unknown')
            lines.append(f"\n--- Light {i}: {light.get('name', 'Unknown')} ---")
            lines.append(f"  Type: {light_type}")
            lines.append(f"  Path: {light_path}  <-- Use this path in your 'modify' operation")
            
            attrs = light.get("attributes", {})
            lines.append(f"  Current Settings:")
            
            if "intensity" in attrs:
                lines.append(f"    - intensity: {attrs['intensity']}")
            else:
                lines.append(f"    - intensity: (default)")
                
            if "color" in attrs:
                c = attrs["color"]
                if isinstance(c, (list, tuple)):
                    lines.append(f"    - color: [{c[0]:.3f}, {c[1]:.3f}, {c[2]:.3f}]")
            else:
                lines.append(f"    - color: [1.0, 1.0, 1.0] (default white)")
                
            if "temperature" in attrs:
                lines.append(f"    - temperature: {attrs['temperature']}K")
                
            if "exposure" in attrs:
                lines.append(f"    - exposure: {attrs['exposure']}")
                
            if "position" in light:
                p = light["position"]
                lines.append(f"    - position: ({p[0]:.2f}, {p[1]:.2f}, {p[2]:.2f})")
            
            # Add role hint based on light type
            if light_type == "DomeLight":
                lines.append(f"  Role: Environment/ambient light - controls shadow darkness and overall tint")
            elif light_type == "DistantLight":
                lines.append(f"  Role: Sun/directional light - main directional illumination")
            elif light_type in ["RectLight", "SphereLight", "DiskLight"]:
                lines.append(f"  Role: Local light - can be used for colored accent lighting")
    else:
        lines.append("\nNo lights in scene - you may need to CREATE lights.")
    
    return "\n".join(lines)


# =============================================================================
# 相机信息导出
# =============================================================================

def export_cameras_info() -> List[Dict]:
    """
    导出所有相机的信息。

    Returns:
        List[Dict]: 相机信息列表
    """
    stage = get_stage()
    if not stage:
        return []

    cameras = []
    
    for prim in stage.Traverse():
        if prim.IsA(UsdGeom.Camera):
            cam_info = export_camera_info(str(prim.GetPath()))
            if cam_info:
                cameras.append(cam_info)

    return cameras


def export_camera_info(camera_path: str) -> Optional[Dict]:
    """
    导出单个相机的信息。

    Args:
        camera_path: 相机的 USD 路径

    Returns:
        Dict: 相机信息
    """
    stage = get_stage()
    if not stage:
        return None

    prim = stage.GetPrimAtPath(camera_path)
    if not prim or not prim.IsValid():
        return None

    if not prim.IsA(UsdGeom.Camera):
        return None

    camera = UsdGeom.Camera(prim)
    
    info = {
        "path": camera_path,
        "name": prim.GetName(),
    }

    try:
        # 获取相机属性
        focal_length_attr = camera.GetFocalLengthAttr()
        if focal_length_attr:
            info["focal_length"] = focal_length_attr.Get()

        h_aperture_attr = camera.GetHorizontalApertureAttr()
        if h_aperture_attr:
            info["horizontal_aperture"] = h_aperture_attr.Get()

        v_aperture_attr = camera.GetVerticalApertureAttr()
        if v_aperture_attr:
            info["vertical_aperture"] = v_aperture_attr.Get()

        clipping_attr = camera.GetClippingRangeAttr()
        if clipping_attr:
            clipping = clipping_attr.Get()
            info["clipping_range"] = [clipping[0], clipping[1]]

        # 获取变换
        xform = UsdGeom.Xformable(prim)
        world_transform = xform.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        translation = world_transform.ExtractTranslation()
        info["position"] = [translation[0], translation[1], translation[2]]

    except Exception as e:
        info["error"] = str(e)

    return info


# =============================================================================
# 灯光信息导出
# =============================================================================

def export_lights_info() -> List[Dict]:
    """
    导出所有灯光的信息。

    Returns:
        List[Dict]: 灯光信息列表
    """
    stage = get_stage()
    if not stage:
        return []

    lights = []
    
    for prim in stage.Traverse():
        if is_light_prim(prim):
            light_info = export_light_info(str(prim.GetPath()))
            if light_info:
                lights.append(light_info)

    return lights


def export_light_info(light_path: str) -> Optional[Dict]:
    """
    导出单个灯光的信息。

    Args:
        light_path: 灯光的 USD 路径

    Returns:
        Dict: 灯光信息
    """
    stage = get_stage()
    if not stage:
        return None

    prim = stage.GetPrimAtPath(light_path)
    if not prim or not prim.IsValid():
        return None

    info = {
        "path": light_path,
        "name": prim.GetName(),
        "type": prim.GetTypeName(),
        "attributes": {},
    }

    try:
        # 获取变换
        xform = UsdGeom.Xformable(prim)
        world_transform = xform.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        translation = world_transform.ExtractTranslation()
        info["position"] = [translation[0], translation[1], translation[2]]

        # 获取灯光属性
        attr_names = [
            ("inputs:intensity", "intensity"),
            ("inputs:color", "color"),
            ("inputs:colorTemperature", "temperature"),
            ("inputs:exposure", "exposure"),
            ("inputs:radius", "radius"),
            ("inputs:width", "width"),
            ("inputs:height", "height"),
            ("inputs:angle", "angle"),
            ("inputs:length", "length"),
            ("inputs:enableColorTemperature", "enable_temperature"),
        ]

        for attr_name, key in attr_names:
            attr = prim.GetAttribute(attr_name)
            if attr and attr.HasAuthoredValue():
                value = attr.Get()
                if hasattr(value, '__iter__') and not isinstance(value, str):
                    info["attributes"][key] = list(value)
                else:
                    info["attributes"][key] = value

    except Exception as e:
        info["error"] = str(e)

    return info


# =============================================================================
# 场景边界导出
# =============================================================================

def export_scene_bounds() -> Dict:
    """
    导出场景的整体边界。

    Returns:
        Dict: 边界信息
    """
    stage = get_stage()
    if not stage:
        return {}

    try:
        # 创建边界缓存
        purpose = UsdGeom.Tokens.default_
        
        # 计算整个场景的边界
        root = stage.GetPseudoRoot()
        imageable = UsdGeom.Imageable(root)
        
        bounds = imageable.ComputeWorldBound(
            Usd.TimeCode.Default(),
            purpose
        )
        
        bbox = bounds.ComputeAlignedBox()
        
        if bbox.IsEmpty():
            return {}

        min_pt = bbox.GetMin()
        max_pt = bbox.GetMax()
        center = (min_pt + max_pt) / 2.0
        size = max_pt - min_pt

        return {
            "min": [min_pt[0], min_pt[1], min_pt[2]],
            "max": [max_pt[0], max_pt[1], max_pt[2]],
            "center": [center[0], center[1], center[2]],
            "size": [size[0], size[1], size[2]],
        }

    except Exception as e:
        safe_log(f"[SceneExporter] Error computing bounds: {e}")
        return {}


def export_geometry_prims_summary() -> str:
    """
    导出几何体简要信息（用于 LLM）。

    Returns:
        str: 几何体摘要
    """
    stage = get_stage()
    if not stage:
        return "Cannot get stage"

    mesh_count = 0
    xform_count = 0
    other_count = 0
    
    important_prims = []

    for prim in stage.Traverse():
        type_name = prim.GetTypeName()
        
        if type_name == "Mesh":
            mesh_count += 1
            # 只记录顶层重要的 mesh
            depth = len(str(prim.GetPath()).split("/"))
            if depth <= 4:
                important_prims.append({
                    "name": prim.GetName(),
                    "path": str(prim.GetPath()),
                    "type": type_name
                })
        elif type_name == "Xform":
            xform_count += 1
        elif prim.IsA(UsdGeom.Boundable):
            other_count += 1

    lines = ["=== Geometry Overview ==="]
    lines.append(f"Mesh Count: {mesh_count}")
    lines.append(f"Xform Count: {xform_count}")
    lines.append(f"Other Geometry: {other_count}")
    
    if important_prims:
        lines.append("\nMain Objects:")
        for p in important_prims[:10]:  # Limit count
            lines.append(f"  - {p['name']} ({p['path']})")

    return "\n".join(lines)


# =============================================================================
# JSON 导出
# =============================================================================

def export_scene_to_json(output_path: Optional[str] = None) -> str:
    """
    将场景信息导出为 JSON 文件或字符串。

    Args:
        output_path: 输出文件路径，如果为 None 则返回 JSON 字符串

    Returns:
        str: JSON 字符串或文件路径
    """
    info = export_scene_info()
    json_str = json.dumps(info, indent=2, ensure_ascii=False)

    if output_path:
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(json_str)
            safe_log(f"[SceneExporter] Scene exported to: {output_path}")
            return output_path
        except Exception as e:
            safe_log(f"[SceneExporter] Error exporting to file: {e}")
            return json_str

    return json_str

