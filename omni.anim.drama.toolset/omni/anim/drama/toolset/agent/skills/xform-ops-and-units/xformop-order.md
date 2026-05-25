# Safe xformOp authoring

## The cardinal rule

Before adding any new xformOp, read the existing `xformOpOrder`. If an op
with the same suffix already exists, REUSE it; do not add a new one.

```
existing xformOpOrder = ["xformOp:translate", "xformOp:rotateXYZ", "xformOp:scale"]

I want to set translate -> get attribute "xformOp:translate" and Set(...)
I want to set rotation  -> get attribute "xformOp:rotateXYZ" and Set(...)
I want to add a pivot   -> add a NEW op "xformOp:translate:pivot"; the suffix
                           after the colon disambiguates it
```

## The recommended order

Animation pipelines commonly follow:

```
[ translate, rotate, scale ]                # most common
[ translate, rotate, scale, translate:pivot ]
[ translate:pivot_inverse, scale, rotate, translate:pivot, translate ]  # pivoted SRT
```

Use `transform` (single 4x4) only for cached / baked transforms; it kills
clean keyframe editing.

## Animated transforms

Each xformOp can hold time samples directly. Authoring keyframed translation
on `xformOp:translate` is the right path; do NOT bake the matrix into
`xformOp:transform` if you want clean editable curves.

Reading: `get_time_samples(prim_path, "xformOp:translate")` gives you the
animation curve.

## Avoid the "multiple ops with same suffix" trap

If you call schema methods like `AddTranslateOp()` more than once without
suffix, USD emits `xformOp:translate` and `xformOp:translate:1`, both end up
in `xformOpOrder`, and the math compounds. Always use suffixes when you mean
"a different op" (pivot, offset, etc.).
