# Ambiguity — when to ask, what to ask

## Trigger conditions

Set `needs_clarification=True` and ask the user when ANY of:

1. The user describes a target by visual property (color, brightness, "the
   bright one") and you cannot map it 1:1 to scene data.
2. Multiple plausible interpretations of the verb ("dim" by 50%? to a
   specific value? to mute?).
3. Destructive intent (delete, overwrite, save) is implied but not
   explicit.
4. Required parameter is missing and no sensible default exists (e.g.
   "make it slower" — slower by how much?).

## How to phrase

A good clarification question:

- Cites what you SAW (so the user trusts you actually checked).
- Offers 2–3 concrete options the user can answer with one sentence.
- Avoids open-ended "what would you like".

Bad:

> Which light do you mean?

Good:

> I see three RectLights in the scene: /World/Lights/Key (white, intensity
> 1500), /World/Lights/Fill (white, intensity 600), /World/Lights/Rim (white,
> intensity 1000). None has a blue color set. Did you mean (a) tint Key
> blue, (b) the perceived blue is from the HDRI / material, or (c) you want
> to add a new blue accent light?

## After the user answers

Re-enter PLAN with `needs_clarification=False`, an updated `intent` and
`steps`, and proceed normally.
