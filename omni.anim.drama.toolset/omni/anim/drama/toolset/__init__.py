# -*- coding: utf-8 -*-
"""
Anim Drama Toolset
==================

Omniverse 动画制作工具集。
"""

from .extension import AnimDramaToolsetExtension

# 存储扩展实例的全局变量
_extension_instance = None


def _set_instance(instance):
    """内部使用：设置扩展实例。"""
    global _extension_instance
    _extension_instance = instance


def show_window():
    """显示工具窗口。"""
    if _extension_instance and hasattr(_extension_instance, '_window'):
        _extension_instance._window.show()


def hide_window():
    """隐藏工具窗口。"""
    if _extension_instance and hasattr(_extension_instance, '_window'):
        _extension_instance._window.hide()


def toggle_window():
    """切换窗口可见性。"""
    if _extension_instance and hasattr(_extension_instance, '_window'):
        _extension_instance._window.toggle()
