# Verification — the contract

## Why

The host runtime returns `success=True` for a tool call when the tool
function did not raise. That tells you the call did not error. It does NOT
tell you that the value you intended is now present on the live stage.
Reasons the value might NOT be there even on success:

- A stronger layer overrides yours.
- The wrong attribute was targeted (typo in attribute name).
- The mutate took effect on a different prim (resolved through a wrong
  reference / variant).
- The undo stack collapsed your op with another.

So we treat "verify" as a hard requirement, not a nice-to-have.

## How: read the verify hint

When a MUTATE tool succeeds and declares `verify_with` in its ToolDef, the
runtime injects a hint into the ToolMessage:

```
{
  "success": true,
  "message": "ok",
  ...,
  "__verify_hint__": "VERIFY_HINT: After this MUTATE succeeded, call one of [get_light_info] on path '/World/Lights/Rect_1' to read the value back and confirm the change actually took effect before reporting success to the user."
}
```

When you see `__verify_hint__`, you SHOULD call the named verifier next.
This is part of the same agent turn — do not move on to the next mutate
or to the user-facing summary first.

## What counts as verified

After calling the verifier, compare the read-back value against your plan:

- For numeric edits, check within tolerance (1e-6 for color, 0.01 for
  intensity in cm-units, exact match for integer fields).
- For created prims, check the new path actually appears in
  `inspect_prim` output.
- For animation, check `num_total_samples` and `first/last_time` against
  intent.

If the read-back disagrees with your intent, surface it honestly in the
summary. Do not silently retry; tell the user what the actual state is.

## When verification fails

Three options, in order of preference:

1. Diagnose: re-inspect with broader scope (`get_stage_metadata` for
   layer / mute issues, `inspect_prim` to confirm attribute name).
2. If the failure is recoverable and trivial, propose a single corrective
   plan and execute (with a fresh PLAN -> ACT -> VERIFY).
3. If unclear, stop, summarize the discrepancy, and ask the user.
