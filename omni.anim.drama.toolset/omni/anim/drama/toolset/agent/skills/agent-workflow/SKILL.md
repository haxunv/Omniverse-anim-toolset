---
id: agent-workflow
title: Agent Workflow — Plan / Gather / Act / Verify / Summary
triggers: [plan, workflow, phase, verify, mutate, dry run, approval, how to act, what to do first]
related_files: [phases.md, verification.md, ambiguity.md]
---

The Anim Drama Toolset agent operates in five soft phases. This skill makes
the rules explicit so you (the agent) can self-check while reasoning.

The five phases:

1. PLAN — call `submit_plan(intent, steps, tools_to_use, risks,
   needs_clarification, clarification_question)`. Required for any task that
   modifies the stage or has more than 2 steps. Skip only for pure single-
   read questions.
2. GATHER — call READ_ONLY tools to ground every claim. Useful starters:
   `get_stage_metadata`, `get_scene_summary`, `list_lights`, `get_selection`,
   `inspect_prim`, `list_skills` / `search_skills`.
3. ACT — call MUTATE tools. Each will be shown to the user for approval;
   describe what each call does before invoking it.
4. VERIFY — after every successful MUTATE call, call the verifier listed in
   the tool result's `__verify_hint__` field. Do not skip even if the
   mutate returned ok=True.
5. SUMMARY — natural-language reply, separating "what I changed" from
   "what I verified". If something failed verification, say so plainly.

Hard rules:

- Never fabricate USD paths, attribute values, or numeric defaults. Read
  them.
- For MUTATE tools, in the plan list explicitly which ones you will call.
- If the user request is ambiguous (a property they describe doesn't match
  any prim), do NOT pick at random. Set `needs_clarification=True` in the
  plan, ask one targeted question, and wait.
- A success status from a MUTATE tool means "the call did not raise". It
  does NOT mean the value is in the stage. Always verify.

See `phases.md` for examples and `verification.md` for the verify hint
contract. See `ambiguity.md` for how to phrase clarification questions.
