# -*- coding: utf-8 -*-
"""
Stage 工具模块
==============

提供与 Omniverse USD Stage 交互的通用工具函数。
这些函数被其他核心模块复用，保持代码 DRY 原则。
"""

import threading
from typing import Any, Callable, List, Optional, TypeVar

from pxr import Usd
import omni.usd

T = TypeVar("T")


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


# =============================================================================
# 主线程 marshal
# =============================================================================
#
# Anime agent 在 ThreadPoolExecutor worker 线程跑 tool 函数。USD 写操作
# （Xform.Define / AddReference / 设置 EditTarget / SetSelected 等）经过 USD
# composition + Hydra 失效路径，会和 Kit 主渲染线程争 layer/composition 锁，
# 容易整个 UI 死锁。
#
# 这个 helper 把一段闭包推到 Kit 主线程下一帧执行，worker 阻塞等结果。
# 已经在主线程里调用时，直接执行（避免自己等自己）。

def run_on_main_thread(func: Callable[[], T], *, timeout: float = 120.0) -> T:
    """Run ``func`` on Kit's main thread (next update tick) and block the
    caller until it returns.

    - If already on the main thread, runs synchronously (no marshalling).
    - If Kit is not running (no `omni.kit.app` available), runs synchronously
      so unit tests / headless callers still work.
    - Re-raises any exception ``func`` raised so callers can wrap with
      try/except as if they ran ``func`` themselves.
    - On marshal timeout, raises ``RuntimeError``.
    """
    if threading.current_thread() is threading.main_thread():
        return func()

    try:
        import omni.kit.app  # local import keeps stage_utils importable in tests
    except Exception:
        return func()

    result_holder: dict = {}
    done = threading.Event()
    sub_holder: list = [None]

    def _on_update(_evt: Any) -> None:
        sub = sub_holder[0]
        sub_holder[0] = None
        if sub is not None:
            try:
                sub.unsubscribe()
            except Exception:
                pass
        try:
            result_holder["value"] = func()
        except BaseException as e:  # propagate everything, including KeyboardInterrupt
            result_holder["error"] = e
        finally:
            done.set()

    sub_holder[0] = (
        omni.kit.app.get_app()
        .get_update_event_stream()
        .create_subscription_to_pop(_on_update, name="anim.drama.toolset.tool_main_marshal")
    )

    if not done.wait(timeout):
        # Best-effort cleanup; subscription will fire harmlessly later.
        sub = sub_holder[0]
        sub_holder[0] = None
        if sub is not None:
            try:
                sub.unsubscribe()
            except Exception:
                pass
        raise RuntimeError(
            f"run_on_main_thread timed out after {timeout:.1f}s; "
            "the Kit update loop may be stuck or the call took too long"
        )

    if "error" in result_holder:
        raise result_holder["error"]
    return result_holder["value"]
