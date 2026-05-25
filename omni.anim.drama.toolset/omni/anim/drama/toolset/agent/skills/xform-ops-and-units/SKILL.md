---
id: xform-ops-and-units
title: xformOps Order, UpAxis, MetersPerUnit
triggers: [transform, xformop, translate, rotate, scale, pivot, up axis, units, world space, local space, gimbal]
related_files: [xformop-order.md, units-and-axis.md]
---

Transforms in USD are NOT a single matrix. Each xformable prim carries an
ordered list of `xformOp:*` attributes (translate, rotateXYZ, rotateZYX,
scale, transform, pivot, ...), with the order itself stored in
`xformOpOrder`. Read me whenever you:

- Are about to author or modify position / rotation / scale on a prim.
- See a prim that "looks rotated wrong" after a code change.
- Need to convert between world space and local space.
- Need to interpret units (cm vs m) or up axis (Y vs Z) for a numeric value.

Critical rules:

1. NEVER blindly add a new `xformOp:translate` if one already exists; you'll
   compound transforms or hit a `multiple ops with same suffix` error.
2. The order in `xformOpOrder` is the order ops are concatenated; rearranging
   it visibly changes the result.
3. UpAxis is per-stage. Y-up vs Z-up means a position `(0, 100, 0)` is "100
   units up" in Y-up but "100 units forward" in Z-up. Always read
   `get_stage_metadata.up_axis` first.
4. metersPerUnit affects scale of all linear quantities. Omniverse usually
   defaults to `0.01` (centimeters). A "1 meter cube" then means
   `xformOp:scale = (100, 100, 100)`. Don't assume meters.
5. Rotations: USD has `rotateXYZ` / `rotateZYX` / `orient` (quaternion). The
   suffix is the EULER ORDER. Picking the wrong order causes gimbal-style
   bugs that survive normalization.

See `xformop-order.md` for safe authoring patterns and
`units-and-axis.md` for unit conversion / camera setup.
