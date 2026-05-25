# Schemas — typed APIs on prims

USD schemas come in two flavors:

1. **Typed schemas** — the prim's main type. Examples: `Mesh`, `Xform`,
   `RectLight`, `Camera`, `Skeleton`. Reported by `prim.GetTypeName()`.
2. **Applied API schemas** — extra typed APIs glued onto a prim. Examples:
   `MaterialBindingAPI`, `SkelBindingAPI`, `CollectionAPI`, `LightAPI`,
   `ShadowAPI`. Reported by `prim.GetAppliedSchemas()`.

## When to look at applied schemas

- Light linking is a **CollectionAPI** instance applied to the light prim
  (`collection:lightLink:includes/excludes`).
- Skeletal binding is **UsdSkelBindingAPI** on the mesh, pointing to a
  `SkelRoot`.
- Material binding goes through **UsdShadeMaterialBindingAPI**.

## How to author

The high-level tools (`create_light`, `modify_light`, light-link tools) handle
schema application for you. If you have to fall back to `execute_kit_command`,
use `ApplyAPISchema` from `Usd.SchemaBase` semantics — but in Kit you usually
just call `prim.ApplyAPI(<APIClass>)`.

## Common gotcha

`HasAPI(LightAPI)` on a `RectLight` returns True only after the light prim has
been fully resolved on a stage; raw schema introspection on a prototype may
return False. Always check on the live stage prim, not a copy.
