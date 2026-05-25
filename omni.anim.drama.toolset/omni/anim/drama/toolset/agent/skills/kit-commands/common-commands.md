# Common Kit Commands (cheat sheet)

Names and signatures vary between Kit versions. ALWAYS verify with
`get_kit_command_doc(name)` before invoking.

## Prim creation / deletion

- `CreatePrim` / `CreatePrimCommand` — create a prim of a given type at a
  path. Common kwargs: `prim_path`, `prim_type`, `select_new_prim`.
- `DeletePrims` — delete a list of paths. Destructive in spirit (the prim
  goes away from current edit target). Prefer over raw `RemovePrim`.

## Selection

- `SelectPrims` / `SelectPrimsCommand` — set viewport selection.
- `ClearPrimSelection` — deselect all.

## Transform

- `TransformPrim` / `TransformPrimCommand` — set a prim's full xform.
- `TransformMultiPrimsSRTCommand` — set translate/rotate/scale on many
  prims atomically.
- `MovePrim` / `MovePrimCommand` — move a prim to a new path (rename /
  reparent).

## Reference / Payload

- `CreateReference` / `CreatePayload` — add an external reference / payload
  arc on a prim.

## USD attributes (fallback)

- `ChangeProperty` / `ChangePropertyCommand` — set an attribute value
  through the undo system. Useful when no domain tool covers the
  attribute.

## Animation

- `SetAnimCurveKey` (if `omni.kit.anim` is loaded) — set a keyframe on an
  animatable attribute.

## Layer (be careful)

- `SetEditTarget` — change the current edit target layer. Don't fight the
  user's existing edit target.
- `MuteLayer` / `UnmuteLayer` — toggle layer mute. Safe.
- `RemoveSublayer` — remove a sublayer entry (denied by default).

## Recommended pattern

```
plan -> list_kit_commands(query="transform") -> pick TransformPrim
     -> get_kit_command_doc("TransformPrim") -> read params
     -> execute_kit_command("TransformPrim", kwargs={...}) -> approval
     -> inspect_prim(prim_path) -> verify new transform matches plan
     -> reply to user
```
