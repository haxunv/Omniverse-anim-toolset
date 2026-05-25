# Meta Tools — L1 discovery & freeform fallback

The agent can NEVER carry the full Omniverse / OpenUSD API surface in its
context window. Instead, it uses two families of meta-tools to discover and
act on unknown territory:

1. USD prim introspection — explore the live stage.
2. Kit command introspection — discover and execute any registered Kit
   command (undo-safe).

Both are intentionally low-level and small in number; they're the agent's
"eyes" and "fallback hands". Domain-specific behavior should still go into
L2 tools where possible.

## USD prim introspection (`agent/tools/usd_introspection.py`)

| Tool                    | Permission   | Purpose                                                                 |
| ----------------------- | ------------ | ----------------------------------------------------------------------- |
| `inspect_prim`          | READ_ONLY    | Type, applied schemas, attributes (with authoring + animation flags), relationships, children preview. |
| `list_prims_by_type`    | READ_ONLY    | Find all prims of a USD type (Mesh / Camera / RectLight / ...).         |
| `list_animated_prims`   | READ_ONLY    | All prims with at least one time-sampled attribute.                     |
| `get_time_samples`      | READ_ONLY    | Full (time, value) list for a single attribute.                         |
| `get_stage_metadata`    | READ_ONLY    | upAxis, metersPerUnit, fps, time range, layer stack + mute state.       |
| `search_prim_paths`     | READ_ONLY    | Substring or wildcard prim path search.                                 |

Design notes:

- Outputs are deliberately truncated (50 prims / 200 samples per call) to
  avoid blowing the context window. Truncation is reported via a `truncated`
  flag and a `count` value so the agent can paginate or narrow its query.
- All tools are robust against `stage is None` and missing prims; they
  return a structured `{"error": ...}` rather than raising, so the agent
  can recover without burning a tool turn on an exception.
- Values are normalized to JSON-serializable types via `_format_value`
  (Gf vectors -> lists of floats, etc.).

## Kit command introspection (`agent/tools/kit_introspection.py`)

| Tool                  | Permission   | Purpose                                                              |
| --------------------- | ------------ | -------------------------------------------------------------------- |
| `list_kit_commands`   | READ_ONLY    | Search registered commands by name substring or owning extension.    |
| `get_kit_command_doc` | READ_ONLY    | Fetch docstring + parameter signature (via `inspect`).               |
| `execute_kit_command` | MUTATE       | Run a Kit command by name with kwargs; goes through `omni.kit.commands.execute` (undo-safe). |

Safety:

- A default keyword **denylist** rejects commands containing `saveas`,
  `removelayer`, `deletefile`, `shutdown`, `createnewstage`, etc. These
  cannot be executed even with user approval. To enable one, edit
  `KIT_COMMAND_ALLOWLIST` explicitly.
- `execute_kit_command` validates kwargs against the command's actual
  `__init__` / `do` signature (via `inspect`). Unknown kwargs are rejected
  before invocation — defends against typos and silent misuse.
- It is registered with `permission=ToolPermission.MUTATE` so it always
  goes through the approval flow.

## When the agent should reach for these

Decision tree (encoded in the system prompt + `agent-workflow` skill):

```
Is there a high-level domain tool (modify_light, ...) that does this?
   Yes -> use it.
   No  -> Is the operation a query?
            Yes -> usd_introspection / scene query.
            No  -> kit_introspection: list -> doc -> execute_kit_command.
```

## Adding a new meta tool

When you find yourself thinking "the agent keeps falling back to
`execute_kit_command` for X", that's a signal to promote X into either:
- A new L2 domain tool (preferred), or
- A more specific L1 meta tool (next best).

Both go through the same `@tool` decorator. See `ADDING_A_TOOL.md`.
