# Units and Up Axis

## Read these BEFORE doing math

- `up_axis` (from `get_stage_metadata`): "Y" or "Z".
- `meters_per_unit`: e.g. `0.01` (cm), `1.0` (m), `0.001` (mm).
- `time_codes_per_second` and `frames_per_second`: usually equal (24 / 25 / 30
  / 60). When they differ, `time` arguments are in time codes, not frames.

## Translation

A "1 meter" offset depends on `meters_per_unit`:

```
distance_in_world_units = meters_desired / meters_per_unit
```

Example: user wants the camera 5 meters back, stage is in cm
(`meters_per_unit = 0.01`). The xformOp value is `5 / 0.01 = 500` (cm).

## Up axis impact on common operations

| Action                 | Y-up axis values    | Z-up axis values    |
| ---------------------- | ------------------- | ------------------- |
| "raise object 1 m"     | (0, +Y, 0)          | (0, 0, +Z)          |
| Default camera looks   | -Z direction        | -Y direction        |
| Default DistantLight   | -Z (then rotated)   | -Z (then rotated)   |

Always consult up_axis before constructing translate/rotate vectors from a
human description ("up", "forward", "right").

## Camera focal length and FOV

`focalLength` and `horizontalAperture` (both on `Camera` schema) define FOV:

```
horizontal_fov_radians = 2 * atan(0.5 * horizontalAperture / focalLength)
```

Both values are in **stage units**, not millimeters, even though the names
sound photographic. Apertures in scene files often use the photographic
convention (e.g. 35.0 = 35mm full-frame width); confirm via `inspect_prim`
before reasoning about FOV.
