# Architecture

## Layering

```
+--------------------------------------------------------------+
|  UI (views/copilot_panel.py + viewmodels/copilot_vm.py)      |
|    - chat panel, settings, approval cards                    |
|    - bridges Kit main thread <-> Agent worker thread         |
+----------------------------+---------------------------------+
                             |
                             v
+--------------------------------------------------------------+
|  Agent layer (omni/anim/drama/toolset/agent/)                |
|                                                              |
|  agents/single_agent.py                                      |
|     - SingleAgent: system prompt + AgentNode loop            |
|                                                              |
|  network_node.py                                             |
|     - AgentNode (tool-calling loop)                          |
|     - AgentPhase enum (plan/gather/act/verify/summary)       |
|     - approval flow + verify hint injection                  |
|                                                              |
|  tool_registry.py                                            |
|     - @tool decorator, ToolDef, ToolPermission               |
|     - verify_with, phase_hint metadata                       |
|                                                              |
|  session.py / messages.py                                    |
|     - conversation state, token accounting                   |
|                                                              |
|  backend/                                                    |
|     - LLMBackend abstract + OpenAI-compat + Gemini impls     |
|                                                              |
|  tools/                                                      |
|    L2 domain (encode best practice + safety):                |
|     - scene_tools.py                                         |
|     - lighting_tools.py                                      |
|    L1 meta (discovery + freeform fallback):                  |
|     - planning_tools.py        (submit_plan)                 |
|     - usd_introspection.py     (inspect_prim, ...)           |
|     - kit_introspection.py     (list/exec Kit commands)      |
|     - skill_tools.py           (list/search/read skills)     |
|    External (opt-in, see mcp/):                              |
|     - register_external_mcp(url) / unregister_external_mcp() |
|                                                              |
|  mcp/                     (external MCP client + bridge)     |
|     - transport.py             (HTTP JSON-RPC, stdlib only)  |
|     - client.py                (MCPClient: connect/list/call)|
|     - bridge.py                (MCP tool -> local ToolDef)   |
|                                                              |
|  skills/                  (markdown knowledge base)          |
|     - usd-fundamentals/                                      |
|     - usd-layers/                                            |
|     - xform-ops-and-units/                                   |
|     - animation-time-samples/                                |
|     - camera-moves/                                          |
|     - lighting-recipes/                                      |
|     - kit-commands/                                          |
|     - agent-workflow/                                        |
+----------------------------+---------------------------------+
                             |
                             v
+--------------------------------------------------------------+
|  Core layer (omni/anim/drama/toolset/core/)                  |
|     - light_control, light_link, scene_exporter, ...         |
|     - These are pure Python around USD / omni.kit.commands   |
|     - Tools wrap these into LLM-callable functions           |
+--------------------------------------------------------------+
                             |
                             v
+--------------------------------------------------------------+
|  Omniverse Kit + OpenUSD                                     |
+--------------------------------------------------------------+
```

## Why two tool layers (L1 + L2)

L2 high-level tools (`create_light`, `modify_light`) encode:
- Safety constraints (intensity floors).
- Routing to the relight layer for safe undo.
- Curated parameters tuned for the domain.

L1 meta tools (`inspect_prim`, `list_kit_commands`, `execute_kit_command`,
`read_skill`) let the agent:
- Self-discover unfamiliar prims, schemas, attributes.
- Fall back to undo-safe Kit commands when no L2 tool exists.
- Pull domain knowledge on demand without bloating the system prompt.

A pure-L2 agent fails the moment a request crosses unfamiliar territory.
A pure-L1 agent fails on quality / safety because the LLM has to re-derive
best practices each turn. Both layers together is the sweet spot.

## Threading model

- Agent runs on a worker thread launched from `viewmodels/copilot_vm.py`.
- LLM calls and tool functions execute on that worker.
- For tool functions that must touch USD, we rely on Kit's USD APIs being
  thread-safe for read; writes go through `omni.kit.commands` which serialize
  internally. (See `kit-commands` skill for details.)
- UI updates flow back via an event queue drained on the main loop.

## Files added in the v0.3 agent upgrade

```
agent/tools/planning_tools.py
agent/tools/usd_introspection.py
agent/tools/kit_introspection.py
agent/tools/skill_tools.py
agent/skills/README.md
agent/skills/usd-fundamentals/{SKILL,stage-and-prim,schemas}.md
agent/skills/usd-layers/{SKILL,layer-stack,mute-vs-remove}.md
agent/skills/xform-ops-and-units/{SKILL,xformop-order,units-and-axis}.md
agent/skills/animation-time-samples/{SKILL,time-samples-vs-default,retiming}.md
agent/skills/camera-moves/{SKILL,shot-vocabulary,dolly-and-orbit}.md
agent/skills/lighting-recipes/{SKILL,three-point,mood-presets}.md
agent/skills/kit-commands/{SKILL,common-commands,undo-stack}.md
agent/skills/agent-workflow/{SKILL,phases,verification,ambiguity}.md
docs/agent/                       <- this directory
```

Modified:

```
agent/tool_registry.py            <- added verify_with + phase_hint fields
agent/network_node.py             <- AgentPhase enum + verify hint injection
agent/agents/single_agent.py      <- new system prompt with phase contract
agent/tools/lighting_tools.py     <- verify_with on each MUTATE/DESTRUCTIVE
agent/tools/__init__.py           <- register the new tool modules
```
