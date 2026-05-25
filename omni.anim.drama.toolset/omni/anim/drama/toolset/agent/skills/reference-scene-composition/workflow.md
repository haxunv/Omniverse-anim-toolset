# Reference Scene Composition Workflow (Phase 2)

Goal: from a reference image (or text only) plus an asset library, produce a
first-pass USD scene with main subjects, environment, a matching camera and
key lighting. This is NOT a pixel-perfect solver; deliver a structurally
correct preview the user can iterate on.

## Pipeline at a glance

```
PLAN
  -> PERCEIVE (only if image given)
  -> GATHER  (search per subject, environment)
  -> LAYOUT  (rule-based xforms)
  -> ACT     (reference assets, camera, lights)
  -> VERIFY
  -> SUMMARY
```

Each step uses a specific tool; do not skip ahead.

## Step-by-step

### 1. PLAN

Always start with `submit_plan`. List the subjects you intend to populate, the
environment, the camera, and 1-2 dominant lights. Keep the plan concise.

### 2. PERCEIVE (image only)

If the user provided `image_path`, call:

```
describe_reference_image(image_path=<path>, focus="general", user_hint=<one line>)
```

Take the returned `scene_graph` and treat it as ground truth for downstream
calls. If the user provided only text, skip this step and assemble a manual
SceneGraph stub from the user prompt - same shape, fewer subjects.

### 3. GATHER (search and pick per subject)

For each `scene_graph.subjects[i]`:

```
search_usd_assets(
    query=subjects[i].search_queries[0],
    search_path=<override or empty>,
    top_k_per_query=5,
)
```

Then commit one candidate explicitly:

```
pick_best_asset(
    subject_label=subjects[i].label,
    candidates=results,
    chosen_index=<your pick>,
    reason=<one short sentence>,
)
```

Repeat for `scene_graph.environment` if present.

If `search_usd_assets` returns `ok=false` because USD Search is not configured,
stop and ask the user to either configure the API or supply asset URLs
manually; do NOT fabricate URLs.

### 4. LAYOUT (deterministic xforms)

Once you have one chosen asset per subject, ask the layout solver for
coordinates:

```
propose_layout(
    scene_graph=<the SceneGraph from step 2 or your stub>,
    prim_path_root="/World/Assets",
)
```

The result `placements[*]` has fields `prim_path`, `translate`, `rotation`,
`scale`. Match each placement to the subject pick by `subject_index`.

### 5. ACT (sequential, each approved)

Place every asset:

```
reference_usd_asset(
    asset_url=<chosen_url from pick_best_asset>,
    prim_path=placement.prim_path,
    translation=placement.translate,
    rotation=placement.rotation,
    scale=placement.scale,
)
```

Place the camera:

```
create_camera_for_view(
    camera_spec=scene_graph.camera,
    framing_target_path="/World/Assets",
    camera_path="/World/Cameras/AnimeAgent_Camera",
)
```

Add the key light. Prefer modifying an existing light when one already
matches the role. Only create a new light when the scene has none of that
type. Use `scene_graph.lighting.key.color_kelvin` for `temperature` and
map `direction` -> rotate so the light points at the subject group:

```
create_light(
    light_type="DistantLight" or "RectLight",
    name="AnimeAgent_Key",
    parent_path="/World/Lights",
    intensity=...,
    temperature=scene_graph.lighting.key.color_kelvin,
    rotate=...,  # derived from key.direction
)
```

When an HDRI hint is present, you may add a `DomeLight` with a low intensity
and the hinted texture if available; otherwise leave ambient lighting alone.

Use `execute_usd_python` ONLY when no high-level tool covers what you need
(e.g. grouping, special xform, framing helper). Remember its writes do NOT go
into the relight layer; revert via Ctrl+Z.

### 6. VERIFY

After every mutate, call the corresponding read-back. The minimum for the
whole pipeline:

- `inspect_prim` for each new prim under `/World/Assets/` and the new camera.
- `get_scene_bounds` to confirm the new geometry sits inside a reasonable
  region.
- `list_cameras` to confirm the camera shows up with the right focal length.
- `list_lights` to confirm key lighting was created or modified.

### 7. SUMMARY

Plain-text reply: split "what I changed" from "what I verified" from
"suggested manual tweaks". Mention:

- The number of assets placed and the camera path.
- Whether `execute_usd_python` was used (and that Ctrl+Z is the way to undo).
- Any subjects you could not match to an asset (search returned nothing or
  the user had to provide URLs).

## Hard rules (do not violate)

- Do NOT fabricate asset URLs. Search first or ask the user.
- Do NOT use `execute_usd_python` for file / network / process access.
- Do NOT skip `pick_best_asset` between `search_usd_assets` and
  `reference_usd_asset` when there is more than one candidate; the
  pick should appear in the tool-call log so the user can review it.
- Do NOT pass dummy default transforms to `reference_usd_asset`. If you have
  no idea where a subject goes, call `propose_layout` first.
- Keep the first pass simple: subjects, environment, one camera, one or two
  dominant lights. The user can iterate.

## Useful snippets (only when no high-level tool fits)

Create or adjust a camera manually (rare; prefer `create_camera_for_view`):

```python
from pxr import Gf, UsdGeom

camera = UsdGeom.Camera.Define(stage, "/World/Cameras/Manual_Camera")
camera.CreateFocalLengthAttr(35.0)
xform = UsdGeom.Xformable(camera.GetPrim())
xform.ClearXformOpOrder()
xform.AddTranslateOp().Set(Gf.Vec3d(0, 6, 4))
xform.AddRotateXYZOp().Set(Gf.Vec3f(-55, 0, 0))
```

Create a simple ground plane (UsdGeom.Plane preferred when available;
fall back to a quad mesh otherwise):

```python
from pxr import Gf, UsdGeom, Sdf

plane_path = "/World/Environment/Ground"
try:
    plane = UsdGeom.Plane.Define(stage, plane_path)
    plane.CreateAxisAttr(UsdGeom.Tokens.Z)
    plane.CreateLengthAttr(20.0)
    plane.CreateWidthAttr(20.0)
except Exception:
    # UsdGeom.Plane not available; build a flat quad mesh instead.
    mesh = UsdGeom.Mesh.Define(stage, plane_path)
    mesh.CreatePointsAttr([
        Gf.Vec3f(-10, 0, -10),
        Gf.Vec3f(+10, 0, -10),
        Gf.Vec3f(+10, 0, +10),
        Gf.Vec3f(-10, 0, +10),
    ])
    mesh.CreateFaceVertexCountsAttr([4])
    mesh.CreateFaceVertexIndicesAttr([0, 1, 2, 3])

UsdGeom.Xformable(stage.GetPrimAtPath(plane_path)).ClearXformOpOrder()
```

Note: do NOT use `UsdGeom.Cube` as a "ground plane"; a cube scaled flat
visually reads as a thin slab, not a ground.
