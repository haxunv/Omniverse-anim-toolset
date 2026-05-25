# Agent Phases — `plan -> gather -> act -> verify -> summary`

## Why a phase model

Without an explicit phase model, an LLM tool-use loop tends to:
- Skip planning (jumps straight to a mutate call on a half-understood request).
- Skip verification (assumes `success=True` means the world changed).
- Mix planning text with tool calls (hard to surface in the UI for approval).

We use a **soft** phase model: not enforced by code blocking, but encoded in
(a) the system prompt, (b) the `submit_plan` tool, (c) the `verify_with`
metadata on each MUTATE tool, and (d) the `phase_hint` field shown in the UI.

## Phase definitions

| Phase       | Goal                                | Allowed tools (typical)                                             |
| ----------- | ----------------------------------- | ------------------------------------------------------------------- |
| PLAN        | Make intent / steps / risks explicit| `submit_plan`                                                       |
| GATHER      | Ground claims in real data          | READ_ONLY tools (introspection, scene query, skill read, kit doc)   |
| ACT         | Apply changes                       | MUTATE / DESTRUCTIVE tools (each requires user approval)            |
| VERIFY      | Read back to confirm                | READ_ONLY tools listed in `verify_with` of the just-executed mutate |
| SUMMARY     | Reply to user                       | (no tools)                                                          |

For purely conversational or single-read queries ("what's in the scene?"),
PLAN can be skipped.

## Implementation

### 1. `submit_plan` tool (`agent/tools/planning_tools.py`)

A READ_ONLY meta-tool. It does not modify anything; it just structurizes the
agent's plan and echoes it back. Calling it is the agent's "self-commitment"
to the plan.

Schema:

```
submit_plan(
    intent: str,
    steps: List[str],
    tools_to_use: List[str],
    risks: List[str],
    needs_clarification: bool = False,
    clarification_question: str = "",
)
```

If `needs_clarification=True`, the system prompt says: stop, do not call
mutate tools, ask the user.

### 2. `AgentPhase` enum (`agent/network_node.py`)

```
class AgentPhase(str, enum.Enum):
    PLANNING, GATHERING, ACTING, VERIFYING, SUMMARIZING
```

Phases are inferred from `phase_hint` on the active `ToolDef` and surfaced
to the UI via the `PHASE_CHANGED` event (UI badge above each tool card).

### 3. `phase_hint` on each `ToolDef`

Tools optionally tag themselves with `phase_hint` in the `@tool(...)`
decorator. Currently:

- `submit_plan` -> `"plan"`
- All introspection / skill / scene-query tools -> `"gather"`
- All MUTATE / DESTRUCTIVE tools -> `"act"`
- Verifier tools (re-using GATHER tools) -> `"gather"` (re-purposed by the
  agent for VERIFY)

### 4. System prompt (in `agents/single_agent.py`)

The prompt contains an "Operating principles" block that tells the model
the five phases and when to skip PLAN. See `single_agent.py` for the
canonical text.

## What is NOT enforced

- We do not block the model from calling a MUTATE before PLAN (that would
  cause excessive retries on simple tasks where PLAN is unnecessary).
- We do not block the model from skipping VERIFY (we only nudge via
  `__verify_hint__`).
- We do not block the model from calling tools out of phase order (so it
  can re-gather mid-act if needed).

This is intentional. The phase model is documentation + UX, not a runtime
firewall. The only hard runtime gate is the **approval flow** for
MUTATE / DESTRUCTIVE tools (handled by `approval_callback` in the UI).

## How the UI uses phases

`copilot_vm.py` listens for events emitted from `network_node.py`:

- `TOOL_CALL_STARTED` carries the `phase_hint` -> show a colored badge
  ("PLAN" / "GATHER" / "ACT" / "VERIFY") on the tool card.
- `__verify_hint__` in a ToolMessage -> show a "verify pending" cue if the
  agent has not yet called the verifier in the next turn.

(The current UI may not yet render all of these badges; the data is
emitted, surfacing it in views is incremental work.)
