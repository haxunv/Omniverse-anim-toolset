# Time Samples vs Default Value

## How they coexist

```
attr.Set(value)           # default value, no time
attr.Set(value, time=10)  # time sample at t=10

When samples exist:
    attr.Get()            # value at stage current time code
    attr.Get(t)           # interpolated value at t
    attr.GetTimeSamples() # list of authored sample times
    attr.HasAuthoredValueOpinion()  # True if authored at all
```

When samples exist on an attribute, the default value is silently ignored.

## "Why is my keyframe not showing in the curve editor"

Common causes:

1. You wrote to the wrong layer (see `usd-layers` skill). The viewport may
   show a different stronger opinion.
2. You wrote to `xformOp:transform` (matrix) instead of the SRT-component
   ops; matrix ops don't show clean tangents.
3. You wrote a single sample. Curve editor sometimes hides "single sample
   constants". Author at least 2 samples to confirm.
4. The attribute type is `bool` / `token` / `string`; these animate but
   don't show in float-curve editors.

## Verify a keyframe was actually authored

After `set_xform_keyframes` or any animation tool:

```
get_time_samples(prim_path, "xformOp:translate")
```

Check `num_total_samples` and the `samples[]` list match what you intended.
Then announce success to the user. NEVER report success based only on the
mutate tool returning ok=True.

## Animating attributes that aren't transforms

- Light intensity over time:    attr name `intensity` on the light prim.
- Visibility blink:             `visibility` (token: "inherited" / "invisible").
- Material parameters:          attribute on the Shader prim.
- Camera focal length zoom:     `focalLength` on the Camera prim.

All of these accept time samples just like xformOps.
