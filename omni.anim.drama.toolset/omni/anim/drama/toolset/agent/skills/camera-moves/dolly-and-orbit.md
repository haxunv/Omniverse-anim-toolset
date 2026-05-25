# Dolly + Orbit math

## Dolly along the camera's facing axis

Camera looks down -Z. To dolly N world units forward across `[t0, t1]`:

```
p0 = current xformOp:translate value
forward_local = (0, 0, -1) rotated by current xformOp:rotate*

samples:
    (t0, p0)
    (t1, p0 + N * forward_local)
```

If the camera is a child of a parent Xform, this still works as long as the
PARENT doesn't move during the shot. Otherwise convert through the parent's
inverse transform.

## Orbit around a target

Given target world point `T`, current camera position `C`, frames `[t0, t1]`,
orbit angle `θ` (radians) around stage up axis:

```
r       = C - T
samples:
    for i in [0, N]:
        a = lerp(0, θ, i / N)
        ri = rotate r around up_axis by a
        Ci = T + ri

        # Aim camera at T:
        forward = normalize(T - Ci)        # unit vector from cam to target
        up      = stage up axis
        right   = normalize(cross(forward, up))
        up_corr = cross(right, forward)

        rotation = matrix-from-basis(right, up_corr, -forward) -> Euler XYZ
```

In practice, rather than authoring matrix-from-basis directly, prefer
`UsdGeom.Xformable.AddOrientOp` with a quaternion sample. If you don't have
a high-level orbit tool, this can be built on top of `execute_kit_command`
+ explicit attribute writes; verify with `get_time_samples` afterward.

## Vertigo (dolly + counter-zoom)

Keep the framing of the subject constant by dollying in while zooming out
(or vice versa):

```
size_on_screen ∝ focalLength / distance_to_subject

To keep size_on_screen constant while changing distance from d0 -> d1:
    focalLength_new = focalLength_old * (d1 / d0)
```

Author both `xformOp:translate` and `focalLength` with the same sample
times. Always verify both attributes' time samples after authoring.
