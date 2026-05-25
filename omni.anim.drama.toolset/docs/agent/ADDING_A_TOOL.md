# Adding a Tool / Skill — recipes

## Decision: where does this live?

Before writing, decide:

1. Is this a **domain operation** (lights, cameras, animation, render
   setup)?
   -> L2 domain tool in `agent/tools/<domain>_tools.py`. Keep it
      opinionated: encode safety constraints, route writes through the
      relight layer or `omni.kit.commands`.

2. Is this a **discovery / introspection** capability that doesn't fit a
   single domain?
   -> L1 meta tool. Add to `usd_introspection.py` if it queries USD
      stage state, or `kit_introspection.py` if it queries the Kit runtime.

3. Is this **knowledge** the agent should reference?
   -> Skill, not tool. See "Adding a skill" below.

4. Is this a **planning / reflection** primitive?
   -> Goes into `planning_tools.py` (current: `submit_plan`).

## Recipe: add an L2 domain tool

Example: `set_camera_focal_length(camera_path, focal_length)`.

1. Implement the underlying core function in `core/`. Use
   `omni.kit.commands.execute("ChangeProperty", ...)` so it lands on the
   undo stack.

2. Wrap it in `agent/tools/scene_tools.py` (or a new module) with `@tool`:

   ```python
   from ..tool_registry import tool, ToolPermission

   @tool(
       description="Set a camera's focalLength. Verify with get_camera_info.",
       permission=ToolPermission.MUTATE,
       category="camera",
       tags=["camera", "modify"],
       verify_with=["get_camera_info"],
       phase_hint="act",
   )
   def set_camera_focal_length(camera_path: str, focal_length: float) -> dict:
       """
       Args:
           camera_path: USD path of the Camera.
           focal_length: New focalLength in stage units.
       """
       ...
   ```

   - `description` must tell the LLM both *what it does* and *what to
     verify with*.
   - `verify_with` list must point at READ_ONLY tools that read back the
     same attribute(s).
   - `phase_hint="act"` for mutates, `"gather"` for queries, `"plan"` for
     planning, `"verify"` if it's purely a verifier.

3. If it's a new module, list it in `agent/tools/__init__.py`'s
   `register_all()`.

4. Lint: open `ReadLints` on the touched files. Fix any new errors you
   introduced.

5. Optional: add a skill or update an existing skill if the new tool
   exposes user-visible vocabulary the model needs to learn.

## Recipe: add an L1 meta tool

Same as above, but:
- Live in `usd_introspection.py` or `kit_introspection.py`.
- Almost always READ_ONLY.
- Truncate output (`limit` argument with sane default + hard cap) — meta
  tools are easy to call with too-broad scope.
- Robust against missing stage / invalid prim — return
  `{"error": "..."}` instead of raising.

## Recipe: add a skill

1. Pick a kebab-case `id` and create directory:
   `agent/skills/<id>/`.

2. Create `SKILL.md` with frontmatter:

   ```
   ---
   id: <id>
   title: Human Title
   triggers: [keyword1, keyword2, ...]
   ---

   Short summary: when to read me, what I cover, which related_file to
   read for details.
   ```

3. Optional: add deep-dive `.md` files in the same directory. They are
   auto-discovered as related_files.

4. Test: in the chat panel, ask the agent something covered by your
   skill. The agent should call `search_skills` and `read_skill` for
   your id.

5. No restart required: skill files are scanned at every tool call.

## Recipe: change the system prompt

Edit `DEFAULT_SYSTEM_PROMPT` in `agent/agents/single_agent.py`. Keep it
**short** (the current size is already on the heavy side). Push details
to skills instead.

When adding new top-level rules, follow the existing structure:

```
# Operating principles
# Knowledge & discovery
# Rules (hard constraints)
# Identifying ...
# Verification policy
# Output format
```

## Pitfalls to avoid

- **Don't make tools too granular.** A tool per attribute is a smell;
  prefer one tool that takes the attribute name.
- **Don't omit `description`.** The LLM picks tools by description; an
  empty description means the tool is invisible.
- **Don't return raw USD types.** Convert to JSON-friendly shapes before
  returning. See `_format_value` in `usd_introspection.py`.
- **Don't forget `verify_with` on MUTATEs.** This is the most common
  miss.
- **Don't author writes outside `omni.kit.commands`** unless you have a
  specific reason — you'll lose undo support.
