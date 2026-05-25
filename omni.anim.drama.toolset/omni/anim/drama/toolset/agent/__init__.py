# -*- coding: utf-8 -*-
"""
Agent Module - Copilot Agent 层
================================

提供类 ChatUSD 的 Copilot Agent 能力：

- messages: HumanMessage / AIMessage / SystemMessage / ToolMessage
- session: 对话历史管理
- tool_registry: 工具注册器与权限模型
- network_node: Agent 基类
- backend/: LLM 后端（OpenAI 兼容 + Gemini）
- tools/: 业务工具（scene/lighting/render/asset/geometry）
- agents/: 具体 Agent 实现

请按需从子模块导入，例如：
``from omni.anim.drama.toolset.agent.messages import HumanMessage``

不要在此处聚合导入全部子模块，保持启动安全。
"""
