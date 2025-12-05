# -*- coding: utf-8 -*-
"""
BasisCurves 宽度调整核心逻辑
============================

提供对 USD BasisCurves 的宽度属性进行批量调整的功能。
支持根到尖端的渐变宽度设置，以及预览和应用功能。

主要功能:
    - collect_curves: 收集指定路径下的所有 BasisCurves
    - make_width_ramp: 生成渐变宽度数组
    - author_ramp_to_curves: 将宽度写入曲线
    - clear_widths: 清除宽度属性
"""

from typing import List, Optional, Tuple
from pxr import Usd, UsdGeom, Sdf, Vt

from .stage_utils import get_stage


# =============================================================================
# 常量配置
# =============================================================================

# 宽度插值模式
WIDTH_INTERPOLATION = "vertex"

# 是否匹配 Points 的时间采样
MATCH_TIME_SAMPLES = True

# 是否在 Root Layer 中写入（而非 Session Layer）
AUTHOR_IN_ROOT_LAYER = True


# =============================================================================
# 曲线收集函数
# =============================================================================

def is_basis_curves(prim: Usd.Prim) -> bool:
    """
    检查 Prim 是否为 BasisCurves 类型。

    Args:
        prim: 要检查的 Prim

    Returns:
        bool: 是否为 BasisCurves
    """
    try:
        return prim.IsA(UsdGeom.BasisCurves)
    except Exception:
        return False


def collect_curves(root_path: str) -> List[UsdGeom.BasisCurves]:
    """
    收集指定路径下的所有 BasisCurves。

    如果 root_path 本身就是 BasisCurves，则只返回它自己。
    否则递归遍历其所有子 Prim。

    Args:
        root_path: 根路径字符串

    Returns:
        List[UsdGeom.BasisCurves]: BasisCurves 对象列表
    """
    if not root_path:
        return []

    stage = get_stage()
    if not stage:
        return []

    root = stage.GetPrimAtPath(root_path)
    if not root or not root.IsValid():
        return []

    # 如果根本身就是曲线，直接返回
    if is_basis_curves(root):
        return [UsdGeom.BasisCurves(root)]

    # 遍历子树收集曲线
    result = []
    for prim in Usd.PrimRange(root):
        if is_basis_curves(prim):
            result.append(UsdGeom.BasisCurves(prim))

    return result


def first_curve_from_selection(selection_paths: List[str]) -> str:
    """
    从选择列表中找到第一个包含 BasisCurves 的路径。

    Args:
        selection_paths: 选中的路径列表

    Returns:
        str: 找到的路径，如果没找到则返回空字符串
    """
    if not selection_paths:
        return ""

    stage = get_stage()
    if not stage:
        return ""

    for sel_path in selection_paths:
        prim = stage.GetPrimAtPath(sel_path)
        if not prim or not prim.IsValid():
            continue

        # 如果选中的本身就是曲线
        if is_basis_curves(prim):
            return str(prim.GetPath())

        # 搜索子树
        for child in Usd.PrimRange(prim):
            if is_basis_curves(child):
                return str(prim.GetPath())

    return selection_paths[0] if selection_paths else ""


# =============================================================================
# 宽度计算函数
# =============================================================================

def get_time_samples(attr: Usd.Attribute) -> List[float]:
    """
    获取属性的时间采样列表。

    Args:
        attr: USD 属性

    Returns:
        List[float]: 时间采样列表
    """
    try:
        return list(attr.GetTimeSamples())
    except TypeError:
        # 旧版本 API 兼容
        samples = []
        attr.GetTimeSamples(samples)
        return samples


def get_curve_vertex_counts(bc: UsdGeom.BasisCurves) -> List[int]:
    """
    获取曲线的顶点计数数组。

    尝试多种方法获取数据以确保兼容性。

    Args:
        bc: BasisCurves 对象

    Returns:
        List[int]: 顶点计数列表
    """
    attr = bc.GetCurveVertexCountsAttr()

    # 尝试不同的获取方式
    counts = attr.Get()
    if not counts:
        counts = attr.Get(Usd.TimeCode.EarliestTime())
    if not counts:
        samples = get_time_samples(attr)
        if samples:
            counts = attr.Get(samples[0])

    return list(counts) if counts else []


def make_width_ramp(
    vertex_counts: List[int],
    root_width: float,
    tip_width: float,
    scale: float = 1.0
) -> Vt.FloatArray:
    """
    生成从根部到尖端的渐变宽度数组。

    对于每条曲线，根据其顶点数量生成线性插值的宽度值。

    Args:
        vertex_counts: 每条曲线的顶点计数列表
        root_width: 根部宽度
        tip_width: 尖端宽度
        scale: 整体缩放系数

    Returns:
        Vt.FloatArray: 宽度数组
    """
    scaled_root = float(root_width) * float(scale)
    scaled_tip = float(tip_width) * float(scale)

    output = []

    for count in vertex_counts:
        count = int(count)
        if count <= 0:
            continue

        if count == 1:
            # 单点曲线使用根部宽度
            output.append(scaled_root)
            continue

        # 线性插值：从根部到尖端
        step = 1.0 / float(count - 1)
        for i in range(count):
            t = i * step
            width = (1.0 - t) * scaled_root + t * scaled_tip
            output.append(width)

    return Vt.FloatArray(output)


# =============================================================================
# 宽度写入函数
# =============================================================================

def author_ramp_to_curves(
    curves: List[UsdGeom.BasisCurves],
    root_width: float,
    tip_width: float,
    scale: float = 1.0
) -> Tuple[int, int]:
    """
    将渐变宽度写入曲线列表。

    Args:
        curves: BasisCurves 对象列表
        root_width: 根部宽度
        tip_width: 尖端宽度
        scale: 整体缩放系数

    Returns:
        Tuple[int, int]: (写入的 Prim 数量, 写入的元素总数)
    """
    stage = get_stage()
    if not stage:
        return 0, 0

    # 保存当前编辑目标
    prev_target = stage.GetEditTarget()

    if AUTHOR_IN_ROOT_LAYER:
        stage.SetEditTarget(Usd.EditTarget(stage.GetRootLayer()))

    wrote_prims = 0
    wrote_elements = 0

    try:
        with Sdf.ChangeBlock():
            for bc in curves:
                counts = get_curve_vertex_counts(bc)
                if not counts:
                    continue

                width_array = make_width_ramp(counts, root_width, tip_width, scale)
                width_attr = bc.GetWidthsAttr()

                # 设置插值模式
                try:
                    width_attr.SetMetadata(
                        "interpolation",
                        getattr(UsdGeom.Tokens, WIDTH_INTERPOLATION)
                    )
                except Exception:
                    pass

                # 如果需要匹配时间采样
                if MATCH_TIME_SAMPLES:
                    time_samples = get_time_samples(bc.GetPointsAttr())
                    if time_samples:
                        for time in time_samples:
                            width_attr.Set(width_array, Usd.TimeCode(time))
                            wrote_elements += len(width_array)
                        wrote_prims += 1
                        continue

                # 默认：设置静态值
                width_attr.Set(width_array)
                wrote_elements += len(width_array)
                wrote_prims += 1

    finally:
        # 恢复编辑目标
        if AUTHOR_IN_ROOT_LAYER:
            stage.SetEditTarget(prev_target)

    return wrote_prims, wrote_elements


def clear_widths(curves: List[UsdGeom.BasisCurves]) -> int:
    """
    清除曲线列表的宽度属性。

    Args:
        curves: BasisCurves 对象列表

    Returns:
        int: 清除的曲线数量
    """
    stage = get_stage()
    if not stage:
        return 0

    prev_target = stage.GetEditTarget()

    if AUTHOR_IN_ROOT_LAYER:
        stage.SetEditTarget(Usd.EditTarget(stage.GetRootLayer()))

    cleared_count = 0

    try:
        with Sdf.ChangeBlock():
            for bc in curves:
                attr = bc.GetWidthsAttr()
                attr.Clear()
                try:
                    attr.ClearMetadata("interpolation")
                except Exception:
                    pass
                cleared_count += 1

    finally:
        if AUTHOR_IN_ROOT_LAYER:
            stage.SetEditTarget(prev_target)

    return cleared_count


# =============================================================================
# Session Layer 可见性控制
# =============================================================================

def get_session_layer():
    """获取 Session Layer。"""
    stage = get_stage()
    return stage.GetSessionLayer() if stage else None


def session_hide_non_preview_curves(
    root_path: str,
    keep_curve_paths: List[str]
) -> None:
    """
    在 Session Layer 中隐藏非预览曲线。

    Args:
        root_path: 根路径
        keep_curve_paths: 需要保持可见的曲线路径列表
    """
    stage = get_stage()
    if not stage:
        return

    prev_target = stage.GetEditTarget()
    stage.SetEditTarget(Usd.EditTarget(get_session_layer()))

    try:
        curves = collect_curves(root_path)
        keep_set = set(keep_curve_paths)

        with Sdf.ChangeBlock():
            for bc in curves:
                prim = bc.GetPrim()
                vis = UsdGeom.Imageable(prim).GetVisibilityAttr()

                if prim.GetPath().pathString in keep_set:
                    vis.Set(UsdGeom.Tokens.inherited)
                else:
                    vis.Set(UsdGeom.Tokens.invisible)
    finally:
        stage.SetEditTarget(prev_target)


def session_clear_visibility(root_path: str) -> None:
    """
    清除 Session Layer 中的可见性设置。

    Args:
        root_path: 根路径
    """
    stage = get_stage()
    if not stage:
        return

    prev_target = stage.GetEditTarget()
    stage.SetEditTarget(Usd.EditTarget(get_session_layer()))

    try:
        curves = collect_curves(root_path)
        with Sdf.ChangeBlock():
            for bc in curves:
                UsdGeom.Imageable(bc.GetPrim()).GetVisibilityAttr().Clear()
    finally:
        stage.SetEditTarget(prev_target)


def session_force_show_all_curves(root_path: str) -> None:
    """
    强制显示所有曲线。

    Args:
        root_path: 根路径
    """
    stage = get_stage()
    if not stage:
        return

    prev_target = stage.GetEditTarget()
    stage.SetEditTarget(Usd.EditTarget(get_session_layer()))

    try:
        curves = collect_curves(root_path)
        with Sdf.ChangeBlock():
            for bc in curves:
                UsdGeom.Imageable(bc.GetPrim()).GetVisibilityAttr().Set(
                    UsdGeom.Tokens.inherited
                )
    finally:
        stage.SetEditTarget(prev_target)
