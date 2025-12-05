# -*- coding: utf-8 -*-
"""
Stage 工具模块
==============

提供与 Omniverse USD Stage 交互的通用工具函数。
这些函数被其他核心模块复用，保持代码 DRY 原则。
"""

from typing import List, Optional
from pxr import Usd
import omni.usd


# =============================================================================
# 常量定义
# =============================================================================

EXTENSION_TITLE = "Anim Drama Toolset"


# =============================================================================
# Stage 操作函数
# =============================================================================

def get_context() -> omni.usd.UsdContext:
    """
    获取当前 USD 上下文。

    Returns:
        UsdContext: Omniverse USD 上下文对象
    """
    return omni.usd.get_context()


def get_stage() -> Optional[Usd.Stage]:
    """
    获取当前打开的 USD Stage。

    Returns:
        Usd.Stage: 当前 Stage，如果没有打开的 Stage 则返回 None
    """
    return get_context().get_stage()


def get_selection_paths() -> List[str]:
    """
    获取当前选中的 Prim 路径列表。

    尝试多种 API 方法以兼容不同版本的 Omniverse Kit。

    Returns:
        List[str]: 选中的 Prim 路径字符串列表
    """
    ctx = get_context()
    sel = ctx.get_selection()

    paths = []
    # 尝试多种可能的 API 方法以保证兼容性
    candidate_methods = [
        "get_selected_prim_paths",
        "get_selected_paths",
        "get_selected_prim_paths_on_stage",
        "get_selected_paths_on_stage",
    ]

    for method_name in candidate_methods:
        method = getattr(sel, method_name, None)
        if not method:
            continue
        try:
            values = list(method())
            for path in values:
                if path not in paths:
                    paths.append(path)
        except Exception:
            pass

    return paths


def safe_log(msg: str, prefix: str = EXTENSION_TITLE) -> None:
    """
    安全地打印日志消息。

    Args:
        msg: 要打印的消息
        prefix: 日志前缀，默认为扩展名称
    """
    print(f"[{prefix}] {msg}")


def get_prim_at_path(path: str) -> Optional[Usd.Prim]:
    """
    根据路径获取 Prim 对象。

    Args:
        path: Prim 的 USD 路径

    Returns:
        Usd.Prim: Prim 对象，如果不存在则返回 None
    """
    stage = get_stage()
    if not stage:
        return None
    prim = stage.GetPrimAtPath(path)
    return prim if prim and prim.IsValid() else None
