# -*- coding: utf-8 -*-
"""
EXR AOV 自动合并
================

将多个AOV EXR文件合并成一个多层EXR文件。

功能特性:
    - 自动检测AOV EXR文件并合并为多层EXR
    - HdrColor 写入顶层 RGBA (无层前缀)
    - 其他AOV保留原始文件名作为层名
    - 支持并行处理多帧
    - 支持 HALF/FLOAT 数据类型选择
    - 可选删除原始单独AOV文件
"""

import os
import re
import sys
import pathlib
import tempfile
import subprocess
from typing import List, Optional, Tuple, Dict, Callable

import omni.kit.app as kit

# 文件名模式: Capture.0001_HdrColor.exr
RE_CAP = re.compile(
    r"^(?P<prefix>.+?)\.(?P<frame>\d+)\_(?P<aov>[A-Za-z0-9_]+)\.exr$",
    re.IGNORECASE
)

# ---------------------------------------------------------------------------
# CLI worker script (执行于子进程 kit/python.exe)
# ---------------------------------------------------------------------------
CLI_SCRIPT = r'''
import os, re, sys, traceback, subprocess, shutil
import concurrent.futures as fut

# ensure deps in the child process (and in workers)
def ensure_deps():
    try:
        import OpenEXR, Imath  # noqa
        return
    except Exception:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
            subprocess.check_call([sys.executable, "-m", "pip", "install", "Imath", "OpenEXR"])
            import importlib; importlib.invalidate_caches()
            import OpenEXR, Imath  # noqa
        except Exception as e:
            print("ERROR: install OpenEXR/Imath failed:", e); sys.exit(2)

ensure_deps()
import OpenEXR, Imath

RE = re.compile(r"^(?P<prefix>.+?)\.(?P<frame>\d+)\_(?P<aov>[A-Za-z0-9_]+)\.exr$", re.IGNORECASE)

def norm(s:str)->str: return s.replace(" ","").lower()

# Pixel type is configured globally per run
PT = Imath.PixelType(Imath.PixelType.HALF)


def read_exr(path):
    exr = OpenEXR.InputFile(path)
    dw = exr.header()['dataWindow']
    w  = dw.max.x - dw.min.x + 1
    h  = dw.max.y - dw.min.y + 1
    chans = {c: exr.channel(c, PT) for c in exr.header()['channels'].keys()}
    exr.close()
    return w, h, chans


def add_layer(payload, hdrchs, layer, chans):
    def reg(name, blob):
        key = f"{name}" if (layer == "") else f"{layer}.{name}"
        payload[key] = blob
        hdrchs[key] = Imath.Channel(PT)

    keys = set(chans.keys())
    if {"R","G","B"}.issubset(keys):
        reg("R", chans["R"]); reg("G", chans["G"]); reg("B", chans["B"])
        if "A" in keys: reg("A", chans["A"])
        keys -= {"R","G","B","A"}

    if {"X","Y","Z"}.issubset(keys):
        reg("X", chans["X"]); reg("Y", chans["Y"]); reg("Z", chans["Z"])
        keys -= {"X","Y","Z"}

    rest = list(keys)
    if len(rest) == 1:
        reg("Y", chans[rest[0]])
    else:
        for k in rest:
            reg(k, chans[k])


def write_multilayer(out_path, default_rgba_path, named_layers):
    # default_rgba_path: file to be written to top-level RGBA (no prefix)
    if default_rgba_path is None and not named_layers:
        raise ValueError("No data to write")

    w=h=None
    payload = {}
    hdrchs = {}

    def _probe(p):
        nonlocal w,h
        _w,_h,_ = read_exr(p)
        if w is None: w,h = _w,_h
        elif (w,h)!=(_w,_h):
            raise ValueError(f"Resolution mismatch: {p}")

    if default_rgba_path:
        _probe(default_rgba_path)
        _,_,ch0 = read_exr(default_rgba_path)
        add_layer(payload, hdrchs, "", ch0)  # top-level RGBA

    for layer_name, p in named_layers.items():
        _probe(p)
        _,_,ch = read_exr(p)
        add_layer(payload, hdrchs, layer_name, ch)

    hdr = OpenEXR.Header(w, h)
    hdr["channels"] = hdrchs
    out = OpenEXR.OutputFile(out_path, hdr)
    out.writePixels(payload)
    out.close()


def scan_dir(src):
    # Return mapping: frame -> list of (aov_raw, path). Keep original AOV name
    groups = {}
    for fn in os.listdir(src):
        if not fn.lower().endswith(".exr"): continue
        m = RE.match(fn)
        if not m: continue
        fr   = m.group("frame")
        aov_raw = m.group("aov")  # original case/name
        path = os.path.join(src, fn)
        groups.setdefault(fr, []).append((aov_raw, path))
    return groups


def _pack_one(task):
    # called inside workers
    ensure_deps()
    import OpenEXR, Imath  # noqa
    fr, items, outd, shot, keep = task
    try:
        def z4(s): return str(s).zfill(4)
        default_rgba = None
        layers = {}
        for aov_raw, p in items:
            if norm(aov_raw) == "hdrcolor" and default_rgba is None:
                default_rgba = p
            else:
                layers[aov_raw] = p  # keep original AOV name

        if not (default_rgba or layers):
            return (fr, None, "skip: no usable AOVs")

        out_path = os.path.join(outd, f"{shot}.{z4(fr)}.exr")

        # fast path
        if default_rgba and not layers:
            shutil.copy2(default_rgba, out_path)
        else:
            write_multilayer(out_path, default_rgba, layers)

        if not keep:
            for _, p in items:
                try: os.remove(p)
                except: pass
        return (fr, out_path, "ok")
    except Exception as e:
        return (fr, None, f"ERROR: {e}")


def main():
    # argv: src out_dir shot keep [dtype HALF|FLOAT] [workers int]
    if len(sys.argv) < 5:
        print("Usage: exr_pack_cli.py <src> <out_dir> <shot> <keepSingles 0/1> [HALF|FLOAT] [workers]")
        sys.exit(3)
    src, outd, shot, keep = sys.argv[1:5]
    keep = bool(int(keep))
    dtype = sys.argv[5] if len(sys.argv) > 5 else "HALF"
    workers = int(sys.argv[6]) if len(sys.argv) > 6 else 0

    global PT
    PT = Imath.PixelType(Imath.PixelType.HALF if dtype.upper().startswith('H') else Imath.PixelType.FLOAT)

    os.makedirs(outd, exist_ok=True)

    groups = scan_dir(src)
    frames = sorted(groups.keys(), key=lambda s:int(s))
    if not frames:
        print("No frames found.")
        return
    print(f"Found frames: {len(frames)} | dtype={dtype} | workers={'auto' if workers<=0 else workers}")

    tasks = [(fr, groups[fr], outd, shot, keep) for fr in frames]

    # pick worker count
    if workers <= 0:
        import os as _os
        workers = max(1, (_os.cpu_count() or 4) - 1)

    done = 0
    with fut.ProcessPoolExecutor(max_workers=workers) as ex:
        for fr, out_path, status in ex.map(_pack_one, tasks, chunksize=1):
            done += 1
            if status == 'ok':
                print(f"[{done}/{len(tasks)}] packed {out_path}")
            else:
                print(f"[{done}/{len(tasks)}] {status} (frame {fr})")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ERROR:", e)
        print(traceback.format_exc())
        sys.exit(1)
'''


def _kit_python_exe() -> pathlib.Path:
    """获取 Kit 内置的 python.exe 路径。"""
    return pathlib.Path(sys.executable).parent / "python" / "python.exe"


def install_openexr_imath_via_kit_python() -> Tuple[bool, str]:
    """通过 kit/python.exe 安装 OpenEXR/Imath。"""
    py = _kit_python_exe()
    if not py.exists():
        return False, f"Kit python.exe not found: {py}"
    try:
        subprocess.check_call([str(py), "-m", "pip", "install", "--upgrade", "pip"])
        subprocess.check_call([str(py), "-m", "pip", "install", "Imath", "OpenEXR"])
        return True, "Installed via kit/python.exe"
    except Exception as e:
        return False, f"pip install failed: {e}"


def ensure_openexr_imath_in_proc() -> Tuple[bool, str]:
    """确保 OpenEXR/Imath 在当前进程中可用。"""
    import importlib
    try:
        import OpenEXR, Imath  # noqa
        return True, "OpenEXR/Imath ready."
    except Exception:
        pass
    
    # 尝试使用 pipapi
    try:
        mgr = kit.get_app().get_extension_manager()
        if not mgr.is_extension_enabled("omni.kit.pipapi"):
            mgr.set_extension_enabled("omni.kit.pipapi", True)
        import omni.kit.pipapi as pipapi
        pi = getattr(pipapi, "get", None)() if hasattr(pipapi, "get") else \
             getattr(pipapi, "PipAPI", None)()
        if pi:
            pi.install("Imath")
            pi.install("OpenEXR")
            importlib.invalidate_caches()
            import OpenEXR, Imath  # noqa
            return True, "Installed via pipapi"
    except Exception as e:
        last = f"pipapi failed: {e}"
    
    # 回退到 kit/python.exe
    ok, why = install_openexr_imath_via_kit_python()
    if ok:
        try:
            import OpenEXR, Imath  # noqa
        except Exception:
            pass
        return True, "Installed via kit/python.exe"
    return False, f"{last if 'last' in locals() else ''} | {why}"


def scan_frames(dir_path: str) -> List[str]:
    """
    扫描目录中的帧列表。
    
    Args:
        dir_path: 源目录路径
        
    Returns:
        排序后的帧号列表
    """
    frames = set()
    if not os.path.isdir(dir_path):
        return []
    for fn in os.listdir(dir_path):
        if not fn.lower().endswith(".exr"):
            continue
        m = RE_CAP.match(fn)
        if not m:
            continue
        frames.add(m.group("frame"))
    return sorted(frames, key=lambda s: int(s))


def scan_aovs(dir_path: str) -> List[str]:
    """
    扫描目录中的AOV列表。
    
    Args:
        dir_path: 源目录路径
        
    Returns:
        AOV名称列表
    """
    aovs = set()
    if not os.path.isdir(dir_path):
        return []
    for fn in os.listdir(dir_path):
        if not fn.lower().endswith(".exr"):
            continue
        m = RE_CAP.match(fn)
        if not m:
            continue
        aovs.add(m.group("aov"))
    return sorted(aovs)


def run_merge_external(
    src_dir: str,
    out_dir: str,
    shot_name: str,
    keep_singles: bool,
    dtype: str,
    workers: int,
    log_callback: Optional[Callable[[str], None]] = None
) -> Tuple[bool, str]:
    """
    运行外部合并进程。
    
    Args:
        src_dir: 源目录
        out_dir: 输出目录
        shot_name: 镜头名称
        keep_singles: 是否保留原始AOV文件
        dtype: 数据类型 (HALF/FLOAT)
        workers: 工作进程数 (0=自动)
        log_callback: 日志回调函数
        
    Returns:
        (成功标志, 消息)
    """
    def log(msg: str):
        if log_callback:
            log_callback(msg)
        print(f"[EXR Merge] {msg}")
    
    if not src_dir or not os.path.isdir(src_dir):
        return False, "Invalid source folder."
    
    if not out_dir:
        out_dir = os.path.join(src_dir, "packed")
    
    os.makedirs(out_dir, exist_ok=True)
    
    # 写入临时CLI脚本
    tmp_py = pathlib.Path(tempfile.gettempdir()) / "exr_pack_cli.py"
    tmp_py.write_text(CLI_SCRIPT, encoding="utf-8")
    
    # 获取 kit/python.exe
    py = _kit_python_exe()
    if not py.exists():
        return False, f"Kit python.exe not found: {py}"
    
    keep_flag = "1" if keep_singles else "0"
    cmd = [str(py), str(tmp_py), src_dir, out_dir, shot_name, keep_flag, dtype, str(workers)]
    
    log(f"Running Auto-Merge... workers={workers} dtype={dtype}")
    
    try:
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.stdout:
            for line in p.stdout.strip().split('\n'):
                log(line)
        if p.returncode != 0:
            if p.stderr:
                log(p.stderr.strip())
            return False, "Merge failed."
        return True, f"Done. Output => {out_dir}"
    except Exception as e:
        return False, f"External pack error: {e}"

