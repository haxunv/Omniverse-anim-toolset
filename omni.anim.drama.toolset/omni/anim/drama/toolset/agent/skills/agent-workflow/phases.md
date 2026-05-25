# Phases — example walkthroughs

## Trivial: pure read

User: "What's in the scene?"

```
GATHER  -> get_scene_summary
SUMMARY -> reply
```

No PLAN needed. No mutate, no verify.

## Single light tweak

User: "Make the key light a bit warmer."

```
PLAN    -> submit_plan(
              intent="warm the key light slightly",
              steps=["list lights", "identify the key light", "lower its color temperature by ~500K"],
              tools_to_use=["list_lights", "modify_light", "get_light_info"],
              risks=["user said 'key light' but no light is named 'key'; may need clarification"],
              needs_clarification=False,  # we will check during gather
            )
GATHER  -> list_lights -> find any light with a name like "*key*" OR ask user
ACT     -> modify_light(light_path=..., temperature=current-500)  [APPROVED]
VERIFY  -> get_light_info(light_path=...) -> confirm temperature changed
SUMMARY -> "Lowered /World/Lights/Key.colorTemperature from 5500 to 5000 K. Verified."
```

## Multi-step retime

User: "Slow the cube animation to 2x duration."

```
PLAN    -> submit_plan(
              intent="retime cube animation to 2x duration",
              steps=[
                "find the animated cube prim",
                "list its animated attributes",
                "for each attribute, multiply each sample's time by 2.0",
                "verify by reading time samples back"],
              tools_to_use=["search_prim_paths", "list_animated_prims", "get_time_samples", "execute_kit_command"],
              risks=["may collide with stage end_time_code", "samples may already be at non-integer times"]
            )
GATHER  -> search_prim_paths(query="cube") -> /World/Cube
        -> list_animated_prims(under_path="/World/Cube")
        -> get_time_samples(prim_path="/World/Cube", attribute_name="xformOp:translate")
ACT     -> execute_kit_command("ChangeProperty", kwargs={...})  per sample [APPROVED]
VERIFY  -> get_time_samples again -> first/last times match 2x intent
SUMMARY -> "Retimed /World/Cube.xformOp:translate (24 samples) to 2x duration.
            Old span [1.0, 24.0] -> new span [2.0, 48.0]. Verified.
            Note: stage end_time_code is still 24.0; consider extending if you want playback past frame 48."
```

## Ambiguous request

User: "Dim the blue light."

```
PLAN    -> submit_plan(
              intent="reduce intensity of the light the user perceives as blue",
              steps=["list lights", "find one with blue-ish color", "either dim it or ask user"],
              tools_to_use=["list_lights"],
              risks=["if no light has authored blue color, perceived blue may come from material or HDRI"],
              needs_clarification=False  # will set True after gather if ambiguous
            )
GATHER  -> list_lights -> all lights show default white
PLAN    -> resubmit_plan with needs_clarification=True,
            clarification_question="None of the lights in the scene have a blue color set; the blue tint may come from a material, the HDRI, or post-processing. Could you (a) name the light path, (b) select it in the viewport, or (c) confirm the source of the blue tint?"
SUMMARY -> reply with the question, no mutate
```
