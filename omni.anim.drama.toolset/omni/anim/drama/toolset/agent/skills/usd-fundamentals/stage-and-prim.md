# Stage and Prim — practical cheatsheet

Use these recipes from inside Kit (Python). The agent should NOT write Python
itself; it should call existing tools. This file is a reference for HOW the
underlying primitives work, so the agent picks the right tool.

## Get the stage / current selection

- `omni.usd.get_context().get_stage()` — current stage, may be None.
- `omni.usd.get_context().get_selection().get_selected_prim_paths()` — current
  selection in the viewport. The agent has `get_selection` tool for this.

## Prim lookup

- `stage.GetPrimAtPath("/World/Cameras/MainCam")` — returns invalid prim if
  missing; always check `prim.IsValid()`.
- `Usd.PrimRange(stage.GetPseudoRoot())` — depth-first traversal.

## Property access

- `prim.GetAttribute("intensity")` — returns invalid attr if absent.
- `attr.Get()` — value at default time.
- `attr.Get(time)` — value at a specific time (only useful if time-sampled).
- `attr.IsAuthored()` — was it explicitly written, or is it the schema fallback?
- `attr.GetNumTimeSamples()` — > 0 means animated.

## Kind / model hierarchy

- `Usd.ModelAPI(prim).GetKind()` — `assembly` / `group` / `component` /
  `subcomponent` / `""`.
- Selection by Kind is what makes "select asset" vs "select mesh" work in the
  viewport.

## Type checks done right

| You want                                | Use                                        |
| --------------------------------------- | ------------------------------------------ |
| Exact USD type                          | `prim.GetTypeName() == "RectLight"`        |
| Any light                               | `UsdLux.LightAPI(prim).GetIsLight()` or check applied schemas |
| Any xformable (movable)                 | `UsdGeom.Xformable(prim)` truthiness       |
| Skinned mesh                            | `prim.HasAPI(UsdSkel.BindingAPI)`          |

## Don't author on the pseudo-root

`stage.GetPseudoRoot()` is `/`. Never call `DefinePrim` on it directly with a
type, never set attributes on it. Instead, use a defaultPrim like `/World`.
