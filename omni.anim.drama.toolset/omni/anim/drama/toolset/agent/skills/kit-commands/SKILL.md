---
id: kit-commands
title: Omniverse Kit Commands & Undo
triggers: [kit, command, undo, redo, execute, omni.kit.commands, lop, prim command]
related_files: [common-commands.md, undo-stack.md]
---

`omni.kit.commands` is the official "undo-safe" entry point for modifying
Omniverse state. Read me when:

- No high-level domain tool covers the user's need (no `modify_light` for it,
  no `set_xform_keyframes` for it).
- The user says "undo" / "redo" or asks "is this undoable?".
- You're about to use `execute_kit_command` (the fallback meta-tool).

Why this matters:

- Every command that goes through `omni.kit.commands.execute(...)` is pushed
  onto the undo stack. Direct USD writes (raw `attr.Set(...)`) typically are
  NOT undoable from the user's perspective.
- This is why our high-level lighting tools internally route through the
  relight layer + commands, and why `execute_kit_command` is preferred over
  ad-hoc Python.

Workflow when falling back to Kit commands:

1. `list_kit_commands(query="...")` — discover candidates.
2. `get_kit_command_doc(command_name)` — read params + docstring.
3. Add the planned execute call to your `submit_plan` `tools_to_use`.
4. Call `execute_kit_command(command_name, kwargs={...})`. This requires
   user approval.
5. VERIFY with `inspect_prim` / `get_stage_metadata` / `get_time_samples`
   before reporting success.

Safety: a default denylist blocks commands containing `saveas`, `removelayer`,
`deletefile`, `shutdown`, `createnewstage`, etc. If you genuinely need one,
ask the user — do NOT try to bypass.

See `common-commands.md` for a small catalog and `undo-stack.md` for how
undo grouping works.
