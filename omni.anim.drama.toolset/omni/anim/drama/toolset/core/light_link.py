# -*- coding: utf-8 -*-
"""
Light Link 核心逻辑
===================

提供灯光链接（Light Link）功能的核心操作。
允许用户将指定光源与特定几何体关联，实现精确的光照控制。

主要功能:
    - create_light_link: 创建灯光与物体的链接
    - remove_light_link: 移除灯光链接
    - get_light_link_targets: 获取灯光已链接的目标
    - is_light_prim: 检查 Prim 是否为灯光
    - is_geometry_prim: 检查 Prim 是否为几何体
"""

from typing import List, Optional, Tuple
from pxr import Usd, UsdLux, UsdGeom, Sdf

from .stage_utils import get_stage, safe_log


# =============================================================================
# 类型检查函数
# =============================================================================

def is_light_prim(prim: Usd.Prim) -> bool:
    """
    检查 Prim 是否为灯光类型。

    Args:
        prim: 要检查的 Prim

    Returns:
        bool: 是否为灯光
    """
    if not prim or not prim.IsValid():
        return False

    # 检查常见的灯光类型名称（最可靠的方法）
    type_name = prim.GetTypeName()
    light_types = [
        "DistantLight", "DomeLight", "RectLight", "SphereLight",
        "CylinderLight", "DiskLight", "PortalLight", "PluginLight",
        "GeometryLight", "MeshLight"
    ]
    if type_name in light_types:
        return True

    # 尝试使用 UsdLux API 检查（兼容不同版本）
    try:
        # 新版本 USD 使用 LightAPI
        if hasattr(UsdLux, 'LightAPI'):
            return prim.HasAPI(UsdLux.LightAPI)
        # 旧版本 USD 使用 Light
        elif hasattr(UsdLux, 'Light'):
            return prim.IsA(UsdLux.Light)
    except Exception:
        pass

    return False


def is_geometry_prim(prim: Usd.Prim) -> bool:
    """
    检查 Prim 是否为几何体类型。

    Args:
        prim: 要检查的 Prim

    Returns:
        bool: 是否为几何体
    """
    if not prim or not prim.IsValid():
        return False

    try:
        # 检查是否为 Boundable（可渲染几何体）
        if prim.IsA(UsdGeom.Boundable):
            return True

        # 检查是否为 Xform（变换节点，可包含几何体）
        if prim.IsA(UsdGeom.Xform):
            return True
    except Exception:
        pass

    # 检查常见的几何体类型名称
    type_name = prim.GetTypeName()
    geometry_types = [
        "Mesh", "Cube", "Sphere", "Cylinder", "Cone", "Capsule",
        "BasisCurves", "NurbsCurves", "Points", "PointInstancer",
        "Xform", "Scope"
    ]
    return type_name in geometry_types


# =============================================================================
# Light Link 核心操作
# =============================================================================

def create_light_link(
    light_path: str,
    geometry_path: str,
    include_mode: bool = True
) -> Tuple[bool, str]:
    """
    创建灯光与几何体之间的 Light Link。

    Args:
        light_path: 灯光的 USD 路径
        geometry_path: 几何体的 USD 路径
        include_mode: True = 添加到 includes（照亮），False = 添加到 excludes（排除）

    Returns:
        Tuple[bool, str]: (是否成功, 消息)
    """
    stage = get_stage()
    if not stage:
        return False, "No stage available"

    # 验证灯光
    light_prim = stage.GetPrimAtPath(light_path)
    if not light_prim or not light_prim.IsValid():
        return False, f"Light not found: {light_path}"

    if not is_light_prim(light_prim):
        return False, f"Not a light prim: {light_path}"

    # 验证几何体
    geo_prim = stage.GetPrimAtPath(geometry_path)
    if not geo_prim or not geo_prim.IsValid():
        return False, f"Geometry not found: {geometry_path}"

    try:
        # 获取或创建 lightLink Collection
        light_link = Usd.CollectionAPI.Get(light_prim, "lightLink")

        if not light_link:
            # 应用 CollectionAPI
            light_link = Usd.CollectionAPI.Apply(light_prim, "lightLink")
        
        # 强制设置正确的模式（每次创建都确保设置正确）
        # includeRoot = False: 不默认照亮所有物体，只照亮 includes 列表中的
        # expansionRule = "expandPrimsAndProperties": 展开 prim、子节点和属性
        # 这个模式可以同时支持单独 mesh 和组（Xform/Scope）
        light_link.CreateIncludeRootAttr().Set(False)
        light_link.CreateExpansionRuleAttr().Set("expandPrimsAndProperties")

        # 添加目标到 includes 或 excludes
        if include_mode:
            includes_rel = light_link.GetIncludesRel()
            if not includes_rel:
                includes_rel = light_link.CreateIncludesRel()
            includes_rel.AddTarget(geometry_path)
            msg = f"Light Link created: {light_path} → {geometry_path} (include)"
        else:
            excludes_rel = light_link.GetExcludesRel()
            if not excludes_rel:
                excludes_rel = light_link.CreateExcludesRel()
            excludes_rel.AddTarget(geometry_path)
            msg = f"Light Link created: {light_path} ⊘ {geometry_path} (exclude)"

        safe_log(f"[LightLink] {msg}")
        return True, msg

    except Exception as e:
        msg = f"Error creating light link: {e}"
        safe_log(f"[LightLink] {msg}")
        return False, msg


def remove_light_link(
    light_path: str,
    geometry_path: Optional[str] = None
) -> Tuple[bool, str]:
    """
    移除灯光的 Light Link 设置。

    Args:
        light_path: 灯光的 USD 路径
        geometry_path: 要移除的几何体路径，如果为 None 则移除所有链接

    Returns:
        Tuple[bool, str]: (是否成功, 消息)
    """
    stage = get_stage()
    if not stage:
        return False, "No stage available"

    light_prim = stage.GetPrimAtPath(light_path)
    if not light_prim or not light_prim.IsValid():
        return False, f"Light not found: {light_path}"

    try:
        light_link = Usd.CollectionAPI.Get(light_prim, "lightLink")
        if not light_link:
            return False, f"No light link found on: {light_path}"

        if geometry_path:
            # 移除特定目标
            includes_rel = light_link.GetIncludesRel()
            excludes_rel = light_link.GetExcludesRel()

            removed = False
            if includes_rel:
                includes_rel.RemoveTarget(geometry_path)
                removed = True
            if excludes_rel:
                excludes_rel.RemoveTarget(geometry_path)
                removed = True

            if removed:
                msg = f"Removed light link: {light_path} ↛ {geometry_path}"
            else:
                msg = f"Target not found in light link: {geometry_path}"
        else:
            # 移除所有链接
            includes_rel = light_link.GetIncludesRel()
            excludes_rel = light_link.GetExcludesRel()

            if includes_rel:
                includes_rel.ClearTargets(True)
            if excludes_rel:
                excludes_rel.ClearTargets(True)

            # 恢复默认行为
            light_link.CreateIncludeRootAttr().Set(True)
            msg = f"Cleared all light links from: {light_path}"

        safe_log(f"[LightLink] {msg}")
        return True, msg

    except Exception as e:
        msg = f"Error removing light link: {e}"
        safe_log(f"[LightLink] {msg}")
        return False, msg


def get_light_link_targets(light_path: str) -> Tuple[List[str], List[str]]:
    """
    获取灯光已链接的目标列表。

    Args:
        light_path: 灯光的 USD 路径

    Returns:
        Tuple[List[str], List[str]]: (includes 列表, excludes 列表)
    """
    stage = get_stage()
    if not stage:
        return [], []

    light_prim = stage.GetPrimAtPath(light_path)
    if not light_prim or not light_prim.IsValid():
        return [], []

    includes = []
    excludes = []

    try:
        light_link = Usd.CollectionAPI.Get(light_prim, "lightLink")
        if light_link:
            includes_rel = light_link.GetIncludesRel()
            excludes_rel = light_link.GetExcludesRel()

            if includes_rel:
                includes = [str(t) for t in includes_rel.GetTargets()]
            if excludes_rel:
                excludes = [str(t) for t in excludes_rel.GetTargets()]

    except Exception as e:
        safe_log(f"[LightLink] Error getting targets: {e}")

    return includes, excludes


def get_light_link_info(light_path: str) -> dict:
    """
    获取灯光的 Light Link 详细信息。

    Args:
        light_path: 灯光的 USD 路径

    Returns:
        dict: 包含 includeRoot, includes, excludes 等信息
    """
    stage = get_stage()
    if not stage:
        return {"error": "No stage"}

    light_prim = stage.GetPrimAtPath(light_path)
    if not light_prim or not light_prim.IsValid():
        return {"error": f"Light not found: {light_path}"}

    info = {
        "light_path": light_path,
        "has_light_link": False,
        "include_root": True,
        "expansion_rule": "expandPrims",
        "includes": [],
        "excludes": [],
    }

    try:
        light_link = Usd.CollectionAPI.Get(light_prim, "lightLink")
        if light_link:
            info["has_light_link"] = True

            include_root_attr = light_link.GetIncludeRootAttr()
            if include_root_attr and include_root_attr.HasAuthoredValue():
                info["include_root"] = include_root_attr.Get()

            expansion_rule_attr = light_link.GetExpansionRuleAttr()
            if expansion_rule_attr and expansion_rule_attr.HasAuthoredValue():
                info["expansion_rule"] = expansion_rule_attr.Get()

            includes_rel = light_link.GetIncludesRel()
            excludes_rel = light_link.GetExcludesRel()

            if includes_rel:
                info["includes"] = [str(t) for t in includes_rel.GetTargets()]
            if excludes_rel:
                info["excludes"] = [str(t) for t in excludes_rel.GetTargets()]

    except Exception as e:
        info["error"] = str(e)

    return info


# =============================================================================
# Shadow Link 操作（可选功能）
# =============================================================================

def create_shadow_link(
    light_path: str,
    geometry_path: str,
    include_mode: bool = True
) -> Tuple[bool, str]:
    """
    创建灯光与几何体之间的 Shadow Link（控制阴影投射）。

    Args:
        light_path: 灯光的 USD 路径
        geometry_path: 几何体的 USD 路径
        include_mode: True = 投射阴影，False = 不投射阴影

    Returns:
        Tuple[bool, str]: (是否成功, 消息)
    """
    stage = get_stage()
    if not stage:
        return False, "No stage available"

    light_prim = stage.GetPrimAtPath(light_path)
    if not light_prim or not light_prim.IsValid():
        return False, f"Light not found: {light_path}"

    if not is_light_prim(light_prim):
        return False, f"Not a light prim: {light_path}"

    try:
        shadow_link = Usd.CollectionAPI.Get(light_prim, "shadowLink")

        if not shadow_link:
            shadow_link = Usd.CollectionAPI.Apply(light_prim, "shadowLink")
        
        # 强制设置正确的模式
        shadow_link.CreateIncludeRootAttr().Set(False)
        shadow_link.CreateExpansionRuleAttr().Set("expandPrimsAndProperties")

        if include_mode:
            includes_rel = shadow_link.GetIncludesRel()
            if not includes_rel:
                includes_rel = shadow_link.CreateIncludesRel()
            includes_rel.AddTarget(geometry_path)
            msg = f"Shadow Link created: {light_path} → {geometry_path}"
        else:
            excludes_rel = shadow_link.GetExcludesRel()
            if not excludes_rel:
                excludes_rel = shadow_link.CreateExcludesRel()
            excludes_rel.AddTarget(geometry_path)
            msg = f"Shadow Link excluded: {light_path} ⊘ {geometry_path}"

        safe_log(f"[ShadowLink] {msg}")
        return True, msg

    except Exception as e:
        msg = f"Error creating shadow link: {e}"
        safe_log(f"[ShadowLink] {msg}")
        return False, msg

