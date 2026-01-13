# -*- coding: utf-8 -*-
"""
AOV EXR 合并模块
================

将多个单独的 AOV EXR 文件合并成一个多层 EXR 文件。

功能:
    - 扫描目录中的 AOV EXR 文件
    - 将多个 AOV 合并成一个多层 EXR
    - HdrColor/LdrColor 作为顶层 RGBA
    - 支持并行处理多帧
"""

import os
import re
import sys
import tempfile
import pathlib
import subprocess
from typing import List, Tuple, Dict, Optional, Callable

from .stage_utils import safe_log


# =============================================================================
# CLI 脚本内容（将在子进程中执行）
# =============================================================================

CLI_SCRIPT = r'''
import os, re, sys, subprocess, shutil
import concurrent.futures as fut

def ensure_deps():
    """确保 OpenEXR 和 Imath 库已安装"""
    try:
        import OpenEXR, Imath
        return
    except Exception:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
            subprocess.check_call([sys.executable, "-m", "pip", "install", "Imath", "OpenEXR"])
            import importlib
            importlib.invalidate_caches()
            import OpenEXR, Imath
        except Exception as e:
            print("ERROR: install OpenEXR/Imath failed:", e)
            sys.exit(2)

ensure_deps()
import OpenEXR, Imath

# 文件名模式: prefix.frame_aov.exr 或 prefix_aov.exr
RE_FRAME = re.compile(r"^(?P<prefix>.+?)\.(?P<frame>\d+)_(?P<aov>[A-Za-z0-9_]+)\.exr$", re.IGNORECASE)
RE_SINGLE = re.compile(r"^(?P<prefix>.+?)_(?P<aov>[A-Za-z0-9_]+)\.exr$", re.IGNORECASE)

def norm(s: str) -> str:
    return s.replace(" ", "").lower()

# 像素类型
PT = Imath.PixelType(Imath.PixelType.HALF)


def read_exr(path):
    """读取 EXR 文件"""
    exr = OpenEXR.InputFile(path)
    dw = exr.header()['dataWindow']
    w = dw.max.x - dw.min.x + 1
    h = dw.max.y - dw.min.y + 1
    chans = {c: exr.channel(c, PT) for c in exr.header()['channels'].keys()}
    exr.close()
    return w, h, chans


def add_layer(payload, hdrchs, layer, chans):
    """将通道添加到输出 payload"""
    def reg(name, blob):
        key = f"{name}" if (layer == "") else f"{layer}.{name}"
        payload[key] = blob
        hdrchs[key] = Imath.Channel(PT)

    keys = set(chans.keys())
    
    # RGBA 通道
    if {"R", "G", "B"}.issubset(keys):
        reg("R", chans["R"])
        reg("G", chans["G"])
        reg("B", chans["B"])
        if "A" in keys:
            reg("A", chans["A"])
        keys -= {"R", "G", "B", "A"}

    # XYZ 通道（法线等）
    if {"X", "Y", "Z"}.issubset(keys):
        reg("X", chans["X"])
        reg("Y", chans["Y"])
        reg("Z", chans["Z"])
        keys -= {"X", "Y", "Z"}

    # 单通道（如深度）
    rest = list(keys)
    if len(rest) == 1:
        reg("Y", chans[rest[0]])
    else:
        for k in rest:
            reg(k, chans[k])


def write_multilayer(out_path, default_rgba_path, named_layers):
    """写入多层 EXR"""
    if default_rgba_path is None and not named_layers:
        raise ValueError("No data to write")

    w = h = None
    payload = {}
    hdrchs = {}

    def _probe(p):
        nonlocal w, h
        _w, _h, _ = read_exr(p)
        if w is None:
            w, h = _w, _h
        elif (w, h) != (_w, _h):
            raise ValueError(f"Resolution mismatch: {p}")

    # 处理默认 RGBA（顶层）
    if default_rgba_path:
        _probe(default_rgba_path)
        _, _, ch0 = read_exr(default_rgba_path)
        add_layer(payload, hdrchs, "", ch0)

    # 处理其他 AOV 层
    for layer_name, p in named_layers.items():
        _probe(p)
        _, _, ch = read_exr(p)
        add_layer(payload, hdrchs, layer_name, ch)

    # 写入文件
    hdr = OpenEXR.Header(w, h)
    hdr["channels"] = hdrchs
    out = OpenEXR.OutputFile(out_path, hdr)
    out.writePixels(payload)
    out.close()


def scan_dir(src):
    """扫描目录，返回帧分组"""
    groups = {}
    single_frame = {}
    
    for fn in os.listdir(src):
        if not fn.lower().endswith(".exr"):
            continue
        
        path = os.path.join(src, fn)
        
        # 尝试匹配带帧号的模式
        m = RE_FRAME.match(fn)
        if m:
            fr = m.group("frame")
            aov_raw = m.group("aov")
            groups.setdefault(fr, []).append((aov_raw, path))
            continue
        
        # 尝试匹配无帧号的模式（单帧）
        m = RE_SINGLE.match(fn)
        if m:
            aov_raw = m.group("aov")
            single_frame[aov_raw] = path
    
    # 如果没有帧分组但有单帧文件，创建一个虚拟帧
    if not groups and single_frame:
        groups["0000"] = [(aov, path) for aov, path in single_frame.items()]
    
    return groups


def pack_one(task):
    """合并单帧的所有 AOV"""
    ensure_deps()
    import OpenEXR, Imath
    
    fr, items, outd, shot, keep = task
    try:
        def z4(s):
            return str(s).zfill(4)
        
        default_rgba = None
        layers = {}
        
        for aov_raw, p in items:
            # HdrColor 或 LdrColor 作为默认 RGBA
            if norm(aov_raw) in ("hdrcolor", "ldrcolor") and default_rgba is None:
                default_rgba = p
            else:
                layers[aov_raw] = p
        
        if not (default_rgba or layers):
            return (fr, None, "skip: no usable AOVs")

        out_path = os.path.join(outd, f"{shot}.{z4(fr)}.exr")

        # 如果只有默认 RGBA，直接复制
        if default_rgba and not layers:
            shutil.copy2(default_rgba, out_path)
        else:
            write_multilayer(out_path, default_rgba, layers)

        # 删除原始文件
        if not keep:
            for _, p in items:
                try:
                    os.remove(p)
                except:
                    pass
        
        return (fr, out_path, "ok")
    
    except Exception as e:
        return (fr, None, f"ERROR: {e}")


def main():
    """主函数"""
    if len(sys.argv) < 5:
        print("Usage: aov_merge_cli.py <src> <out_dir> <shot> <keepSingles 0/1> [HALF|FLOAT] [workers]")
        sys.exit(3)
    
    src, outd, shot, keep = sys.argv[1:5]
    keep = bool(int(keep))
    dtype = sys.argv[5] if len(sys.argv) > 5 else "HALF"
    workers = int(sys.argv[6]) if len(sys.argv) > 6 else 0

    global PT
    PT = Imath.PixelType(Imath.PixelType.HALF if dtype.upper().startswith('H') else Imath.PixelType.FLOAT)

    os.makedirs(outd, exist_ok=True)

    groups = scan_dir(src)
    frames = sorted(groups.keys(), key=lambda s: int(s) if s.isdigit() else 0)
    
    if not frames:
        print("No frames found.")
        return
    
    print(f"Found frames: {len(frames)} | dtype={dtype} | workers={'auto' if workers <= 0 else workers}")

    tasks = [(fr, groups[fr], outd, shot, keep) for fr in frames]

    # 选择工作线程数
    if workers <= 0:
        import os as _os
        workers = max(1, (_os.cpu_count() or 4) - 1)

    done = 0
    with fut.ProcessPoolExecutor(max_workers=workers) as ex:
        for fr, out_path, status in ex.map(pack_one, tasks, chunksize=1):
            done += 1
            if status == 'ok':
                print(f"[{done}/{len(tasks)}] packed {out_path}")
            else:
                print(f"[{done}/{len(tasks)}] {status} (frame {fr})")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        print("ERROR:", e)
        print(traceback.format_exc())
        sys.exit(1)
'''


# =============================================================================
# 辅助函数
# =============================================================================

def _get_kit_python_exe() -> Optional[pathlib.Path]:
    """获取 Kit 的 Python 可执行文件路径"""
    # 在 Kit 环境中，sys.executable 是 kit.exe
    # python.exe 在 kit/python/python.exe
    kit_path = pathlib.Path(sys.executable).parent
    
    # 尝试几个可能的路径
    candidates = [
        kit_path / "python" / "python.exe",
        kit_path / "python.exe",
        kit_path.parent / "python" / "python.exe",
    ]
    
    for p in candidates:
        if p.exists():
            return p
    
    return None


def _install_openexr_imath() -> Tuple[bool, str]:
    """安装 OpenEXR 和 Imath 库"""
    py = _get_kit_python_exe()
    if not py:
        return False, "Kit python.exe not found"
    
    try:
        subprocess.check_call([str(py), "-m", "pip", "install", "--upgrade", "pip"])
        subprocess.check_call([str(py), "-m", "pip", "install", "Imath", "OpenEXR"])
        return True, "Installed OpenEXR and Imath"
    except Exception as e:
        return False, f"pip install failed: {e}"


def check_openexr_available() -> Tuple[bool, str]:
    """检查 OpenEXR 是否可用"""
    try:
        import OpenEXR
        import Imath
        return True, "OpenEXR/Imath ready"
    except ImportError:
        return False, "OpenEXR/Imath not installed"


def ensure_openexr_available() -> Tuple[bool, str]:
    """确保 OpenEXR 可用，如果不可用则尝试安装"""
    ok, msg = check_openexr_available()
    if ok:
        return True, msg
    
    # 尝试安装
    safe_log("[AOV Merge] OpenEXR not found, attempting to install...")
    ok, msg = _install_openexr_imath()
    if ok:
        # 重新检查
        import importlib
        importlib.invalidate_caches()
        return check_openexr_available()
    
    return False, msg


# =============================================================================
# 扫描功能
# =============================================================================

# 文件名模式
RE_FRAME = re.compile(r"^(?P<prefix>.+?)\.(?P<frame>\d+)_(?P<aov>[A-Za-z0-9_]+)\.exr$", re.IGNORECASE)
RE_SINGLE = re.compile(r"^(?P<prefix>.+?)_(?P<aov>[A-Za-z0-9_]+)\.exr$", re.IGNORECASE)


def scan_aov_files(src_dir: str) -> Dict[str, List[Tuple[str, str]]]:
    """
    扫描目录中的 AOV EXR 文件。
    
    Args:
        src_dir: 源目录
        
    Returns:
        Dict[帧号, List[(AOV名称, 文件路径)]]
    """
    if not os.path.isdir(src_dir):
        return {}
    
    groups = {}
    single_frame = {}
    
    for fn in os.listdir(src_dir):
        if not fn.lower().endswith(".exr"):
            continue
        
        path = os.path.join(src_dir, fn)
        
        # 尝试匹配带帧号的模式
        m = RE_FRAME.match(fn)
        if m:
            fr = m.group("frame")
            aov_raw = m.group("aov")
            groups.setdefault(fr, []).append((aov_raw, path))
            continue
        
        # 尝试匹配无帧号的模式（单帧）
        m = RE_SINGLE.match(fn)
        if m:
            aov_raw = m.group("aov")
            single_frame[aov_raw] = path
    
    # 如果没有帧分组但有单帧文件，创建一个虚拟帧
    if not groups and single_frame:
        groups["0000"] = [(aov, path) for aov, path in single_frame.items()]
    
    return groups


def get_scan_summary(src_dir: str) -> Tuple[int, List[str], str]:
    """
    获取目录扫描摘要。
    
    Args:
        src_dir: 源目录
        
    Returns:
        Tuple[帧数, AOV列表, 消息]
    """
    groups = scan_aov_files(src_dir)
    
    if not groups:
        return 0, [], "No AOV EXR files found"
    
    # 获取所有唯一的 AOV 名称
    all_aovs = set()
    for frame_items in groups.values():
        for aov_name, _ in frame_items:
            all_aovs.add(aov_name)
    
    frame_count = len(groups)
    aov_list = sorted(all_aovs)
    
    msg = f"Found {frame_count} frame(s), {len(aov_list)} AOV(s): {', '.join(aov_list[:5])}"
    if len(aov_list) > 5:
        msg += f"... (+{len(aov_list) - 5} more)"
    
    return frame_count, aov_list, msg


# =============================================================================
# 合并功能
# =============================================================================

def merge_aovs_external(
    src_dir: str,
    output_dir: str,
    shot_name: str = "render",
    keep_singles: bool = True,
    dtype: str = "HALF",
    workers: int = 0,
    progress_callback: Optional[Callable[[str], None]] = None
) -> Tuple[bool, str]:
    """
    使用外部进程合并 AOV 文件。
    
    这是推荐的方式，因为它在独立进程中运行，不会影响 Kit 主进程。
    
    Args:
        src_dir: 源目录（包含单独的 AOV EXR 文件）
        output_dir: 输出目录
        shot_name: Shot 名称（用于输出文件命名）
        keep_singles: 是否保留原始的单独文件
        dtype: 像素类型 ("HALF" 或 "FLOAT")
        workers: 工作进程数（0 = 自动）
        progress_callback: 进度回调函数
        
    Returns:
        Tuple[bool, str]: (是否成功, 消息)
    """
    if not os.path.isdir(src_dir):
        return False, f"Source directory not found: {src_dir}"
    
    # 扫描检查
    frame_count, aov_list, scan_msg = get_scan_summary(src_dir)
    if frame_count == 0:
        return False, scan_msg
    
    if progress_callback:
        progress_callback(f"Scanning: {scan_msg}")
    
    # 获取 Kit Python
    py = _get_kit_python_exe()
    if not py:
        return False, "Kit python.exe not found"
    
    # 写入 CLI 脚本到临时文件
    tmp_py = pathlib.Path(tempfile.gettempdir()) / "aov_merge_cli.py"
    tmp_py.write_text(CLI_SCRIPT, encoding="utf-8")
    
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    # 构建命令
    keep_flag = "1" if keep_singles else "0"
    cmd = [
        str(py),
        str(tmp_py),
        src_dir,
        output_dir,
        shot_name,
        keep_flag,
        dtype,
        str(workers)
    ]
    
    if progress_callback:
        progress_callback(f"Running merge... workers={workers}, dtype={dtype}")
    
    safe_log(f"[AOV Merge] Running: {' '.join(cmd)}")
    
    try:
        # 运行外部进程
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600  # 1小时超时
        )
        
        # 记录输出
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                safe_log(f"[AOV Merge] {line}")
                if progress_callback:
                    progress_callback(line)
        
        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            safe_log(f"[AOV Merge] ERROR: {error_msg}")
            return False, f"Merge failed: {error_msg}"
        
        msg = f"Successfully merged {frame_count} frame(s) to {output_dir}"
        safe_log(f"[AOV Merge] {msg}")
        return True, msg
        
    except subprocess.TimeoutExpired:
        return False, "Merge process timed out"
    except Exception as e:
        return False, f"Error running merge: {e}"


def merge_aovs_single_frame(
    src_dir: str,
    output_path: str,
    shot_name: str = "render"
) -> Tuple[bool, str]:
    """
    合并单帧的 AOV 文件（在当前进程中执行）。
    
    适用于已安装 OpenEXR 且只需要处理单帧的情况。
    
    Args:
        src_dir: 源目录
        output_path: 输出文件路径
        shot_name: Shot 名称
        
    Returns:
        Tuple[bool, str]: (是否成功, 消息)
    """
    # 检查 OpenEXR
    ok, msg = check_openexr_available()
    if not ok:
        return False, msg
    
    import OpenEXR
    import Imath
    
    # 扫描文件
    groups = scan_aov_files(src_dir)
    if not groups:
        return False, "No AOV files found"
    
    # 只处理第一帧
    frame = sorted(groups.keys())[0]
    items = groups[frame]
    
    # 分离默认 RGBA 和其他层
    default_rgba = None
    layers = {}
    
    for aov_name, path in items:
        aov_lower = aov_name.lower()
        if aov_lower in ("hdrcolor", "ldrcolor") and default_rgba is None:
            default_rgba = path
        else:
            layers[aov_name] = path
    
    if not default_rgba and not layers:
        return False, "No usable AOV files"
    
    try:
        PT = Imath.PixelType(Imath.PixelType.HALF)
        
        w = h = None
        payload = {}
        hdrchs = {}
        
        def read_exr(path):
            exr = OpenEXR.InputFile(path)
            dw = exr.header()['dataWindow']
            _w = dw.max.x - dw.min.x + 1
            _h = dw.max.y - dw.min.y + 1
            chans = {c: exr.channel(c, PT) for c in exr.header()['channels'].keys()}
            exr.close()
            return _w, _h, chans
        
        def add_layer(layer_name, chans):
            def reg(name, blob):
                key = f"{name}" if (layer_name == "") else f"{layer_name}.{name}"
                payload[key] = blob
                hdrchs[key] = Imath.Channel(PT)
            
            keys = set(chans.keys())
            if {"R", "G", "B"}.issubset(keys):
                reg("R", chans["R"])
                reg("G", chans["G"])
                reg("B", chans["B"])
                if "A" in keys:
                    reg("A", chans["A"])
                keys -= {"R", "G", "B", "A"}
            
            if {"X", "Y", "Z"}.issubset(keys):
                reg("X", chans["X"])
                reg("Y", chans["Y"])
                reg("Z", chans["Z"])
                keys -= {"X", "Y", "Z"}
            
            rest = list(keys)
            if len(rest) == 1:
                reg("Y", chans[rest[0]])
            else:
                for k in rest:
                    reg(k, chans[k])
        
        # 读取默认 RGBA
        if default_rgba:
            w, h, chans = read_exr(default_rgba)
            add_layer("", chans)
        
        # 读取其他层
        for layer_name, path in layers.items():
            _w, _h, chans = read_exr(path)
            if w is None:
                w, h = _w, _h
            elif (w, h) != (_w, _h):
                return False, f"Resolution mismatch: {path}"
            add_layer(layer_name, chans)
        
        # 写入文件
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        hdr = OpenEXR.Header(w, h)
        hdr["channels"] = hdrchs
        out = OpenEXR.OutputFile(output_path, hdr)
        out.writePixels(payload)
        out.close()
        
        msg = f"Merged {len(layers) + (1 if default_rgba else 0)} AOVs to {output_path}"
        safe_log(f"[AOV Merge] {msg}")
        return True, msg
        
    except Exception as e:
        return False, f"Merge error: {e}"


# =============================================================================
# 高级 API
# =============================================================================

def auto_merge_aovs(
    src_dir: str,
    output_dir: Optional[str] = None,
    shot_name: str = "render",
    keep_singles: bool = True
) -> Tuple[bool, str, Optional[str]]:
    """
    自动合并 AOV 文件。
    
    这是最简单的 API，会自动处理目录中的所有 AOV 文件。
    
    Args:
        src_dir: 源目录
        output_dir: 输出目录（默认为 src_dir/merged）
        shot_name: Shot 名称
        keep_singles: 是否保留原始文件
        
    Returns:
        Tuple[bool, str, Optional[str]]: (是否成功, 消息, 输出目录)
    """
    if output_dir is None:
        output_dir = os.path.join(src_dir, "merged")
    
    success, msg = merge_aovs_external(
        src_dir=src_dir,
        output_dir=output_dir,
        shot_name=shot_name,
        keep_singles=keep_singles
    )
    
    return success, msg, output_dir if success else None

