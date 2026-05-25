# Verification — `verify_with` and `__verify_hint__`

## The contract

For every MUTATE / DESTRUCTIVE tool, declare which READ_ONLY tool(s) can
read back the value(s) you just changed. The runtime then automatically
nudges the agent to call one of them next.

```
@tool(
    description="Modify an existing light...",
    permission=ToolPermission.MUTATE,
    category="lighting",
    verify_with=["get_light_info"],   # <-- the contract
    phase_hint="act",
)
def modify_light(light_path: str, intensity: float = ...) -> Dict:
    ...
```

## Runtime behavior

In `agent/network_node.py`, after a MUTATE tool succeeds, if its `ToolDef`
has a non-empty `verify_with`, the runtime:

1. Calls `_build_verify_hint(tool_def, arguments)` which inspects common
   path-like arguments (`light_path` / `prim_path` / `path` / `camera_path`)
   to construct a string like:

   ```
   VERIFY_HINT: After this MUTATE succeeded, call one of [get_light_info]
   on path '/World/Lights/Rect_1' to read the value back and confirm the
   change actually took effect before reporting success to the user.
   ```

2. Appends the hint to the `ToolMessage` content. If the content is a JSON
   object, the hint is set as a `__verify_hint__` field. Otherwise it is
   appended in `[VERIFY_HINT: ...]` form.

3. Also stores the original `verify_with` list under
   `ToolMessage.metadata["verify_with"]` for the UI.

The next LLM turn sees the hint and (per system prompt) calls the
verifier.

## Why this works (and why it's not enforced harder)

- LLMs are good at responding to in-context cues. A hint inside the tool
  result is much more reliable than a paragraph in the system prompt.
- We do NOT block the loop on the agent skipping verification — that
  causes ugly retries on tasks where verification is impossible (e.g. the
  user asked to mute a layer; the verifier is "the next render frame",
  which we can't auto-call).
- We also surface `verify_with` to the UI; future iterations can show a
  "verify pending" badge and let the user click to force a verify call.

## Adding `verify_with` to a new tool

When designing a MUTATE tool, ask:

1. **What did I change?** Identify the prim path or the layer that was
   touched.
2. **What READ_ONLY tool can re-fetch that value?**
   - For a single attribute change on a known prim: an `inspect_prim` or
     a domain-specific getter (`get_light_info`, `get_camera_info`).
   - For batch / multi-prim changes: a list-style getter or
     `list_animated_prims` / `list_lights`.
   - For layer-level operations: `get_stage_metadata` (lists layers + mute
     state) or `get_relight_layer_info`.
3. **Add `verify_with=[...]`** in the `@tool` decorator.

If you cannot name a verifier, that's a smell — either:

- The mutate is non-observable (e.g. logging) and probably shouldn't be
  MUTATE at all, or
- You haven't surfaced a getter yet. Write the getter first.

## Verifier inputs

The current `_build_verify_hint` looks at `arguments` for known path keys
(`light_path` / `prim_path` / `path` / `camera_path`). If your mutate uses
a different key (e.g. `target_prim`), pass it in or rename to one of the
recognized keys for the hint to be specific.

## Future: structured verifier descriptors

The current `verify_with: List[str]` is the simplest possible contract.
A future iteration could allow:

```
verify_with=[
    {"tool": "get_light_info", "args_from": {"light_path": "light_path"}},
    {"tool": "list_lights", "args_from": {}},
]
```

so the runtime can synthesize the verifier call directly. Worth doing
once we have evidence the LLM frequently picks the wrong verifier.
