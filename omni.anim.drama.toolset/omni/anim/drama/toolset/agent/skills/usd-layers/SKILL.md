---
id: usd-layers
title: USD Layers, Composition, Mute vs Remove
triggers: [layer, sublayer, composition, mute, override, opinion, lop, edit target, relight layer]
related_files: [layer-stack.md, mute-vs-remove.md]
---

USD changes are written into a LAYER, not directly into the stage. The stage
flattens an ordered list of layers (root + sublayers + session layer + payloads
+ references) into the runtime view you see. Read me whenever:

- The user asks "save my changes" / "discard my changes"
- You're about to author lighting, animation, or any modification
- You see a property that "won't change" no matter what you write to it
- The user mentions undo, A/B compare, mute, sublayer, override

Key concepts:

- Edit target: the layer the next write goes into. The Anim Drama Toolset's
  `relight` layer is the edit target while you call lighting tools, so
  modifications can be rolled back via `remove_relight_layer` or A/B'd via
  `toggle_relight_layer`.
- Strength order: layers earlier in the sublayer list win over later ones.
  Session layer wins over root sublayers.
- Opinion vs default: an attribute returns its strongest authored opinion,
  falling back to the schema default if none is authored. `IsAuthored()` tells
  you which.

Common pitfall: you "set" intensity to 1000, but the read-back returns 1500.
Reason: a stronger layer (root or session) has its own opinion overriding
yours. Inspect with `get_stage_metadata` (lists sublayers + mute state) and
verify by reading the property after the write.

See `mute-vs-remove.md` for the difference between hiding a layer and removing
it (very common bug source).
