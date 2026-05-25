# Mute vs Remove — DON'T confuse them

| Action            | What happens                                         | Reversible? |
| ----------------- | ---------------------------------------------------- | ----------- |
| **Mute layer**    | Layer is ignored at composition; data still on disk  | Yes (unmute)|
| **Remove sublayer** | Reference removed from the stack; data not deleted | Yes (re-add)|
| **Erase / save-as without** | The actual edits in that layer are lost     | NO          |

Default the agent should reach for: **mute**, never **remove**, when the user
says "turn off" / "hide" / "compare with original". The Anim Drama Toolset's
`toggle_relight_layer(enabled=False)` is a mute, which is safe.

## When the user really wants to discard

Use `remove_relight_layer`. This drops the relight sublayer entry; the file
itself is still on disk and can be re-added.

## When the user says "save"

That is a separate concern. Layer mute does NOT auto-persist. Saving requires
explicit `Sdf.Layer.Save()` or `omni.usd.get_context().save_stage()`. The agent
should NOT save without explicit user confirmation, because saves usually go to
read-only pipeline locations.
