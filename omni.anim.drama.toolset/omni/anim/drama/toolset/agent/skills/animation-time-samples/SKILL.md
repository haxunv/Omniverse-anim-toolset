---
id: animation-time-samples
title: USD Time Samples & Keyframe Animation
triggers: [animation, keyframe, time sample, timecode, fps, retime, interpolation, timeline, playhead]
related_files: [time-samples-vs-default.md, retiming.md]
---

USD animates by storing per-attribute time samples. Read me whenever the user
mentions keyframes, timeline, fps, retiming, baking, or "make this move".

Mental model:

- Each attribute can hold either:
    (a) a single default value (no animation), OR
    (b) a list of (time, value) pairs called time samples.
- "Time" is in TIME CODES, not always frames. Convert with
  `frames_per_second` from `get_stage_metadata`. With `fps == tcps == 24`,
  frame N corresponds to time code N.
- Interpolation is `linear` by default at the stage level
  (`interpolationType`); attributes of types like `string`, `token`, `bool`
  always use HELD interpolation regardless.

Critical pitfalls:

1. Reading `attr.Get()` on an animated attribute returns the value at the
   stage's current timeCode, NOT a samples list. Use
   `get_time_samples(prim, attr)` to see the actual curve.
2. Authoring a single sample at time `t` does NOT make a constant value;
   outside the sample range the value is held to the nearest sample. If you
   want a constant unanimated value, clear samples and set the default
   instead.
3. Mixing default + samples on the same attribute is legal but confusing —
   default is ignored once any sample exists.
4. For `xformOp:translate` etc., authoring time samples is the keyframing
   path. Do NOT bake into `xformOp:transform` if you want editable curves
   (see `xform-ops-and-units` skill).

For retime / scale-time / shift-time recipes see `retiming.md`.
