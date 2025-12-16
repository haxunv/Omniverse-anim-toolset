# -*- coding: utf-8 -*-
"""
UV 传输核心逻辑
===============

提供从源 BasisCurves 到目标曲线组的 UV（Primvar）数据传输功能。
支持重定位安全的 USD 文件输出。

主要功能:
    - expand_primvar: 展开 Primvar 数据（处理索引）
    - collect_curves_under: 收集路径下的所有曲线
    - bake_uv_to_file: 将 UV 数据烘焙到输出文件
"""

import os
from typing import List, Optional, Tuple
from pxr import Usd, UsdGeom, Sdf, Vt, Gf

from .stage_utils import get_stage


# =============================================================================
# 常量配置
# =============================================================================

# 默认时间码
DEFAULT_TIMECODE = Usd.TimeCode.EarliestTime()

# 数据不足时是否填充
PAD_SHORTAGE = True

# 填充模式: "repeat" (重复最后一个) / "wrap" (循环) / "zero" (填零)
PAD_MODE = "repeat"

# 空数据时是否强制创建属性
FORCE_ATTR_ON_EMPTY = True

# 输出文件中的内部路径
INTERNAL_ROOT = Sdf.Path("/HairPack")
TARGET_MOUNT = INTERNAL_ROOT.AppendChild("Target")


# =============================================================================
# 数据转换工具
# =============================================================================

def to_vec2f_array(seq) -> Vt.Vec2fArray:
    """
    将序列转换为 Vt.Vec2fArray。

    Args:
        seq: 输入序列

    Returns:
        Vt.Vec2fArray: 转换后的数组
    """
    if isinstance(seq, Vt.Vec2fArray):
        return seq

    items = list(seq)
    output = Vt.Vec2fArray(len(items))

    for i, v in enumerate(items):
        if isinstance(v, Gf.Vec2f):
            output[i] = v
        else:
            output[i] = Gf.Vec2f(float(v[0]), float(v[1]))

    return output


def expand_primvar(pv: UsdGeom.Primvar) -> Tuple[Optional[Vt.Vec2fArray], str]:
    """
    展开 Primvar 数据，处理可能的索引。

    Args:
        pv: UsdGeom.Primvar 对象

    Returns:
        Tuple[Vt.Vec2fArray, str]: (展开后的数据, 插值模式)
    """
    interp = pv.GetInterpolation()
    values = pv.Get(DEFAULT_TIMECODE)

    if values is None:
        return None, interp

    # 检查是否有索引
    idx_attr = pv.GetIndicesAttr()
    indices = None
    if idx_attr and idx_attr.HasAuthoredValueOpinion():
        indices = idx_attr.Get(DEFAULT_TIMECODE)

    if indices:
        # 通过索引展开数据
        base = list(values)
        output = Vt.Vec2fArray(len(indices))
        for i, idx in enumerate(indices):
            v = base[idx]
            if isinstance(v, Gf.Vec2f):
                output[i] = v
            else:
                output[i] = Gf.Vec2f(float(v[0]), float(v[1]))
        return output, interp

    return to_vec2f_array(values), interp


def get_first_time_sample(attr: Usd.Attribute):
    """
    获取属性的第一个时间采样值。

    Args:
        attr: USD 属性

    Returns:
        第一个时间采样的值，如果没有则返回 None
    """
    try:
        samples = list(attr.GetTimeSamples())
    except TypeError:
        samples = []
        attr.GetTimeSamples(samples)

    return attr.Get(samples[0]) if samples else None


# =============================================================================
# 曲线收集函数
# =============================================================================

def collect_curves_under(root_path: str) -> List[Usd.Prim]:
    """
    收集指定路径下的所有 BasisCurves Prim。

    Args:
        root_path: 根路径

    Returns:
        List[Usd.Prim]: BasisCurves Prim 列表
    """
    stage = get_stage()
    if not stage:
        return []

    root = stage.GetPrimAtPath(root_path)
    if not root:
        return []

    result = []
    for prim in Usd.PrimRange(root):
        if prim.IsA(UsdGeom.BasisCurves):
            result.append(prim)

    return result


def need_counts_robust(bc: UsdGeom.BasisCurves, interp: str) -> int:
    """
    稳健地计算曲线需要的 UV 元素数量。

    根据插值模式计算所需数量：
    - vertex/varying: 顶点总数
    - uniform: 曲线数量
    - constant: 1

    Args:
        bc: BasisCurves 对象
        interp: 插值模式

    Returns:
        int: 需要的元素数量
    """
    # 尝试获取顶点计数
    counts = bc.GetCurveVertexCountsAttr().Get(DEFAULT_TIMECODE)
    if not counts:
        counts = bc.GetCurveVertexCountsAttr().Get()
    if not counts:
        counts = get_first_time_sample(bc.GetCurveVertexCountsAttr())

    # 如果没有计数但需要顶点级数据，尝试从 Points 推断
    if (not counts) and interp in ("vertex", "varying"):
        points = (
            bc.GetPointsAttr().Get(DEFAULT_TIMECODE) or
            bc.GetPointsAttr().Get() or
            get_first_time_sample(bc.GetPointsAttr())
        )
        if points is not None:
            return int(len(points))

    if not counts:
        return 0

    # 根据插值模式返回所需数量
    if interp in ("vertex", "varying"):
        return int(sum(counts))
    elif interp == "uniform":
        return int(len(counts))
    elif interp == "constant":
        return 1

    return 0


# =============================================================================
# 文件路径工具
# =============================================================================

def make_relative_path(base_file: str, target_file: str) -> str:
    """
    计算相对路径。

    Args:
        base_file: 基准文件路径
        target_file: 目标文件路径

    Returns:
        str: 相对路径
    """
    try:
        base_dir = os.path.dirname(os.path.abspath(base_file))
        target_abs = os.path.abspath(target_file)
        return os.path.relpath(target_abs, base_dir).replace("\\", "/")
    except Exception:
        return target_file


def map_to_internal_path(original_path: str, target_root: str) -> Sdf.Path:
    """
    将原始路径映射到输出文件的内部路径。

    Args:
        original_path: 原始 Prim 路径
        target_root: 目标根路径

    Returns:
        Sdf.Path: 映射后的内部路径
    """
    orig = Sdf.Path(original_path)
    root = Sdf.Path(target_root)

    if orig == root:
        return TARGET_MOUNT

    rel_path = orig.MakeRelativePath(root)
    if not rel_path or rel_path.pathString in (".", ""):
        return TARGET_MOUNT

    return TARGET_MOUNT.AppendPath(rel_path)


def find_source_layer_and_path(prim: Usd.Prim) -> Tuple[Optional[str], Optional[str]]:
    """
    找到 Prim 的源 Layer 和路径。

    用于在输出文件中正确引用原始资产。

    Args:
        prim: USD Prim

    Returns:
        Tuple[str, str]: (Layer 文件路径, Prim 路径)
    """
    if not prim:
        return None, None

    stack = prim.GetPrimStack()
    if not stack:
        return None, None

    # 优先找路径完全一致的 spec
    for spec in stack:
        layer = spec.layer
        if not layer:
            continue
        real_path = layer.realPath
        if not real_path:
            continue
        if spec.path == prim.GetPath():
            return real_path, spec.path.pathString

    # 退而求其次：找第一个有 realPath 的 spec
    for spec in stack:
        layer = spec.layer
        if not layer:
            continue
        real_path = layer.realPath
        if real_path:
            return real_path, spec.path.pathString

    return None, prim.GetPath().pathString


# =============================================================================
# UV 烘焙主函数
# =============================================================================

def bake_uv_to_file(
    source_curve_path: str,
    target_root_path: str,
    primvar_name: str,
    output_file_path: str,
    on_log: callable = None
) -> Tuple[bool, str]:
    """
    将 UV 数据从源曲线烘焙到目标曲线并输出文件。

    此函数执行以下步骤：
    1. 从源曲线读取 UV Primvar
    2. 收集目标路径下的所有曲线
    3. 创建新的 USD 文件，引用目标资产
    4. 将 UV 数据写入输出文件作为 Override

    Args:
        source_curve_path: 源 BasisCurves 路径（包含 UV）
        target_root_path: 目标根路径或 BasisCurves
        primvar_name: Primvar 名称（如 "st1"）
        output_file_path: 输出文件路径
        on_log: 日志回调函数

    Returns:
        Tuple[bool, str]: (是否成功, 消息)
    """
    def log(msg):
        if on_log:
            on_log(msg)

    stage = get_stage()
    if not stage:
        return False, "No open Stage."

    # 验证输入
    if not source_curve_path or not target_root_path:
        return False, "Please set Source and Target first."

    # 确保输出路径有正确的扩展名
    if not output_file_path:
        base_dir = os.path.dirname(stage.GetRootLayer().realPath or "") or os.path.expanduser("~")
        output_file_path = os.path.join(base_dir, "final_hair.usda").replace("\\", "/")
    else:
        root, ext = os.path.splitext(output_file_path)
        if ext.lower() not in (".usda", ".usd", ".usdc"):
            output_file_path = root + ".usda"

    try:
        # === 读取源 UV ===
        src_prim = stage.GetPrimAtPath(source_curve_path)
        if not src_prim or not src_prim.IsA(UsdGeom.BasisCurves):
            return False, "Source is not a BasisCurves."

        api = UsdGeom.PrimvarsAPI(src_prim)
        pv = (
            api.GetPrimvar(primvar_name) or
            api.GetPrimvar("st") or
            api.GetPrimvar("st0")
        )

        if not pv or not pv.HasValue():
            return False, f"No primvars:{primvar_name}/st/st0 on source."

        src_vals, src_interp = expand_primvar(pv)
        if src_vals is None or len(src_vals) == 0:
            return False, "Source UV is empty."

        log(f"Source UV: interp='{src_interp}', count={len(src_vals)}")

        # === 收集目标曲线 ===
        curves = collect_curves_under(target_root_path)
        if not curves:
            return False, "No BasisCurves found under / at target."

        log(f"Target curves: {len(curves)}")

        # 计算每条曲线需要的元素数量
        needs = []
        total_need = 0
        for p in curves:
            n = need_counts_robust(UsdGeom.BasisCurves(p), src_interp)
            needs.append((p.GetPath().pathString, n))
            total_need += max(0, n)

        log(f"Total need: {total_need}, source elems: {len(src_vals)}")

        # === 找到目标的源资产 ===
        src_target_prim = stage.GetPrimAtPath(target_root_path)
        layer_path, prim_path_in_layer = find_source_layer_and_path(src_target_prim)

        if not layer_path:
            return False, "Cannot find authored layer for target prim."

        log(f"Target asset file: {layer_path}")
        log(f"Target prim path in asset: {prim_path_in_layer}")

        # === 创建输出 Stage ===
        final = Usd.Stage.CreateInMemory()

        # 复制 Stage 元数据
        try:
            up = UsdGeom.GetStageUpAxis(stage)
            if up:
                UsdGeom.SetStageUpAxis(final, up)
            mpu = UsdGeom.GetStageMetersPerUnit(stage)
            if mpu:
                UsdGeom.SetStageMetersPerUnit(final, mpu)
            tps = stage.GetTimeCodesPerSecond()
            if tps:
                final.SetTimeCodesPerSecond(tps)
                final.SetFramesPerSecond(stage.GetFramesPerSecond())
        except Exception:
            pass

        # 创建内部结构
        final_root = final.DefinePrim(INTERNAL_ROOT, "Xform")
        final.SetDefaultPrim(final_root)

        src_type = src_target_prim.GetTypeName() if src_target_prim else ""
        target_prim = final.DefinePrim(TARGET_MOUNT, src_type)

        # 添加对原始资产的引用
        rel_asset = make_relative_path(output_file_path, layer_path)
        target_prim.GetReferences().AddReference(
            assetPath=rel_asset,
            primPath=prim_path_in_layer
        )

        # === 写入 UV Override ===
        vtname = Sdf.ValueTypeNames.TexCoord2fArray
        cursor = 0
        wrote = 0
        wrote_elems = 0
        skipped = 0

        for orig_path, need in needs:
            final_p = map_to_internal_path(orig_path, target_root_path)

            if need <= 0:
                if FORCE_ATTR_ON_EMPTY:
                    over = final.OverridePrim(final_p)
                    pv_out = UsdGeom.PrimvarsAPI(over).CreatePrimvar(
                        primvar_name, vtname, src_interp or "vertex"
                    )
                    pv_out.Set(Vt.Vec2fArray())
                    log(f"[ForceAttr] {final_p.pathString} need=0 → empty {primvar_name}")
                    wrote += 1
                else:
                    log(f"[Skip] {final_p.pathString} need=0")
                    skipped += 1
                continue

            remaining = len(src_vals) - cursor

            if remaining < need:
                if not PAD_SHORTAGE or remaining <= 0:
                    log(f"[Stop] not enough data: {final_p.pathString} need {need}, remain {remaining}")
                    break

                # 填充不足的数据
                slice_vals = Vt.Vec2fArray(need)
                for i in range(min(remaining, need)):
                    slice_vals[i] = src_vals[cursor + i]

                if PAD_MODE == "repeat":
                    last = src_vals[cursor + remaining - 1]
                    for i in range(remaining, need):
                        slice_vals[i] = last
                elif PAD_MODE == "wrap":
                    for i in range(remaining, need):
                        slice_vals[i] = src_vals[cursor + (i % remaining)]
                else:  # zero
                    for i in range(remaining, need):
                        slice_vals[i] = Gf.Vec2f(0.0, 0.0)

                cursor += remaining
                log(f"[Pad] {final_p.pathString} need {need}, remain {remaining} → fill {need-remaining} ({PAD_MODE})")
            else:
                slice_vals = Vt.Vec2fArray(need)
                for i in range(need):
                    slice_vals[i] = src_vals[cursor + i]
                cursor += need

            over = final.OverridePrim(final_p)
            pv_out = UsdGeom.PrimvarsAPI(over).CreatePrimvar(
                primvar_name, vtname, src_interp or "vertex"
            )
            pv_out.Set(slice_vals)
            wrote += 1
            wrote_elems += need

        # 导出文件
        final.GetRootLayer().Export(output_file_path)

        summary = f"Wrote {wrote} curves, elems {wrote_elems}; skipped {skipped}; remain {len(src_vals)-cursor}"
        log(f"✅ Saved: {output_file_path}")
        log(summary)

        return True, f"Saved to {output_file_path}"

    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, f"Failed: {e}"


# =============================================================================
# 独立文件导出（无依赖）
# =============================================================================

def bake_uv_to_standalone_file(
    source_curve_path: str,
    target_root_path: str,
    primvar_name: str,
    output_file_path: str,
    on_log: callable = None
) -> Tuple[bool, str]:
    """
    将 UV 数据从源曲线烘焙到目标曲线，输出独立文件（不依赖原文件）。

    与 bake_uv_to_file 不同，此函数会完整复制目标曲线的几何数据，
    生成一个可以独立存在的 USD 文件。

    Args:
        source_curve_path: 源 BasisCurves 路径（包含 UV）
        target_root_path: 目标根路径或 BasisCurves
        primvar_name: Primvar 名称（如 "st1"）
        output_file_path: 输出文件路径
        on_log: 日志回调函数

    Returns:
        Tuple[bool, str]: (是否成功, 消息)
    """
    def log(msg):
        if on_log:
            on_log(msg)

    stage = get_stage()
    if not stage:
        return False, "No open Stage."

    # 验证输入
    if not source_curve_path or not target_root_path:
        return False, "Please set Source and Target first."

    # 确保输出路径有正确的扩展名
    if not output_file_path:
        base_dir = os.path.dirname(stage.GetRootLayer().realPath or "") or os.path.expanduser("~")
        output_file_path = os.path.join(base_dir, "standalone_hair.usda").replace("\\", "/")
    else:
        root, ext = os.path.splitext(output_file_path)
        if ext.lower() not in (".usda", ".usd", ".usdc"):
            output_file_path = root + ".usda"

    try:
        # === 读取源 UV ===
        src_prim = stage.GetPrimAtPath(source_curve_path)
        if not src_prim or not src_prim.IsA(UsdGeom.BasisCurves):
            return False, "Source is not a BasisCurves."

        api = UsdGeom.PrimvarsAPI(src_prim)
        pv = (
            api.GetPrimvar(primvar_name) or
            api.GetPrimvar("st") or
            api.GetPrimvar("st0")
        )

        if not pv or not pv.HasValue():
            return False, f"No primvars:{primvar_name}/st/st0 on source."

        src_vals, src_interp = expand_primvar(pv)
        if src_vals is None or len(src_vals) == 0:
            return False, "Source UV is empty."

        log(f"Source UV: interp='{src_interp}', count={len(src_vals)}")

        # === 收集目标曲线 ===
        curves = collect_curves_under(target_root_path)
        if not curves:
            return False, "No BasisCurves found under / at target."

        log(f"Target curves: {len(curves)}")

        # 计算每条曲线需要的元素数量
        needs = []
        total_need = 0
        for p in curves:
            n = need_counts_robust(UsdGeom.BasisCurves(p), src_interp)
            needs.append((p, n))  # 保存 prim 而不是路径
            total_need += max(0, n)

        log(f"Total need: {total_need}, source elems: {len(src_vals)}")

        # === 创建独立输出 Stage ===
        final = Usd.Stage.CreateInMemory()

        # 复制 Stage 元数据
        try:
            up = UsdGeom.GetStageUpAxis(stage)
            if up:
                UsdGeom.SetStageUpAxis(final, up)
            mpu = UsdGeom.GetStageMetersPerUnit(stage)
            if mpu:
                UsdGeom.SetStageMetersPerUnit(final, mpu)
            tps = stage.GetTimeCodesPerSecond()
            if tps:
                final.SetTimeCodesPerSecond(tps)
                final.SetFramesPerSecond(stage.GetFramesPerSecond())
        except Exception:
            pass

        # 创建根节点
        final_root = final.DefinePrim(INTERNAL_ROOT, "Xform")
        final.SetDefaultPrim(final_root)

        # === 复制曲线几何数据并写入 UV ===
        vtname = Sdf.ValueTypeNames.TexCoord2fArray
        cursor = 0
        wrote = 0
        wrote_elems = 0
        skipped = 0

        for src_curve_prim, need in needs:
            # 计算输出路径
            orig_path = src_curve_prim.GetPath().pathString
            final_p = map_to_internal_path(orig_path, target_root_path)

            # 创建新的 BasisCurves prim（不是 Override，而是完整定义）
            new_curve = UsdGeom.BasisCurves.Define(final, final_p)

            # 复制几何属性
            src_bc = UsdGeom.BasisCurves(src_curve_prim)
            _copy_basis_curves_data(src_bc, new_curve, log)

            if need <= 0:
                if FORCE_ATTR_ON_EMPTY:
                    pv_out = UsdGeom.PrimvarsAPI(new_curve).CreatePrimvar(
                        primvar_name, vtname, src_interp or "vertex"
                    )
                    pv_out.Set(Vt.Vec2fArray())
                    log(f"[Standalone] {final_p.pathString} need=0 → empty {primvar_name}")
                    wrote += 1
                else:
                    log(f"[Skip] {final_p.pathString} need=0")
                    skipped += 1
                continue

            remaining = len(src_vals) - cursor

            if remaining < need:
                if not PAD_SHORTAGE or remaining <= 0:
                    log(f"[Stop] not enough data: {final_p.pathString} need {need}, remain {remaining}")
                    break

                # 填充不足的数据
                slice_vals = Vt.Vec2fArray(need)
                for i in range(min(remaining, need)):
                    slice_vals[i] = src_vals[cursor + i]

                if PAD_MODE == "repeat":
                    last = src_vals[cursor + remaining - 1]
                    for i in range(remaining, need):
                        slice_vals[i] = last
                elif PAD_MODE == "wrap":
                    for i in range(remaining, need):
                        slice_vals[i] = src_vals[cursor + (i % remaining)]
                else:  # zero
                    for i in range(remaining, need):
                        slice_vals[i] = Gf.Vec2f(0.0, 0.0)

                cursor += remaining
                log(f"[Pad] {final_p.pathString} need {need}, remain {remaining} → fill {need-remaining} ({PAD_MODE})")
            else:
                slice_vals = Vt.Vec2fArray(need)
                for i in range(need):
                    slice_vals[i] = src_vals[cursor + i]
                cursor += need

            # 写入 UV
            pv_out = UsdGeom.PrimvarsAPI(new_curve).CreatePrimvar(
                primvar_name, vtname, src_interp or "vertex"
            )
            pv_out.Set(slice_vals)
            wrote += 1
            wrote_elems += need

        # 导出文件
        final.GetRootLayer().Export(output_file_path)

        summary = f"Wrote {wrote} curves (standalone), elems {wrote_elems}; skipped {skipped}; remain {len(src_vals)-cursor}"
        log(f"✅ Saved (standalone): {output_file_path}")
        log(summary)

        return True, f"Saved standalone to {output_file_path}"

    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, f"Failed: {e}"


def _copy_basis_curves_data(src: UsdGeom.BasisCurves, dst: UsdGeom.BasisCurves, log=None):
    """
    复制 BasisCurves 的几何数据。

    Args:
        src: 源 BasisCurves
        dst: 目标 BasisCurves
        log: 日志函数
    """
    try:
        # 复制 Points（顶点位置）
        points = src.GetPointsAttr().Get(DEFAULT_TIMECODE)
        if points is None:
            points = src.GetPointsAttr().Get()
        if points is None:
            points = get_first_time_sample(src.GetPointsAttr())
        if points is not None:
            dst.GetPointsAttr().Set(points)

        # 复制 CurveVertexCounts（每条曲线的顶点数）
        counts = src.GetCurveVertexCountsAttr().Get(DEFAULT_TIMECODE)
        if counts is None:
            counts = src.GetCurveVertexCountsAttr().Get()
        if counts is None:
            counts = get_first_time_sample(src.GetCurveVertexCountsAttr())
        if counts is not None:
            dst.GetCurveVertexCountsAttr().Set(counts)

        # 复制 Type（曲线类型：linear, cubic 等）
        curve_type = src.GetTypeAttr().Get()
        if curve_type:
            dst.GetTypeAttr().Set(curve_type)

        # 复制 Basis（基函数：bezier, bspline, catmullRom）
        basis = src.GetBasisAttr().Get()
        if basis:
            dst.GetBasisAttr().Set(basis)

        # 复制 Wrap（是否闭合：nonperiodic, periodic）
        wrap = src.GetWrapAttr().Get()
        if wrap:
            dst.GetWrapAttr().Set(wrap)

        # 复制 Widths（曲线宽度）
        widths = src.GetWidthsAttr().Get(DEFAULT_TIMECODE)
        if widths is None:
            widths = src.GetWidthsAttr().Get()
        if widths is not None and len(widths) > 0:
            dst.GetWidthsAttr().Set(widths)
            # 复制 widths 的插值模式
            widths_interp = src.GetWidthsInterpolation()
            if widths_interp:
                dst.SetWidthsInterpolation(widths_interp)

        # 复制 Normals（法线，如果有）
        normals = src.GetNormalsAttr().Get(DEFAULT_TIMECODE)
        if normals is None:
            normals = src.GetNormalsAttr().Get()
        if normals is not None and len(normals) > 0:
            dst.GetNormalsAttr().Set(normals)

        # 复制 Extent（边界框）
        extent = src.GetExtentAttr().Get(DEFAULT_TIMECODE)
        if extent is None:
            extent = src.GetExtentAttr().Get()
        if extent is not None:
            dst.GetExtentAttr().Set(extent)

        # 复制其他 Primvars（如颜色等，但不包括 UV，UV 会单独处理）
        src_api = UsdGeom.PrimvarsAPI(src.GetPrim())
        dst_api = UsdGeom.PrimvarsAPI(dst.GetPrim())
        for pv in src_api.GetPrimvars():
            pv_name = pv.GetPrimvarName()
            # 跳过 UV 相关的 primvar
            if pv_name in ("st", "st0", "st1", "st2", "uv", "UVMap"):
                continue
            if pv.HasValue():
                val = pv.Get(DEFAULT_TIMECODE)
                if val is None:
                    val = pv.Get()
                if val is not None:
                    try:
                        new_pv = dst_api.CreatePrimvar(
                            pv_name,
                            pv.GetTypeName(),
                            pv.GetInterpolation()
                        )
                        new_pv.Set(val)
                    except Exception:
                        pass  # 跳过无法复制的 primvar

    except Exception as e:
        if log:
            log(f"[Warning] Error copying curve data: {e}")