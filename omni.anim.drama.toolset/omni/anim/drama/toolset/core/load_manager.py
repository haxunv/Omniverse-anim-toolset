# -*- coding: utf-8 -*-
"""
角色加载管理器核心逻辑
======================

提供 Prim 的加载（Load/Activate）和卸载（Unload/Deactivate）功能。
这些函数直接操作 USD Stage，不涉及 UI 逻辑。

主要功能:
    - load_or_activate: 激活 Prim 并加载 Payload
    - unload_or_deactivate: 停用 Prim
"""

from typing import Tuple
from .stage_utils import get_stage, safe_log


# =============================================================================
# 核心操作函数
# =============================================================================

def load_or_activate(path: str) -> Tuple[bool, str]:
    """
    激活指定路径的 Prim，并在有 Payload 时加载它。

    此操作等价于在 Stage 面板中右键选择 "Activate"。

    Args:
        path: Prim 的 USD 路径

    Returns:
        Tuple[bool, str]: (是否成功, 操作消息)
    """
    stage = get_stage()
    if not stage:
        return False, "No stage available"

    prim = stage.GetPrimAtPath(path)
    if not prim:
        msg = f"Prim not found: {path}"
        safe_log(f"[Load] {msg}")
        return False, msg

    try:
        # 激活 Prim
        prim.SetActive(True)

        # 如果有 Payload，加载它
        if prim.HasPayload():
            stage.Load(prim.GetPath())

        msg = f"Activated (and loaded if payload): {path}"
        safe_log(f"[Load] {msg}")
        return True, msg

    except Exception as e:
        msg = f"Error activating {path}: {e}"
        safe_log(f"[Load] {msg}")
        return False, msg


def unload_or_deactivate(path: str) -> Tuple[bool, str]:
    """
    停用指定路径的 Prim。

    此操作等价于在 Stage 面板中右键选择 "Deactivate"。

    Args:
        path: Prim 的 USD 路径

    Returns:
        Tuple[bool, str]: (是否成功, 操作消息)
    """
    stage = get_stage()
    if not stage:
        return False, "No stage available"

    prim = stage.GetPrimAtPath(path)
    if not prim:
        msg = f"Prim not found: {path}"
        safe_log(f"[Unload] {msg}")
        return False, msg

    try:
        prim.SetActive(False)
        msg = f"Deactivated: {path}"
        safe_log(f"[Unload] {msg}")
        return True, msg

    except Exception as e:
        msg = f"Error deactivating {path}: {e}"
        safe_log(f"[Unload] {msg}")
        return False, msg


def batch_load(paths: list) -> Tuple[int, int, list]:
    """
    批量加载多个 Prim。

    Args:
        paths: Prim 路径列表

    Returns:
        Tuple[int, int, list]: (成功数, 失败数, 消息列表)
    """
    success_count = 0
    fail_count = 0
    messages = []

    for path in paths:
        success, msg = load_or_activate(path)
        messages.append(msg)
        if success:
            success_count += 1
        else:
            fail_count += 1

    return success_count, fail_count, messages


def batch_unload(paths: list) -> Tuple[int, int, list]:
    """
    批量卸载多个 Prim。

    Args:
        paths: Prim 路径列表

    Returns:
        Tuple[int, int, list]: (成功数, 失败数, 消息列表)
    """
    success_count = 0
    fail_count = 0
    messages = []

    for path in paths:
        success, msg = unload_or_deactivate(path)
        messages.append(msg)
        if success:
            success_count += 1
        else:
            fail_count += 1

    return success_count, fail_count, messages
