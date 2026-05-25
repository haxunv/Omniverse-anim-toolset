---
id: reference-scene-composition
title: Reference Scene Composition
triggers: [reference image, reference scene, ref image, scene matching, asset library, usd search, layout, composition, camera, framing, matching look, recreate scene, build scene from image, compose scene]
related_files: [workflow.md]
---

Use this skill when the user wants the anime agent to build or rough-match a USD
scene from a reference image, concept frame, or text description, using an asset
library (USD Search compatible). Note this is an MVP workflow, NOT a pixel-perfect
visual solver.

The high-level pipeline is:

1. PLAN with `submit_plan`, listing the subjects you intend to populate.
2. PERCEIVE: if the user supplied a `image_path`, call `describe_reference_image`
   to get a structured SceneGraph (subjects, environment, camera, lighting). Skip
   this step when the user only gave text.
3. GATHER: for each subject and the environment, call `search_usd_assets` (text or
   image search). Then call `pick_best_asset` to commit one candidate per subject.
4. LAYOUT: call `propose_layout` to convert rough_position / rough_scale / facing
   into concrete (translate, rotate_y, scale). This is rule-based and READ_ONLY.
5. ACT (each step needs approval, in order):
   - `reference_usd_asset` for every chosen asset.
   - `create_camera_for_view` for the framing.
   - `create_light` / `modify_light` for the key + ambient lighting.
6. VERIFY with `inspect_prim`, `get_scene_bounds`, `list_cameras`, `list_lights`.
7. SUMMARY: separate "did" vs. "verified", suggest manual tweaks.

Hard rules (do not deviate):

- Do NOT fabricate asset URLs. Always search first or ask the user for an asset path.
- Do NOT use `execute_usd_python` for file / network / process access. Prefer the
  high-level tools above; only fall back to `execute_usd_python` when no suitable
  tool exists, and remember its writes do NOT go into the relight layer.
- Keep the first pass simple: main subject, environment, camera, one or two
  dominant lights. Do not over-commit assets.
- If USD Search is not configured, explain that the API key / endpoint is missing
  and offer to continue with user-provided asset paths.

For the full workflow, code snippets, and the SceneGraph JSON schema, read
`workflow.md`. For the source-of-truth requirements, read
`docs/REQUIREMENTS_reference_scene.md` at the extension root.
