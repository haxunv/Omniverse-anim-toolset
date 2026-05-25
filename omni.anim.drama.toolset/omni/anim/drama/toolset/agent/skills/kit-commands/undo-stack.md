# Undo Stack — what's safe, what isn't

## Goes into the undo stack (good)

- Anything called via `omni.kit.commands.execute(name, ...)`.
- The high-level toolset operations that internally use commands
  (`create_light`, `modify_light`, light-link tools).
- `execute_kit_command` (the meta-tool).

## Does NOT go into the undo stack (be careful)

- Direct `attr.Set(...)` / `prim.GetAttribute(...).Set(...)` from raw Python.
- `Sdf.Layer.Save()` — saves are not undoable.
- File-system side effects.

## Grouping

Multiple commands executed back-to-back appear as separate undo entries by
default. To group several writes into one undoable unit, code can wrap them
in `Sdf.ChangeBlock` + `omni.kit.undo.group()`. The agent does NOT need to
do this manually — it's enough to know that calling N tools may produce N
undo entries from the user's perspective.

## What "undo" actually does to layers

Undo reverts the LATEST opinion in the edit target layer. If the agent
authored values into the relight sublayer, undoing while the edit target is
the root will not affect those relight values. Always tell the user which
layer the change went into when summarizing.
