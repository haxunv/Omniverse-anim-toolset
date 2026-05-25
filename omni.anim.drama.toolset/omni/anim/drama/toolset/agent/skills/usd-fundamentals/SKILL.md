---
id: usd-fundamentals
title: OpenUSD Fundamentals
triggers: [usd, openusd, prim, schema, stage, pseudoroot, defaultprim, kind, model, applied schema]
related_files: [stage-and-prim.md, schemas.md]
---

OpenUSD basics every Omniverse animation task touches. Read me first whenever
you are about to query or modify the stage and you are not sure about prim
hierarchy, schemas, or terminology.

Covered concepts:

- Stage = ordered set of layers composed at runtime; one Stage object is the
  edit surface.
- Prim = node in the namespace tree. Has type (`Mesh`, `Xform`, `RectLight`,
  `Camera`, `Scope`, ...) and a path like `/World/Cameras/MainCam`.
- Pseudo-root `/` is special; do not author attributes on it.
- Default prim: stage-level metadata, often `/World`. Used by referencers.
- Property = attribute (typed value, possibly time-sampled) or relationship
  (typed link to other prim path(s)).
- Applied schemas: extra typed APIs attached to a prim (e.g. UsdGeomXformable,
  UsdSkelBindingAPI). `prim.GetAppliedSchemas()` lists them.
- Kind: model hierarchy hint (`group`, `assembly`, `component`, `subcomponent`).
  Important for selection / referencing semantics.

Common pitfalls:

- A prim may exist but be `not active` or `not loaded`; querying attributes will
  return defaults silently. Check `IsActive()` / `IsLoaded()` (we surface them
  in `inspect_prim`).
- Type checks: `prim.GetTypeName() == "RectLight"` is fast but does NOT cover
  inherited types. For "is it any light?" check applied schemas instead.
- `IsInstance()` returns True for prototype instances; their children are
  read-only on the instance side.

Where to go next:

- For layer composition / mute / sublayer ordering -> see `usd-layers` skill.
- For xformOps order and rotation gotchas -> see `xform-ops-and-units` skill.
- For animation / keyframes -> see `animation-time-samples` skill.
