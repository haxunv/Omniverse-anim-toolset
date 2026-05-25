# Layer stack — strength ordering

```
session layer        (strongest, transient by default)
root layer
  ├── sublayer 0     (next strongest)
  ├── sublayer 1
  ├── ...
  ├── reference[A] -> external layer stack (resolves recursively)
  └── payload[B]   -> external layer stack (loaded on demand)
schema fallback      (weakest)
```

Reads return the strongest authored opinion. Writes go to the **edit target**.

## Edit target rules

- Anim Drama Toolset routes lighting writes to a dedicated "relight" sublayer.
  After calling `create_light` / `modify_light`, the change is in that
  sublayer, NOT the root. To persist for downstream tools, the user has to
  flatten or save explicitly.
- For free-form Kit commands you might trigger via `execute_kit_command`, the
  edit target is whatever Kit currently has set. Avoid changing it; let the
  user decide.

## Inspection cheatsheet

- `get_stage_metadata` — returns root layer identifier + all sublayer ids +
  mute state.
- `inspect_prim` — `attributes[].authored` tells you whether a value came
  from a layer at all (vs a schema fallback).
