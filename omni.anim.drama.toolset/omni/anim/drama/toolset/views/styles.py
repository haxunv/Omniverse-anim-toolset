# -*- coding: utf-8 -*-
"""
统一样式定义
============

定义插件中使用的所有 UI 样式常量。
集中管理样式以保持视觉一致性。
"""


class Colors:
    """颜色常量定义。"""

    # 主题色
    PRIMARY = 0xFF3A8EBA          # 主蓝色
    PRIMARY_HOVER = 0xFF4DA3CF    # 主蓝色悬停
    PRIMARY_DARK = 0xFF2A6E9A     # 深蓝色

    # 功能色
    SUCCESS = 0xFF00FF00          # 成功/确认 - 绿色
    WARNING = 0xFFFFAA00          # 警告 - 橙色
    ERROR = 0xFFFF4444            # 错误 - 红色
    INFO = 0xFF00AAFF             # 信息 - 浅蓝色

    # 中性色
    TEXT_PRIMARY = 0xFFE0E0E0     # 主要文字
    TEXT_SECONDARY = 0xFFA0A0A0   # 次要文字
    TEXT_DISABLED = 0xFF606060    # 禁用文字

    BACKGROUND = 0xFF303030       # 背景色
    BACKGROUND_LIGHT = 0xFF404040 # 浅背景
    BACKGROUND_DARK = 0xFF202020  # 深背景

    BORDER = 0xFF505050           # 边框色
    SEPARATOR = 0xFF454545        # 分隔线


class Sizes:
    """尺寸常量定义。"""

    # 边距
    MARGIN_SMALL = 4
    MARGIN_MEDIUM = 8
    MARGIN_LARGE = 12

    # 间距
    SPACING_SMALL = 4
    SPACING_MEDIUM = 8
    SPACING_LARGE = 12

    # 组件尺寸
    BUTTON_HEIGHT = 26
    BUTTON_HEIGHT_LARGE = 34
    INPUT_HEIGHT = 24
    LABEL_WIDTH = 180
    LABEL_WIDTH_SMALL = 100

    # 日志区域
    LOG_HEIGHT = 140
    STATUS_HEIGHT = 42

    # 窗口默认尺寸
    WINDOW_WIDTH = 580
    WINDOW_HEIGHT = 600


class Styles:
    """
    样式集合类。

    提供预定义的样式字典，用于 omni.ui 组件。
    """

    # =========================================================================
    # 按钮样式
    # =========================================================================

    BUTTON_PRIMARY = {
        "background_color": Colors.PRIMARY,
        "border_radius": 4,
    }

    BUTTON_SUCCESS = {
        "color": Colors.SUCCESS,
        "font_size": 14,
    }

    BUTTON_WARNING = {
        "color": Colors.WARNING,
    }

    BUTTON_DANGER = {
        "color": Colors.ERROR,
    }

    # =========================================================================
    # 输入框样式
    # =========================================================================

    INPUT_DEFAULT = {
        "background_color": Colors.BACKGROUND_DARK,
        "border_color": Colors.BORDER,
        "border_radius": 3,
    }

    INPUT_MULTILINE = {
        "background_color": Colors.BACKGROUND_DARK,
        "border_color": Colors.BORDER,
        "border_radius": 3,
    }

    # =========================================================================
    # 标签样式
    # =========================================================================

    LABEL_HEADER = {
        "font_size": 16,
        "color": Colors.TEXT_PRIMARY,
    }

    LABEL_NORMAL = {
        "color": Colors.TEXT_PRIMARY,
    }

    LABEL_SECONDARY = {
        "color": Colors.TEXT_SECONDARY,
    }

    LABEL_PATH = {
        "color": Colors.TEXT_SECONDARY,
        "word_wrap": True,
    }

    # =========================================================================
    # 容器样式
    # =========================================================================

    FRAME_DEFAULT = {
        "background_color": Colors.BACKGROUND,
        "border_radius": 4,
    }

    SCROLLING_FRAME = {
        "background_color": Colors.BACKGROUND_DARK,
        "border_color": Colors.BORDER,
        "border_radius": 3,
    }

    # =========================================================================
    # 工具方法
    # =========================================================================

    @staticmethod
    def get_path_label_style(height: int = 36) -> dict:
        """
        获取路径显示标签的样式。

        Args:
            height: 标签高度

        Returns:
            dict: 样式字典
        """
        return {
            "height": height,
            "color": Colors.TEXT_SECONDARY,
        }
