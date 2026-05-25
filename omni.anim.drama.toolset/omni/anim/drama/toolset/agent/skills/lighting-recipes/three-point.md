# Three-point Lighting

## The three lights

| Role  | Direction (relative to subject)            | Typical intensity ratio | Quality            |
| ----- | ------------------------------------------ | ----------------------- | ------------------ |
| Key   | Front + slightly above + side ~30-45 deg   | 1.0 (the brightest)     | Hard or soft       |
| Fill  | Opposite side of key, lower height         | 0.3 - 0.5 of key        | Soft, broader      |
| Rim   | Behind subject, opposite of key, high      | 0.7 - 1.5 of key        | Hard, narrow       |

A "soft" key in modern Omniverse is usually a `RectLight` (large `width` /
`height`). A "hard" rim is often a `DistantLight` or a small `SphereLight`.

## Authoring checklist

1. Find the subject prim (`search_prim_paths`, `inspect_prim` to get its
   world-space bounding box center if you have a tool, otherwise just its
   xform translate).
2. Compute three target positions around the subject in stage units (mind
   `meters_per_unit`). Distances 2-5 meters from a face-sized subject is a
   good starting point.
3. For a "natural daylight" feel, key 5500K, fill 6500K (cool fill), rim
   matches key.
4. For a "warm interior" feel, key 3200K, fill 4500K, rim 3000K.
5. Always create lights into the relight layer (the toolset already does
   this). After `create_light` calls, verify with `list_lights` that the
   new lights exist with the expected attributes.

## Pitfall: relative ratios vs absolute intensities

The "1.0 / 0.3 / 0.7" table above is RATIO. In USD the absolute intensity
depends on units (`meters_per_unit`) and exposure. A safer pattern:

- Pick an exposure first (e.g. exposure = 0.0).
- Set key intensity to a sane base (e.g. 1500 for cm-units stage).
- Derive fill = 0.4 * 1500 = 600 and rim = 1.0 * 1500.
- After the change, ask the user if it's too bright/dim and tune by
  adjusting EXPOSURE on all three by the same delta (preserves ratio).
