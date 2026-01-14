# -*- coding: utf-8 -*-
"""
Light Control 核心逻辑
======================

提供灯光创建、修改、删除的核心操作。
支持从JSON原语批量执行灯光操作。
所有 relight 操作写入独立的 Layer，支持恢复原始灯光。

主要功能:
    - create_light: 创建新灯光
    - modify_light: 修改现有灯光
    - delete_light: 删除灯光
    - execute_light_operations: 批量执行灯光操作（自动写入新Layer）
    - get_all_lights: 获取场景中所有灯光
    - get_light_info: 获取灯光详细信息
    - remove_relight_layer: 移除relight Layer，恢复原始状态
    - toggle_relight_layer: 启用/禁用relight Layer
"""

import os
import datetime
from typing import Dict, List, Tuple, Any, Optional
from pxr import Usd, UsdLux, UsdGeom, Gf, Sdf

from .stage_utils import get_stage, safe_log
from .light_link import is_light_prim


# =============================================================================
# Relight Layer 管理
# =============================================================================

# 全局变量存储当前 relight layer 信息
_relight_layer_identifier: Optional[str] = None


def _create_relight_layer() -> Tuple[bool, str, Optional[Sdf.Layer]]:
    """
    创建用于 relight 操作的新 Layer。
    
    Returns:
        Tuple[bool, str, Optional[Sdf.Layer]]: (成功, 消息, Layer对象)
    """
    global _relight_layer_identifier
    
    stage = get_stage()
    if not stage:
        return False, "No stage available", None
    
    try:
        root_layer = stage.GetRootLayer()
        
        # 生成带时间戳的 layer 名称
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        layer_name = f"relight_{timestamp}.usd"
        
        # 获取场景目录
        if root_layer.realPath:
            base_dir = os.path.dirname(root_layer.realPath)
        else:
            # 如果是未保存的场景，使用临时目录
            import tempfile
            base_dir = tempfile.gettempdir()
        
        layer_path = os.path.join(base_dir, layer_name)
        
        # 创建新 Layer
        relight_layer = Sdf.Layer.CreateNew(layer_path)
        if not relight_layer:
            return False, f"Failed to create layer: {layer_path}", None
        
        # 添加为子 Layer（放在最上层，优先级最高）
        # 使用相对路径或绝对路径
        if root_layer.realPath:
            # 尝试使用相对路径
            sub_layer_path = layer_name
        else:
            sub_layer_path = layer_path
            
        root_layer.subLayerPaths.insert(0, sub_layer_path)
        
        # 保存 layer 标识符
        _relight_layer_identifier = relight_layer.identifier
        
        msg = f"Relight layer created: {layer_path}"
        safe_log(f"[LightControl] {msg}")
        return True, msg, relight_layer
        
    except Exception as e:
        msg = f"Error creating relight layer: {e}"
        safe_log(f"[LightControl] {msg}")
        return False, msg, None


def remove_relight_layer() -> Tuple[bool, str]:
    """
    移除 relight Layer，恢复原始灯光状态。
    
    Returns:
        Tuple[bool, str]: (成功, 消息)
    """
    global _relight_layer_identifier
    
    stage = get_stage()
    if not stage:
        return False, "No stage available"
    
    if not _relight_layer_identifier:
        return False, "No relight layer to remove"
    
    try:
        root_layer = stage.GetRootLayer()
        
        # 查找并移除 relight layer
        layer_found = False
        for i, sub_path in enumerate(list(root_layer.subLayerPaths)):
            sub_layer = Sdf.Layer.Find(sub_path)
            if sub_layer and sub_layer.identifier == _relight_layer_identifier:
                del root_layer.subLayerPaths[i]
                layer_found = True
                break
            # 也检查路径是否包含 relight 关键字
            if "relight_" in sub_path:
                del root_layer.subLayerPaths[i]
                layer_found = True
                break
        
        if not layer_found:
            # 尝试直接按路径名移除
            for i, sub_path in enumerate(list(root_layer.subLayerPaths)):
                if "relight_" in sub_path:
                    del root_layer.subLayerPaths[i]
                    layer_found = True
                    break
        
        _relight_layer_identifier = None
        
        if layer_found:
            msg = "Relight layer removed, original lighting restored"
        else:
            msg = "Relight layer not found in sublayers"
            
        safe_log(f"[LightControl] {msg}")
        return True, msg
        
    except Exception as e:
        msg = f"Error removing relight layer: {e}"
        safe_log(f"[LightControl] {msg}")
        return False, msg


def toggle_relight_layer(enabled: bool) -> Tuple[bool, str]:
    """
    启用/禁用 relight Layer（通过 Mute 机制快速切换预览）。
    
    Args:
        enabled: True 启用, False 禁用
        
    Returns:
        Tuple[bool, str]: (成功, 消息)
    """
    global _relight_layer_identifier
    
    stage = get_stage()
    if not stage:
        return False, "No stage available"
    
    if not _relight_layer_identifier:
        return False, "No relight layer available"
    
    try:
        if enabled:
            stage.UnmuteLayer(_relight_layer_identifier)
            msg = "Relight layer enabled"
        else:
            stage.MuteLayer(_relight_layer_identifier)
            msg = "Relight layer disabled (muted)"
            
        safe_log(f"[LightControl] {msg}")
        return True, msg
        
    except Exception as e:
        msg = f"Error toggling relight layer: {e}"
        safe_log(f"[LightControl] {msg}")
        return False, msg


def get_relight_layer_info() -> Dict:
    """
    获取当前 relight layer 的信息。
    
    Returns:
        Dict: Layer 信息
    """
    global _relight_layer_identifier
    
    return {
        "has_relight_layer": _relight_layer_identifier is not None,
        "layer_identifier": _relight_layer_identifier,
    }


# =============================================================================
# 灯光类型映射
# =============================================================================

LIGHT_TYPE_MAP = {
    "DistantLight": UsdLux.DistantLight,
    "RectLight": UsdLux.RectLight,
    "SphereLight": UsdLux.SphereLight,
    "DomeLight": UsdLux.DomeLight,
    "CylinderLight": UsdLux.CylinderLight,
    "DiskLight": UsdLux.DiskLight,
}

# Light type display names
LIGHT_TYPE_NAMES = {
    "DistantLight": "Distant Light",
    "RectLight": "Rect Light",
    "SphereLight": "Sphere Light",
    "DomeLight": "Dome Light",
    "CylinderLight": "Cylinder Light",
    "DiskLight": "Disk Light",
}


# =============================================================================
# 灯光创建
# =============================================================================

def create_light(
    light_type: str,
    name: str,
    parent_path: str = "/World/Lights",
    transform: Optional[Dict] = None,
    attributes: Optional[Dict] = None
) -> Tuple[bool, str, Optional[str]]:
    """
    创建新的灯光。

    Args:
        light_type: 灯光类型 (DistantLight, RectLight, etc.)
        name: 灯光名称
        parent_path: 父级路径
        transform: 变换参数 {translate, rotate, scale}
        attributes: 灯光属性 {intensity, color, temperature, etc.}

    Returns:
        Tuple[bool, str, Optional[str]]: (成功, 消息, 灯光路径)
    """
    stage = get_stage()
    if not stage:
        return False, "No stage available", None

    if light_type not in LIGHT_TYPE_MAP:
        return False, f"Unknown light type: {light_type}", None

    # 确保父路径存在
    parent_prim = stage.GetPrimAtPath(parent_path)
    if not parent_prim or not parent_prim.IsValid():
        UsdGeom.Xform.Define(stage, parent_path)

    # 创建灯光路径
    light_path = f"{parent_path}/{name}"
    
    # 检查路径是否已存在
    if stage.GetPrimAtPath(light_path).IsValid():
        # 添加数字后缀
        i = 1
        while stage.GetPrimAtPath(f"{light_path}_{i}").IsValid():
            i += 1
        light_path = f"{light_path}_{i}"

    try:
        # 创建灯光
        light_class = LIGHT_TYPE_MAP[light_type]
        light = light_class.Define(stage, light_path)

        # 设置变换
        if transform:
            _apply_transform(light.GetPrim(), transform)

        # 设置属性
        if attributes:
            _apply_light_attributes(light, attributes)

        msg = f"Light created: {light_path}"
        safe_log(f"[LightControl] {msg}")
        return True, msg, light_path

    except Exception as e:
        msg = f"Error creating light: {e}"
        safe_log(f"[LightControl] {msg}")
        return False, msg, None


def _apply_transform(prim: Usd.Prim, transform: Dict) -> None:
    """应用变换到 Prim。"""
    xform = UsdGeom.Xformable(prim)
    
    # 清除现有变换操作
    xform.ClearXformOpOrder()
    
    if "translate" in transform:
        t = transform["translate"]
        xform.AddTranslateOp().Set(Gf.Vec3d(float(t[0]), float(t[1]), float(t[2])))
    
    if "rotate" in transform:
        r = transform["rotate"]
        xform.AddRotateXYZOp().Set(Gf.Vec3f(float(r[0]), float(r[1]), float(r[2])))
    
    if "scale" in transform:
        s = transform["scale"]
        xform.AddScaleOp().Set(Gf.Vec3f(float(s[0]), float(s[1]), float(s[2])))


def _apply_light_attributes(light, attributes: Dict) -> None:
    """应用灯光属性。"""
    prim = light.GetPrim()
    
    # 通用属性 - 使用兼容的方式获取属性
    if "intensity" in attributes:
        intensity_attr = prim.GetAttribute("inputs:intensity")
        if not intensity_attr:
            intensity_attr = prim.CreateAttribute("inputs:intensity", Sdf.ValueTypeNames.Float)
        intensity_attr.Set(float(attributes["intensity"]))
    
    if "color" in attributes:
        c = attributes["color"]
        color_attr = prim.GetAttribute("inputs:color")
        if not color_attr:
            color_attr = prim.CreateAttribute("inputs:color", Sdf.ValueTypeNames.Color3f)
        color_attr.Set(Gf.Vec3f(float(c[0]), float(c[1]), float(c[2])))
    
    if "temperature" in attributes:
        temp_attr = prim.GetAttribute("inputs:colorTemperature")
        if not temp_attr:
            temp_attr = prim.CreateAttribute("inputs:colorTemperature", Sdf.ValueTypeNames.Float)
        temp_attr.Set(float(attributes["temperature"]))
        
        enable_temp_attr = prim.GetAttribute("inputs:enableColorTemperature")
        if not enable_temp_attr:
            enable_temp_attr = prim.CreateAttribute("inputs:enableColorTemperature", Sdf.ValueTypeNames.Bool)
        enable_temp_attr.Set(True)
    
    if "exposure" in attributes:
        exposure_attr = prim.GetAttribute("inputs:exposure")
        if not exposure_attr:
            exposure_attr = prim.CreateAttribute("inputs:exposure", Sdf.ValueTypeNames.Float)
        exposure_attr.Set(float(attributes["exposure"]))

    # 特定类型属性
    type_name = prim.GetTypeName()
    
    if type_name == "RectLight":
        if "width" in attributes:
            width_attr = prim.GetAttribute("inputs:width")
            if width_attr:
                width_attr.Set(float(attributes["width"]))
        if "height" in attributes:
            height_attr = prim.GetAttribute("inputs:height")
            if height_attr:
                height_attr.Set(float(attributes["height"]))
    
    elif type_name == "SphereLight":
        if "radius" in attributes:
            radius_attr = prim.GetAttribute("inputs:radius")
            if radius_attr:
                radius_attr.Set(float(attributes["radius"]))
    
    elif type_name == "DistantLight":
        if "angle" in attributes:
            angle_attr = prim.GetAttribute("inputs:angle")
            if angle_attr:
                angle_attr.Set(float(attributes["angle"]))
    
    elif type_name == "DiskLight":
        if "radius" in attributes:
            radius_attr = prim.GetAttribute("inputs:radius")
            if radius_attr:
                radius_attr.Set(float(attributes["radius"]))
    
    elif type_name == "CylinderLight":
        if "radius" in attributes:
            radius_attr = prim.GetAttribute("inputs:radius")
            if radius_attr:
                radius_attr.Set(float(attributes["radius"]))
        if "length" in attributes:
            length_attr = prim.GetAttribute("inputs:length")
            if length_attr:
                length_attr.Set(float(attributes["length"]))


# =============================================================================
# 灯光修改
# =============================================================================

def modify_light(
    light_path: str,
    transform: Optional[Dict] = None,
    attributes: Optional[Dict] = None
) -> Tuple[bool, str]:
    """
    修改现有灯光的属性和变换。

    Args:
        light_path: 灯光的 USD 路径
        transform: 变换参数 {translate, rotate, scale}
        attributes: 灯光属性

    Returns:
        Tuple[bool, str]: (成功, 消息)
    """
    stage = get_stage()
    if not stage:
        return False, "No stage available"

    prim = stage.GetPrimAtPath(light_path)
    if not prim or not prim.IsValid():
        return False, f"Light not found: {light_path}"

    if not is_light_prim(prim):
        return False, f"Not a light prim: {light_path}"

    try:
        # 修改变换
        if transform:
            _apply_transform(prim, transform)

        # 修改属性
        if attributes:
            # 根据类型获取灯光对象
            type_name = prim.GetTypeName()
            if type_name in LIGHT_TYPE_MAP:
                light = LIGHT_TYPE_MAP[type_name](prim)
                _apply_light_attributes(light, attributes)

        msg = f"Light modified: {light_path}"
        safe_log(f"[LightControl] {msg}")
        return True, msg

    except Exception as e:
        msg = f"Error modifying light: {e}"
        safe_log(f"[LightControl] {msg}")
        return False, msg


# =============================================================================
# 灯光删除
# =============================================================================

def delete_light(light_path: str) -> Tuple[bool, str]:
    """
    删除灯光。

    Args:
        light_path: 灯光的 USD 路径

    Returns:
        Tuple[bool, str]: (成功, 消息)
    """
    stage = get_stage()
    if not stage:
        return False, "No stage available"

    prim = stage.GetPrimAtPath(light_path)
    if not prim or not prim.IsValid():
        return False, f"Light not found: {light_path}"

    if not is_light_prim(prim):
        return False, f"Not a light prim: {light_path}"

    try:
        stage.RemovePrim(light_path)
        msg = f"Light deleted: {light_path}"
        safe_log(f"[LightControl] {msg}")
        return True, msg

    except Exception as e:
        msg = f"Error deleting light: {e}"
        safe_log(f"[LightControl] {msg}")
        return False, msg


# =============================================================================
# 批量操作
# =============================================================================

def execute_light_operations(
    operations: List[Dict],
    use_relight_layer: bool = True
) -> Tuple[int, int, List[str]]:
    """
    批量执行灯光操作。
    
    所有操作默认写入独立的 relight Layer，方便后续恢复。

    Args:
        operations: 操作列表，每个操作包含 action 和相关参数
        use_relight_layer: 是否使用独立的 relight layer（默认 True）

    Returns:
        Tuple[int, int, List[str]]: (成功数, 失败数, 消息列表)
    """
    success_count = 0
    fail_count = 0
    messages = []
    
    stage = get_stage()
    if not stage:
        return 0, len(operations), ["No stage available"]
    
    # 保存原始 edit target
    original_edit_target = stage.GetEditTarget()
    relight_layer = None
    
    try:
        # 创建 relight layer 并设置为 edit target
        if use_relight_layer:
            layer_success, layer_msg, relight_layer = _create_relight_layer()
            if layer_success and relight_layer:
                stage.SetEditTarget(Usd.EditTarget(relight_layer))
                messages.append(layer_msg)
            else:
                messages.append(f"Warning: {layer_msg}, using current edit target")

        # 执行所有操作
        for op in operations:
            action = op.get("action", "").lower()
            
            try:
                if action == "create":
                    success, msg, path = create_light(
                        light_type=op.get("light_type", "SphereLight"),
                        name=op.get("name", "NewLight"),
                        parent_path=op.get("parent_path", "/World/Lights"),
                        transform=op.get("transform"),
                        attributes=op.get("attributes")
                    )
                    if success:
                        success_count += 1
                    else:
                        fail_count += 1
                    messages.append(msg)
                
                elif action == "modify":
                    success, msg = modify_light(
                        light_path=op.get("light_path", ""),
                        transform=op.get("transform"),
                        attributes=op.get("attributes")
                    )
                    if success:
                        success_count += 1
                    else:
                        fail_count += 1
                    messages.append(msg)
                
                elif action == "delete":
                    success, msg = delete_light(
                        light_path=op.get("light_path", "")
                    )
                    if success:
                        success_count += 1
                    else:
                        fail_count += 1
                    messages.append(msg)
                
                else:
                    fail_count += 1
                    messages.append(f"Unknown action: {action}")

            except Exception as e:
                fail_count += 1
                messages.append(f"Error executing operation: {e}")
        
        # 保存 relight layer
        if relight_layer:
            relight_layer.Save()
            messages.append(f"Relight layer saved: {relight_layer.identifier}")
                
    finally:
        # 恢复原始 edit target
        if use_relight_layer:
            stage.SetEditTarget(original_edit_target)

    return success_count, fail_count, messages


# =============================================================================
# 查询函数
# =============================================================================

def get_all_lights() -> List[Dict]:
    """
    获取场景中所有灯光的信息。

    Returns:
        List[Dict]: 灯光信息列表
    """
    stage = get_stage()
    if not stage:
        return []

    lights = []
    
    for prim in stage.Traverse():
        if is_light_prim(prim):
            lights.append(get_light_info(str(prim.GetPath())))

    return lights


def get_light_info(light_path: str) -> Dict:
    """
    获取灯光的详细信息。

    Args:
        light_path: 灯光的 USD 路径

    Returns:
        Dict: 灯光信息字典
    """
    stage = get_stage()
    if not stage:
        return {"error": "No stage"}

    prim = stage.GetPrimAtPath(light_path)
    if not prim or not prim.IsValid():
        return {"error": f"Light not found: {light_path}"}

    info = {
        "path": light_path,
        "name": prim.GetName(),
        "type": prim.GetTypeName(),
        "type_display": LIGHT_TYPE_NAMES.get(prim.GetTypeName(), prim.GetTypeName()),
        "attributes": {},
        "transform": {}
    }

    try:
        # 获取变换信息
        xform = UsdGeom.Xformable(prim)
        world_transform = xform.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        
        # 提取位移
        translation = world_transform.ExtractTranslation()
        info["transform"]["translate"] = [translation[0], translation[1], translation[2]]

        # 获取常用属性
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


def get_lights_summary() -> str:
    """
    Get text summary of scene lights (for LLM input).

    Returns:
        str: Lights summary text
    """
    lights = get_all_lights()
    
    if not lights:
        return "No lights in scene."

    lines = [f"Scene has {len(lights)} lights:\n"]
    
    for i, light in enumerate(lights, 1):
        lines.append(f"{i}. {light.get('name', 'Unknown')} ({light.get('type_display', 'Unknown')})")
        lines.append(f"   Path: {light.get('path', 'Unknown')}")
        
        attrs = light.get("attributes", {})
        if "intensity" in attrs:
            lines.append(f"   Intensity: {attrs['intensity']}")
        if "color" in attrs:
            lines.append(f"   Color: {attrs['color']}")
        if "temperature" in attrs:
            lines.append(f"   Temperature: {attrs['temperature']}K")
        
        transform = light.get("transform", {})
        if "translate" in transform:
            t = transform["translate"]
            lines.append(f"   Position: ({t[0]:.2f}, {t[1]:.2f}, {t[2]:.2f})")
        
        lines.append("")

    return "\n".join(lines)
