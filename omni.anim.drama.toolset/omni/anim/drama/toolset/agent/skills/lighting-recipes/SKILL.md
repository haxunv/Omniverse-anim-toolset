---
id: lighting-recipes
title: Lighting Mood & Three-Point Recipes
triggers: [light, lighting, mood, key, fill, rim, three-point, golden hour, sunset, night, moon, color temperature, exposure]
related_files: [three-point.md, mood-presets.md]
---

How to translate human mood / lighting language into concrete light prim
attributes. Read me whenever the user says things like "make it look like
sunset", "warm it up", "give me a moody key light", "add a rim".

Vocabulary mapping:

- COLOR TEMPERATURE in Kelvin: candle 1800K, tungsten 3200K, daylight 5500K,
  noon sun 6500K, overcast 7500K, blue hour 10000K. Most lights expose
  `colorTemperature` (used only when `enableColorTemperature` is true) as
  well as `color` (RGB).
- EXPOSURE is in EV stops (log2). +1 doubles intensity, -1 halves. Often
  cleaner to bias exposure than touch raw intensity.
- INTENSITY is the linear gain. Defaults vary per light type; safety
  minimums in this toolset: DomeLight >= 10, DistantLight >= 1, others >= 10.

Always-true rules:

1. Before modifying lights, list them with `list_lights` and identify the
   target. NEVER guess a light_path.
2. If the user describes the light by visual property ("the blue light")
   and no light's `attributes.color` matches, set
   `needs_clarification=True` in your plan; do not pick one at random.
3. Default-color light reports `color = [1.0, 1.0, 1.0]` (white). The
   `_color_authored` flag distinguishes "explicitly white" from "never
   set".
4. Modifications go into the relight layer; safe to undo via
   `remove_relight_layer` / `toggle_relight_layer`.

For specific recipes see:
- `three-point.md` — classical key/fill/rim, ratio guidance.
- `mood-presets.md` — golden hour, blue hour, neon night, candlelight, etc.
