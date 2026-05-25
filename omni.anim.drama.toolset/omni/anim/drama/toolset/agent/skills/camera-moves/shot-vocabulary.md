# Shot vocabulary -> USD operations

| User says            | Operation                             | USD attributes touched                         |
| -------------------- | ------------------------------------- | ---------------------------------------------- |
| "Push in / dolly in" | Translate along local -Z              | `xformOp:translate`                            |
| "Pull out / dolly out" | Translate along local +Z            | `xformOp:translate`                            |
| "Truck left/right"   | Translate along local ±X              | `xformOp:translate`                            |
| "Boom up/down"       | Translate along local ±Y              | `xformOp:translate`                            |
| "Pan left/right"     | Rotate around local Y                 | `xformOp:rotateXYZ` (or `:orient`)             |
| "Tilt up/down"       | Rotate around local X                 | `xformOp:rotateXYZ`                            |
| "Roll"               | Rotate around local Z                 | `xformOp:rotateXYZ`                            |
| "Zoom in"            | Increase focalLength                  | `focalLength`                                  |
| "Zoom out"           | Decrease focalLength                  | `focalLength`                                  |
| "Rack focus"         | Animate focusDistance                 | `focusDistance`                                |
| "Vertigo / dolly zoom" | Dolly + zoom in opposite directions | `xformOp:translate` + `focalLength`            |
| "Orbit X for 4s"     | Camera revolves on a circle around X  | `xformOp:translate` + recomputed rotation      |

## Local vs world translation

USD xformOp translation is in PARENT space, not always world. If the camera
sits under `/World/Cameras/CamRig/MainCam`, your translate values are in the
CamRig's local frame. For free dolly / truck, parent the camera under an
identity Xform if possible, or compute world->local manually.

## Default camera orientation

Pinhole cameras in USD look down -Z by default with +Y up (in Y-up worlds).
Don't pre-rotate them unless the asset author rotated them away.
