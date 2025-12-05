# -*- coding: utf-8 -*-
"""
ViewModel 基类
==============

提供所有 ViewModel 的通用功能，包括：
    - 日志管理
    - 状态通知
    - 生命周期管理
"""

from typing import Callable, List, Optional


class BaseViewModel:
    """
    ViewModel 基类，提供通用的状态管理和日志功能。

    所有具体的 ViewModel 都应继承此类。

    Attributes:
        _log_callbacks: 日志监听器列表
        _status_callbacks: 状态变更监听器列表
        _log_history: 日志历史记录
    """

    def __init__(self):
        """初始化 ViewModel 基类。"""
        self._log_callbacks: List[Callable[[str], None]] = []
        self._status_callbacks: List[Callable[[str], None]] = []
        self._log_history: List[str] = []
        self._max_log_history = 1000  # 最大日志条数

    # =========================================================================
    # 日志管理
    # =========================================================================

    def add_log_callback(self, callback: Callable[[str], None]) -> None:
        """
        添加日志监听器。

        Args:
            callback: 当有新日志时调用的回调函数
        """
        if callback not in self._log_callbacks:
            self._log_callbacks.append(callback)

    def remove_log_callback(self, callback: Callable[[str], None]) -> None:
        """
        移除日志监听器。

        Args:
            callback: 要移除的回调函数
        """
        if callback in self._log_callbacks:
            self._log_callbacks.remove(callback)

    def log(self, message: str) -> None:
        """
        记录日志消息。

        Args:
            message: 日志消息
        """
        # 保存到历史
        self._log_history.append(message)
        if len(self._log_history) > self._max_log_history:
            self._log_history = self._log_history[-self._max_log_history:]

        # 通知所有监听器
        for callback in self._log_callbacks:
            try:
                callback(message)
            except Exception as e:
                print(f"[ViewModel] Log callback error: {e}")

        # 同时打印到控制台
        print(f"[{self.__class__.__name__}] {message}")

    def get_log_history(self) -> List[str]:
        """
        获取日志历史。

        Returns:
            List[str]: 日志历史列表
        """
        return self._log_history.copy()

    def clear_log_history(self) -> None:
        """清空日志历史。"""
        self._log_history.clear()

    # =========================================================================
    # 状态管理
    # =========================================================================

    def add_status_callback(self, callback: Callable[[str], None]) -> None:
        """
        添加状态变更监听器。

        Args:
            callback: 当状态变更时调用的回调函数
        """
        if callback not in self._status_callbacks:
            self._status_callbacks.append(callback)

    def remove_status_callback(self, callback: Callable[[str], None]) -> None:
        """
        移除状态变更监听器。

        Args:
            callback: 要移除的回调函数
        """
        if callback in self._status_callbacks:
            self._status_callbacks.remove(callback)

    def set_status(self, status: str) -> None:
        """
        设置并通知状态变更。

        Args:
            status: 新状态消息
        """
        for callback in self._status_callbacks:
            try:
                callback(status)
            except Exception as e:
                print(f"[ViewModel] Status callback error: {e}")

        # 状态也记录到日志
        self.log(f"Status: {status}")

    # =========================================================================
    # 生命周期
    # =========================================================================

    def dispose(self) -> None:
        """
        清理资源。

        子类应重写此方法以清理特定资源。
        """
        self._log_callbacks.clear()
        self._status_callbacks.clear()
        self._log_history.clear()
