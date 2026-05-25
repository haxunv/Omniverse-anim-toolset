# Retiming Recipes

When the user asks to "make the animation slower / faster / shifted":

## Time scale (slower / faster, same start)

For each animated attribute, multiply each sample's time by `factor`:

```
factor = new_duration / old_duration   # 0.5 = twice as fast, 2.0 = twice as slow
new_samples = [(t * factor, v) for (t, v) in old_samples]
```

Important: keep `factor > 0` and ensure rounded times don't collide. If the
stage `time_codes_per_second` is 24 and the user asks for "1.5x slower",
prefer to round to whole time codes (`round(t * 1.5)`) only if the user
mentioned frames; otherwise keep float times.

## Shift in time (move whole anim later by N frames)

```
new_samples = [(t + delta_in_timecodes, v) for (t, v) in old_samples]
```

Shifting may push samples beyond the stage's `endTimeCode`. After authoring,
either:
- Extend `endTimeCode` (stage metadata write), or
- Tell the user the playback range may need extending.

## Bake to a different fps

If the project changed from 24fps to 30fps and old samples were authored at
24fps integer frames, multiply by `30/24 = 1.25` and re-snap.

## After retime: ALWAYS verify

Use `get_time_samples` on at least one of the retimed attributes and check
`first_time` / `last_time` match expectations before reporting success.
