# Agent Layer — Changelog

Tracks changes scoped to the `agent/` package and `docs/agent/` only.
Extension-wide changes belong in `../CHANGELOG.md`.

## v0.4.0 — External MCP Integration (in progress)

Goal: let our agent transparently consume tools exposed by external Model
Context Protocol servers (NVIDIA Kit MCP first, USD Code MCP / OmniUI MCP /
third-party next). After this change the agent has access to **both** our
local anime/scene/lighting tools **and** the external MCP toolset without
changing the runtime loop or the LLM backend.

### Added

- `agent/mcp/` package (zero external Python deps; uses stdlib `urllib` +
  JSON-RPC for parity with our OpenAI-compat backend).
  - `transport.py` — `HTTPJsonRpcTransport`: MCP-over-HTTP minimal client
    handling `initialize`, `Mcp-Session-Id`, `tools/list`, `tools/call`,
    plus a tolerant SSE fallback parser.
  - `client.py` — `MCPClient`: synchronous `connect()` / `list_tools()` /
    `call_tool()` / `ping()` with caching of server info and tool list.
  - `bridge.py` — `register_kit_mcp(url, prefix="kit_mcp__", ...)`:
    converts each MCP tool into a local `ToolDef` (proxy fn forwards to
    server), with name-prefix isolation, JSON-Schema passthrough, and
    re-entrancy (re-registering with the same prefix unregisters first).
- `agent/tools/__init__.py`
  - `register_external_mcp(...)` / `unregister_external_mcp(...)` thin
    wrappers for `extension.py` to call.
- `extension.py`
  - `_maybe_register_kit_mcp()` reads carb settings on startup; on success
    logs server name/version and tool count; on failure logs a warning and
    continues with local tools only.
  - `on_shutdown` cleans up MCP registrations.
- `config/extension.toml`
  - New settings, **opt-in / default off**:
    ```
    exts."omni.anim.drama.toolset".agent.mcp.kit.enable  = false
    exts."omni.anim.drama.toolset".agent.mcp.kit.url     = "http://localhost:9902/mcp"
    exts."omni.anim.drama.toolset".agent.mcp.kit.prefix  = "kit_mcp__"
    exts."omni.anim.drama.toolset".agent.mcp.kit.timeout = 30.0
    ```
- `docs/agent/MCP_INTEGRATION.md` — setup steps, runtime mechanism,
  multi-server usage, third-party integration recipe, design notes.

### Changed

- `docs/agent/README.md` — new entry in the read-order list pointing to the
  MCP integration doc.

### Behavior

- When NVIDIA Kit MCP is enabled and reachable, the agent gains 12 new
  read-only tools prefixed `kit_mcp__*` covering 400+ Kit extensions, code
  examples, settings, app templates, and knowledge base.
- All MCP-bridged tools default to `ToolPermission.READ_ONLY`. Mutating MCP
  servers can be added by passing `permission=ToolPermission.MUTATE` to
  `register_external_mcp`.
- Missing server / wrong URL / failed handshake never raise into the agent
  loop; they only log and reduce the tool set.

### Migration notes

- Default behavior is unchanged because MCP is opt-in. Users who do not
  flip `agent.mcp.kit.enable = true` see no difference.
- Existing local tools and their semantics are untouched; the `verify_with`
  contract, approval flow, and skill system continue to work as before.

### Known follow-ups

- Surface MCP status in the Copilot settings panel (enable toggle, URL
  field, ping button, server info display).
- Health-check loop emitting `AgentEvent` when a previously-connected MCP
  server becomes unreachable mid-session.
- Add an outgoing-MCP-server module that exposes our local tools to
  external MCP clients (Cursor / Claude) — the inverse direction.

## v0.3.0 — Plan / Verify / Meta-tools / Skills

Goal: turn the agent from a thin function-caller into a domain-aware
worker that plans, gathers, acts, verifies, and can self-discover OV
capabilities it doesn't know about yet.

### Added

- `agent/tools/planning_tools.py`
  - `submit_plan(intent, steps, tools_to_use, risks, needs_clarification,
    clarification_question)` — structured plan capture.
- `agent/tools/usd_introspection.py`
  - `inspect_prim`, `list_prims_by_type`, `list_animated_prims`,
    `get_time_samples`, `get_stage_metadata`, `search_prim_paths`.
- `agent/tools/kit_introspection.py`
  - `list_kit_commands`, `get_kit_command_doc`, `execute_kit_command`.
  - Default denylist for clearly destructive commands (saveas, removelayer,
    deletefile, shutdown, createnewstage).
  - Kwargs validated against the command's actual signature before invoke.
- `agent/tools/skill_tools.py`
  - `list_skills`, `search_skills`, `read_skill`.
  - Markdown-based, frontmatter-aware, body truncated to 12 KB / call.
- `agent/skills/` — 7 starter skills (each with SKILL.md + deep-dive files):
  - `usd-fundamentals`
  - `usd-layers`
  - `xform-ops-and-units`
  - `animation-time-samples`
  - `camera-moves`
  - `lighting-recipes`
  - `kit-commands`
  - `agent-workflow`
- `docs/agent/` — this developer documentation set.

### Changed

- `agent/tool_registry.py`
  - `ToolDef` gained `verify_with: List[str]` and `phase_hint: str`.
  - `@tool(...)` decorator accepts the new fields.
- `agent/network_node.py`
  - New `AgentPhase` enum (PLANNING / GATHERING / ACTING / VERIFYING /
    SUMMARIZING).
  - New `PHASE_CHANGED` event type for the UI.
  - On MUTATE / DESTRUCTIVE tool success, runtime now injects a
    `__verify_hint__` (or `[VERIFY_HINT: ...]`) into the ToolMessage to
    nudge the agent to call its declared verifier.
  - `ToolMessage.metadata["verify_with"]` carries the original list for the
    UI to surface.
- `agent/agents/single_agent.py`
  - System prompt rewritten:
    - Explicit five-phase contract (Plan / Gather / Act / Verify / Summary).
    - Knowledge & discovery section pointing at skills + introspection +
      Kit commands.
    - Verification policy section: "success doesn't mean changed".
    - Ambiguity policy: use `needs_clarification=True` instead of guessing.
- `agent/tools/lighting_tools.py`
  - All MUTATE / DESTRUCTIVE tools now declare `verify_with` (e.g.
    `modify_light` -> `get_light_info`, `delete_light` -> `list_lights` +
    `inspect_prim`).
  - All gained `phase_hint="act"`.
- `agent/tools/__init__.py`
  - `register_all()` now imports the four new tool modules.

### Migration notes

- No DB / persistent format changes.
- UI is backward-compatible. New event `PHASE_CHANGED` is optional; the
  existing UI does not need to handle it.
- `verify_with` defaults to `[]` and `phase_hint` to `""`, so any custom
  out-of-tree tools keep working.

### Known follow-ups

- UI badges for `phase_hint` and "verify pending" indicators.
- An eval harness (`tests/agent_eval/`) covering the new behaviors.
- Promote frequently-fallen-back-on Kit commands into named L2 tools
  (e.g. `transform_prim`, `set_attribute_value` with safety wrapping).
- Switch `search_skills` to BM25 / embedding-backed when the corpus
  grows past ~50 files.
