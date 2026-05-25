# MCP Integration — 接入外部 MCP server

本扩展可以把任何符合 [Model Context Protocol](https://modelcontextprotocol.io/)
规范的 server 暴露的工具，**桥接到本扩展的 ToolRegistry**，让我们的 agent 同
时拥有：

1. 我们自己写的 anime / scene / lighting / introspection / skill 工具，**和**
2. 外部 MCP server 提供的工具（NVIDIA Kit MCP / USD Code MCP / OmniUI MCP /
   你自己写的 server / 第三方……）。

agent 不区分二者，由 LLM 根据问题自主选用。

---

## 一、当前默认接入：NVIDIA Kit MCP Server

NVIDIA 在 2025 年 8 月开源了
[`kit-usd-agents`](https://github.com/NVIDIA-Omniverse/kit-usd-agents) 仓库，
其中 Kit MCP Server 暴露了 12 个工具，覆盖 400+ Kit 扩展的语义搜索 / 代码示例 /
依赖图 / 设置项 / 应用模板等。

接入后 agent 会多出（前缀 `kit_mcp__`）：

| 工具 | 用途 |
|---|---|
| `kit_mcp__search_kit_extensions` | 跨 400+ 扩展做语义搜索 |
| `kit_mcp__get_kit_extension_details` | 单个扩展的元信息 |
| `kit_mcp__get_kit_extension_dependencies` | 依赖图 |
| `kit_mcp__get_kit_extension_apis` | 列扩展 API |
| `kit_mcp__get_kit_api_details` | 单个 API 详情 |
| `kit_mcp__search_kit_code_examples` | 代码示例语义搜索 |
| `kit_mcp__search_kit_test_examples` | 测试示例（学最佳实践用）|
| `kit_mcp__search_kit_settings` | Kit 设置项搜索 |
| `kit_mcp__search_kit_app_templates` | Kit 应用模板 |
| `kit_mcp__get_kit_app_template_details` | 单个模板详情 |
| `kit_mcp__search_kit_knowledge` | 通用 Kit 文档搜索 |
| `kit_mcp__get_kit_instructions` | Kit 系统总则 / 最佳实践 |

---

## 二、启用步骤

### 1. 在你机器上跑 Kit MCP Server（一次性）

```bash
git clone https://github.com/NVIDIA-Omniverse/kit-usd-agents
cd kit-usd-agents/source/mcp/kit_mcp

# Linux / macOS
./setup-dev.sh && ./run.sh
# Windows
setup-dev.bat
run.bat
```

需要 Python 3.11+、Poetry、以及一把 NVIDIA API Key（去
[build.nvidia.com](https://build.nvidia.com) 申请）。Server 默认监听
`http://localhost:9902/mcp`。

### 2. 在本扩展里打开开关

打开 `config/extension.toml`，把 `enable` 改成 `true`：

```toml
exts."omni.anim.drama.toolset".agent.mcp.kit.enable = true
exts."omni.anim.drama.toolset".agent.mcp.kit.url    = "http://localhost:9902/mcp"
exts."omni.anim.drama.toolset".agent.mcp.kit.prefix = "kit_mcp__"
exts."omni.anim.drama.toolset".agent.mcp.kit.timeout = 30.0
```

或在 omniverse 启动时通过命令行 / 自定义 app `.kit` 文件覆写同一组 setting。

### 3. 重启 Kit / 启用扩展

启动日志里会看到：

```
[omni.anim.drama.toolset] Kit MCP enabled, connecting to http://localhost:9902/mcp ...
[MCP] connected to http://localhost:9902/mcp (...)
[MCP] listed 12 tool(s) from http://localhost:9902/mcp
[MCP] registered 12 MCP tool(s) from kit-mcp with prefix 'kit_mcp__'
[omni.anim.drama.toolset] Kit MCP connected: ..., +12 tool(s).
```

### 4. 失败模式（不会让 agent 崩）

| 现象 | 日志 | agent 行为 |
|---|---|---|
| MCP server 没启动 | `Kit MCP NOT connected (...): Cannot reach MCP server` | 继续按本地工具运行 |
| URL 配错 | `Cannot reach MCP server` | 继续运行 |
| 连上但 NVIDIA API Key 缺失 | server 端报错 / 工具调用 isError=True | 单次调用失败，agent 看到 error 后会换工具 |
| 协议版本不匹配 | `MCP error: code=...` | 注册失败，继续运行 |

设计上 MCP 桥接是**纯增量**：失败时 agent 退化为"只用本地工具"。

---

## 三、运行机制

```
启动阶段
   extension.py
     → register_all()                  # 注册我们自己的工具
     → _maybe_register_kit_mcp()       # 看 carb settings
         → register_external_mcp(url)
             → MCPClient.connect()     # initialize 握手
             → MCPClient.list_tools()
             → 每个 MCP 工具生成一个 ToolDef，fn = 代理函数
             → ToolRegistry.register(...)

运行阶段
   AgentNode.run()
     → backend.chat(messages, tools=ALL_TOOLS)   # 包含 kit_mcp__* 12 个
     → LLM 决定调用 kit_mcp__search_kit_extensions
     → AgentNode._execute_single_tool_call(call)
         → ToolRegistry.get("kit_mcp__search_kit_extensions")
         → 代理 fn(**args)
             → MCPClient.call_tool("search_kit_extensions", args)
                 → HTTP POST /mcp  {"method":"tools/call", ...}
                 → 拿到 {"content":[{"type":"text","text":"..."}]}
             → 拼成 {"ok": true, "tool": "search_kit_extensions", "text": "..."}
     → 写入 ToolMessage，下一轮 LLM 看到结果继续推理
```

权限上：MCP 工具默认按 `READ_ONLY` 注册（Kit MCP 三台官方都是查询类，纯只读）。
所以它们走 `auto_run_read_only` 自动执行通道，不弹审批卡。如果你接入的 server
里有写操作类工具，应当显式传 `permission=ToolPermission.MUTATE`。

---

## 四、接入第三方 MCP server

只要符合 MCP 规范，都能用同一套机制。例：

```python
from omni.anim.drama.toolset.agent.tools import register_external_mcp

register_external_mcp(
    url="http://localhost:9903/mcp",
    prefix="usdcode__",            # 不同 server 用不同前缀
    timeout=60.0,
    extra_headers={"Authorization": "Bearer xxx"},  # 若 server 要鉴权
)
```

可以同时桥接多个 server：

```python
register_external_mcp(url="http://localhost:9902/mcp", prefix="kit_mcp__")     # Kit
register_external_mcp(url="http://localhost:9903/mcp", prefix="usd_mcp__")     # USD Code
register_external_mcp(url="http://localhost:9904/mcp", prefix="omniui_mcp__")  # OmniUI
```

每个 server 独立连接、独立工具集、独立前缀。

---

## 五、模块结构

```
agent/mcp/
    __init__.py        # 公共入口：register_kit_mcp / unregister_kit_mcp / MCPClient
    transport.py       # HTTPJsonRpcTransport：MCP-over-HTTP 极简实现
    client.py          # MCPClient：同步 list_tools / call_tool 包装
    bridge.py          # 把 MCP 工具桥接成本地 ToolDef（核心逻辑）
```

约 600 行，零外部依赖（urllib + json）。

---

## 六、为什么不用 mcp 官方 SDK

- 官方 SDK 强依赖 `anyio` + 异步上下文管理；Omniverse Kit 的 Python 环境不一
  定能干净安装额外包。
- 我们只用到极小子集（initialize / tools/list / tools/call），手写 200 行就够。
- 对齐项目其它 backend（OpenAI / Gemini）的"纯 stdlib + 同步阻塞"风格，便于
  排错和审计。

如果未来需要 SSE 流式 / prompts / resources 等高级能力，再考虑接 SDK。

---

## 七、下一步可能的演进

- **UI 入口**：在 Copilot 设置面板加一个 "Kit MCP" 开关 + URL 输入框 + 连接状
  态指示，不用编辑 toml。
- **健康检查事件**：MCP server 中途宕机时通过 AgentEvent 推到 UI 显示降级状
  态。
- **MUTATE 类 server 的审批策略**：当桥接 server 暴露写操作工具时，复用现有
  的 ApprovalCallback 机制。
- **反向：把本扩展工具暴露成 MCP server**：让别人的 agent（Cursor / Claude）
  也能调你的 lighting / animation 工具。下一步实现。
