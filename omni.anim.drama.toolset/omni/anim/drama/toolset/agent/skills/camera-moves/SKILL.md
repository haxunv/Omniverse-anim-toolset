---
id: camera-moves
title: Cinematic Camera Move Recipes
triggers: [camera, dolly, truck, pan, tilt, crane, orbit, zoom, focal length, shot, framing]
related_files: [shot-vocabulary.md, dolly-and-orbit.md]
---

How to translate human shot language into concrete xformOp / focal-length
animations on a USD Camera prim. Read me whenever the user asks to "make a
shot", "do a dolly", "orbit around X", "pull focus", "zoom in".

Vocabulary the user might use (mapped to operations):

- DOLLY: camera body moves along its own forward axis. Animate
  `xformOp:translate` along the camera's local -Z (looking down -Z).
- TRUCK: camera body moves sideways (local X).
- PEDESTAL / BOOM: camera body moves vertically (local Y in Y-up worlds).
- PAN: camera rotates left/right around its own up axis (local Y).
- TILT: camera rotates up/down around its own right axis (local X).
- ZOOM: change `focalLength` over time, body stationary.
- ORBIT (arc): camera revolves around a target point keeping aim on target.

Concrete checklist before authoring any camera move:

1. Read `get_stage_metadata` -> up_axis, fps, start/end time code.
2. Read `inspect_prim` on the camera -> existing xformOps, current
   focalLength, current horizontalAperture.
3. If the user named a target ("orbit around the chair"), find the target
   path with `search_prim_paths` and `inspect_prim` to get its world position.
4. Compute keyframes in TIME CODES (not frames unless tcps == fps).
5. Author samples on `xformOp:translate`, `xformOp:rotateXYZ` (or quaternion
   `orient`), and/or `focalLength`.
6. VERIFY by reading back via `get_time_samples` for at least the first and
   last keyframe.

For the math of orbiting and dolly + zoom (Vertigo), see `dolly-and-orbit.md`.
