# Anime Agent — How to Run (End-to-End)

This is the runbook for taking the anime agent from "code on disk" to
"reference image to USD scene" in your local Omniverse Kit App. Pre-Phase 2
audience: someone with the repo built once and the Kit app launched once.

If you have never built `kit-app-template` before, do the [Kit prereqs](#0-kit-app-template-prereqs)
first.

## TL;DR

```
1) Wire extension into .kit (already done; source/apps/...kit is hard-linked
   to _build, so edits propagate without rebuild)
2) Configure API keys (USD Search + Vision LLM) via env vars or extension.toml
3) Launch:   .\repo.bat launch -n my_company.my_usd_composer
   (or directly: _build\windows-x86_64\release\my_company.my_usd_composer.kit.bat)
4) In Kit, open the "Anime Agent" tab, configure chat LLM in Settings
5) Tell the agent: "Build a scene from this image: D:\path\to\ref.png"
6) Approve each step. Use Ctrl+Z to undo if needed.
```

> Note on rebuilding: `repo build` is only required for first checkout, when
> a new remote extension dependency is added, or when the Kit SDK version
> changes. Editing Python code under
> `Omniverse-anim-toolset/omni.anim.drama.toolset/...` or the `.kit` file
> itself does NOT need a rebuild — the .kit in `_build/.../apps/` is a hard
> link to `source/apps/`, and the extension folder is on the runtime ext
> search path. Just relaunch Kit.

---

## 0) kit-app-template prereqs

Make sure the base Kit app already builds and launches:

```powershell
cd D:\ov\kit-app-template
.\repo.bat build
_build\windows-x86_64\release\my_company.my_usd_composer.kit.bat
```

If that opens the USD Composer window, you are good to go.

If not, fix that first by following the upstream `kit-app-template` README. The
anime agent depends on a working `my_company.my_usd_composer` build.

---

## 1) Wire the extension into the .kit application

This is already done in `source/apps/my_company.my_usd_composer.kit`. Two
changes were made:

- Added the dependency line:
  ```toml
  "omni.anim.drama.toolset" = {} # Anime agent (in-tree, see ../../Omniverse-anim-toolset)
  ```
- Added a search folder so Kit can find the extension on disk:
  ```toml
  [settings.app.exts.folders]
  '++' = [
      "${app}/../exts",
      "${app}/../extscache",
      "${app}/../../../../Omniverse-anim-toolset",
  ]
  ```

If you ever regenerate the .kit from a template, re-apply these two edits.

---

## 2) Configure API keys

The anime agent needs two services and one chat LLM:

| Service | What for | Required to demo |
|---|---|---|
| **Chat LLM** (Kimi/OpenAI/Gemini compatible) | Drives the agent loop | Yes |
| **Vision LLM** | `describe_reference_image` | Only if you give a reference image |
| **USD Search** | `search_usd_assets` | Only if you want auto asset discovery |

You can set them three ways. Use whichever is easiest.

### Option A: Environment variables (quickest)

Open a fresh PowerShell, set vars, then launch Kit from the same shell:

```powershell
# Chat LLM is configured inside the Kit panel (Settings dialog),
# not via env. So only vision + USD Search go here.

# Vision (Google Gemini multimodal recommended for first try)
$env:GEMINI_API_KEY = "ya29.your-key-here"

# OR for OpenAI-compatible vision (gpt-4o, etc.)
# $env:OPENAI_API_KEY = "sk-your-key-here"
# $env:ANIM_VISION_PROVIDER = "openai_compat"
# $env:ANIM_VISION_MODEL    = "gpt-4o"

# USD Search (NVIDIA's hosted endpoint or your own compatible service)
$env:NVIDIA_API_KEY  = "nvapi-your-key-here"
# Optional: scope to a single asset library
$env:USDSEARCH_SEARCH_PATH = "omniverse://your-host/Library/Demo"

# Now launch Kit from THIS PowerShell so env vars are visible to the process
cd D:\ov\kit-app-template
.\repo.bat launch -n my_company.my_usd_composer
```

### Option B: edit `config/extension.toml`

`Omniverse-anim-toolset/omni.anim.drama.toolset/config/extension.toml`
already has placeholder lines. Fill in the keys you want:

```toml
exts."omni.anim.drama.toolset".agent.usd_search.api_key = "nvapi-..."
exts."omni.anim.drama.toolset".agent.usd_search.search_path = "omniverse://..."

exts."omni.anim.drama.toolset".agent.vision.provider = "gemini"
exts."omni.anim.drama.toolset".agent.vision.api_key = "ya29..."
```

This survives Kit restarts and is per-extension.

### Option C: at runtime via carb settings

You can also set them after Kit is running via the Script Editor:

```python
import carb.settings
s = carb.settings.get_settings()
s.set("/exts/omni.anim.drama.toolset/agent/vision/api_key", "ya29...")
s.set("/exts/omni.anim.drama.toolset/agent/usd_search/api_key", "nvapi-...")
```

These do NOT persist across restarts.

### Configure the chat LLM (always required)

This one is **not** in the toml. After Kit launches:

1. Open the `Anime Agent` tab.
2. Click `Settings` (top-right of the Anime Agent panel).
3. Pick a provider preset: SiliconFlow / Kimi / OpenAI / Gemini / DeepSeek /
   Custom.
4. Paste the API key, optionally tweak model name + temperature.
5. Click `Test Connection`. If it returns `OK`, save and close.

The chat LLM does the agent reasoning loop (tool calls). The vision LLM is a
**separate** call and is configured via env or extension.toml above.

---

## 3) Launch

```powershell
cd D:\ov\kit-app-template
.\repo.bat launch -n my_company.my_usd_composer
```

(Or skip the wrapper:
`_build\windows-x86_64\release\my_company.my_usd_composer.kit.bat`.)

You only need `repo build` after pulling fresh, after editing repo deps, or
after a Kit SDK bump. For Python code edits or .kit edits, just relaunch.

In the Kit console, watch for this line:

```
[omni.anim.drama.toolset] Registered NN anime agent tools
```

`NN` should be **42** with the new vision/layout tools registered. If it's
much smaller, the registration failed; scroll up to find the traceback.

If the line never appears, the extension was not loaded:

- Confirm `omni.anim.drama.toolset` is in the `[dependencies]` of your .kit.
- Confirm Kit found the extension folder: open Kit's `Window > Extensions`
  and search for "anim drama". The state should be `enabled`.
- Check the Kit log for "Failed to register anime agent tools".

---

## 4) Quick smoke test (no reference image, no asset library)

This confirms the agent + chat LLM + sandboxed Python all work, without
requiring vision or USD Search to be configured.

In the Anime Agent tab:

```
List the lights in the scene.
```

Expected: agent calls `list_lights`, returns the structured result. If this
works, the agent loop and tool layer are both healthy.

Now try a tiny mutation:

```
Add a DistantLight named TestKey at /World/Lights with intensity 1500
and rotation [-30, 30, 0], then verify.
```

Expected:
- agent calls `submit_plan`
- requests approval for `create_light` (you click Approve)
- calls `get_light_info("/World/Lights/TestKey")` automatically
- summarises in plain English

Hit Ctrl+Z; the relight layer change reverts.

---

## 5) The full reference-image flow

Once the smoke test passes, do the real demo.

### 5.1 Pick a reference image

Anything PNG/JPG/WebP up to ~20 MB. Local path required (the agent does not
have file picker UI yet; you paste the path as a string).

Example: `D:\refs\cozy_living_room.png`

### 5.2 Open a fresh stage

In Kit: `File > New From Stage Template > Empty` (or any other empty stage).
This is so the agent has a clean canvas. Save it somewhere if you want to
preserve the work.

### 5.3 Tell the agent

In the Anime Agent tab, send something like:

```
Build a USD scene that matches this reference image:
D:\refs\cozy_living_room.png

Make it cozy and warm. Use our asset library.
```

Optionally append to scope the asset library for this run:

```
Use search_path = omniverse://my-host/Library/Furniture for this build.
```

### 5.4 Watch the pipeline

The agent should run, in order:

1. `submit_plan` — list of subjects, environment, camera, lights.
2. `describe_reference_image` — returns `scene_graph` with subjects, env,
   camera, lighting (auto-runs, READ_ONLY).
3. For each subject:
   - `search_usd_assets` (auto-runs, READ_ONLY)
   - `pick_best_asset` (auto-runs, READ_ONLY) — agent commits one.
4. `propose_layout` — returns translate/rotate/scale per subject (auto-runs).
5. `reference_usd_asset` per subject — **needs your approval**, one per asset.
6. `create_camera_for_view` — **needs approval**.
7. `create_light` (or `modify_light`) — **needs approval**.
8. Verification: `inspect_prim`, `list_cameras`, `list_lights`,
   `get_scene_bounds`. (auto-runs)
9. Plain-text summary.

Approve each mutate step from the card UI. Reject any that look wrong.

### 5.5 Switch viewport to the new camera

After `create_camera_for_view` succeeded:

- In Kit's viewport: top-left dropdown -> select
  `/World/Cameras/AnimeAgent_Camera`.

### 5.6 Iterate

If a subject is in the wrong spot, ask the agent:

```
Move the chair (/World/Assets/Wooden_chair) closer to the camera and
slightly to the right. Rotate it 30 degrees clockwise.
```

The agent should call `execute_usd_python` (under `omni.kit.undo.group`) or a
new `reference_usd_asset` invocation depending on what it decides. Either
way, every change is undoable with Ctrl+Z.

---

## 6) Common errors and how to read them

### "USD Search API key is not configured"

Returned by `search_usd_assets`. Set
`agent.usd_search.api_key` (extension.toml) or `NVIDIA_API_KEY` env, then
restart Kit.

### "Vision provider API key is not configured"

Returned by `describe_reference_image`. Same fix, but for
`agent.vision.api_key` / `GEMINI_API_KEY` etc.

### "Vision response was not valid JSON"

The vision LLM did not return parseable JSON. Look at the `raw_excerpt` field
in the tool result. Fix:
- Try `focus="general"` instead of `subjects_only`.
- Some providers ignore the JSON-mode hint; switch to `gemini-2.0-flash` or
  `gpt-4o` (both natively support JSON mode).

### "Import of 'os' is not allowed in execute_usd_python"

Working as intended. The sandbox blocks file/network/process modules. Ask the
agent to use a high-level tool instead, or rewrite the snippet without
forbidden imports.

### "Failed to create dry-run stage"

Stage was closed mid-call. Reopen any USD stage and retry.

### "No approval callback configured; rejected"

The Anime Agent panel was closed while the agent was still running. Reopen
the tab so approval cards can be served.

### Tools register count is 0 or much less than 42

Extension didn't load. Check:
- `[dependencies]` in .kit has the extension name.
- The folder `Omniverse-anim-toolset/omni.anim.drama.toolset/config/extension.toml`
  exists.
- The path `${app}/../../../../Omniverse-anim-toolset` resolves to the repo
  folder. After build, the .kit lives in
  `_build/windows-x86_64/release/apps/`, so 4 levels up is the repo root.

---

## 7) Where things live (cheat sheet)

| File | What |
|---|---|
| `source/apps/my_company.my_usd_composer.kit` | Kit app spec (deps + ext folders) |
| `Omniverse-anim-toolset/omni.anim.drama.toolset/config/extension.toml` | Extension settings (vision/usd_search/layout) |
| `.../agent/agents/single_agent.py` | System prompt & agent class |
| `.../agent/tools/vision_tools.py` | `describe_reference_image` |
| `.../agent/tools/asset_tools.py` | `search_usd_assets`, `reference_usd_asset` |
| `.../agent/tools/layout_tools.py` | `pick_best_asset`, `propose_layout`, `create_camera_for_view` |
| `.../agent/tools/usd_code_tools.py` | `execute_usd_python` (sandbox + undo) |
| `.../agent/skills/reference-scene-composition/workflow.md` | Pipeline doc the agent reads |
| `docs/REQUIREMENTS_reference_scene.md` | Full spec |
| `docs/CHANGELOG_M1_plan.md` | M1 fixes done |

---

## 8) What does NOT work yet (Phase 3 backlog)

- File picker UI for reference image — paste local path string for now.
- Multi-library asset search — single `search_path` per call only.
- Render-feedback loop — agent does not yet render and self-correct.
- Layout solver does not understand relative constraints ("chair next to
  table"). It uses 9-grid + greedy push.
- Agent does NOT see the image directly. Only `describe_reference_image`
  sees it; everything downstream operates on the structured JSON.

These are documented in `docs/REQUIREMENTS_reference_scene.md` Sections
2.3 and 14.
