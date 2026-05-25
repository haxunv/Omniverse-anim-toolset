# Mood Presets

These are starting points, not absolutes. Apply, then ask the user to tune.

## Golden hour / sunset

- Key: DistantLight, intensity ~3.0, color temperature 2800-3500K (warm),
  rotation pitched ~10-20 deg above horizon.
- Fill: DomeLight (HDRI of dusk sky preferred), intensity 0.3-0.6, low
  color temp 4500-5500K to keep ambient warmish.
- Optional rim DistantLight 5500K from camera-back to sell separation.

## Blue hour / pre-dawn

- Key: low intensity DistantLight, 8000-10000K, near-horizon angle.
- Fill: DomeLight 7500-10000K, intensity 0.5-1.0.
- No warm sources unless practical lights in the scene.

## Moonlit night

- Key: DistantLight, intensity 1.0, color 6500-8000K (cool white-blue), high
  altitude angle.
- Fill: DomeLight at very low intensity (0.05-0.2), 8000K.
- Practical sources (lamps, screens) become the warm accents, kept dim.

## Neon city night

- DomeLight at low intensity, neutral.
- Two-three RectLights placed close to subject acting as wall/sign bounce:
    one cyan (8000K + slight blue tint), one magenta (use color RGB like
    [1.0, 0.2, 0.8], disable colorTemperature to honor explicit RGB),
    intensity tuned to ~0.3-0.6 of key.
- Rim DistantLight, low intensity, 7000K.

## Candle / firelight

- SphereLight at the candle position, color 1800-2200K, intensity small but
  exposure +1 to +2 to mimic local glow.
- DomeLight at very low intensity, 3000K, just to lift shadows.

## Pitfalls

- `colorTemperature` is ignored unless `enableColorTemperature == True`. If
  you set both `colorTemperature` and an explicit RGB `color`, the math
  multiplies them — usually NOT what you want. Decide one channel and stick
  to it.
- Absolute intensities depend on `meters_per_unit`. Numbers above assume
  cm-units (Omniverse default). Scale linearly if your stage uses meters.
