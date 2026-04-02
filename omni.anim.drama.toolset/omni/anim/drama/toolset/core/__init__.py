# -*- coding: utf-8 -*-
"""
Core Module - 核心业务逻辑层
============================

子模块请按需导入，例如：
``from omni.anim.drama.toolset.core.stage_utils import get_stage``

勿在本包 ``__init__`` 中聚合导入全部子模块：否则任意 ``from ...core.xxx`` 都会
先执行此处并拉取 render_setup、exr_merge、light_control 等，在文件缺失或
环境不兼容时会导致整个扩展无法启动（堆栈常误指向 load_manager_vm）。
"""
