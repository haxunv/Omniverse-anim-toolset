# Skills — on-demand domain knowledge

## Why a skill library

The naive way to give an agent domain knowledge is to stuff it all into the
system prompt. That fails for three reasons:

- It is expensive (every request pays for re-reading the whole prompt).
- It dilutes attention — the model treats important rules and reference
  text the same.
- It scales badly — Omniverse + OpenUSD + your project knowledge would
  saturate any context window.

A **skill library** flips this: a small index lives in the prompt, and the
detailed manuals are pulled on demand by the agent itself via tools.

## Disk layout

```
agent/skills/
    README.md                   # human note about the format
    usd-fundamentals/
        SKILL.md                # short summary + frontmatter (loaded as index)
        stage-and-prim.md       # deep-dive (read on demand)
        schemas.md
    usd-layers/
        SKILL.md
        layer-stack.md
        mute-vs-remove.md
    xform-ops-and-units/
        SKILL.md
        xformop-order.md
        units-and-axis.md
    animation-time-samples/
        SKILL.md
        time-samples-vs-default.md
        retiming.md
    camera-moves/
        SKILL.md
        shot-vocabulary.md
        dolly-and-orbit.md
    lighting-recipes/
        SKILL.md
        three-point.md
        mood-presets.md
    kit-commands/
        SKILL.md
        common-commands.md
        undo-stack.md
    agent-workflow/
        SKILL.md
        phases.md
        verification.md
        ambiguity.md
```

Override the directory by setting `ANIM_DRAMA_AGENT_SKILLS_DIR` env var.

## SKILL.md format

```
---
id: my-skill-id           # kebab-case, must be unique
title: Human Title
triggers: [keyword1, keyword2, ...]
related_files: [some-deep-dive.md]
---

Short summary body. <= ~800 chars.
- Tell the agent: when to read me / what I cover.
- Point to deep-dive files for details.
```

Notes:

- The frontmatter is YAML-ish (no real YAML parser dependency). Only `key:
  value` and `key: [a, b, c]` are supported.
- `related_files` is auto-augmented with any other `.md` files found in
  the same skill directory; you don't need to list them manually.
- The body is what's returned by `read_skill(skill_id)`. Body length is
  truncated to 12,000 chars per call.

## How the agent uses skills

The system prompt instructs:

> When in doubt about USD or animation concepts, search skills FIRST.

Workflow:

```
search_skills(query="layer mute")
  -> [{id: "usd-layers", title: "...", snippet: "..."}]

read_skill("usd-layers")           # SKILL.md summary
  -> { body: "Read me when ...", related_files: ["mute-vs-remove.md"] }

read_skill("usd-layers", file="mute-vs-remove.md")    # the deep dive
  -> { body: "<full text>" }
```

Only the SKILL.md summaries are loaded into context (when the agent
explicitly asks); deep-dive files are pulled only when needed.

## Adding a new skill

1. Pick a kebab-case id, create `agent/skills/<id>/`.
2. Write `SKILL.md` with frontmatter (id, title, triggers).
3. Optional: add deep-dive `.md` files alongside.
4. Test: invoke `list_skills` from the chat panel — your skill should
   appear without restarting the extension (skills are loaded fresh on
   every tool call).

Conventions:

- Keep SKILL.md SHORT (rule of thumb: under 800 chars body).
- Make `triggers` exhaustive (synonyms, common misspellings, related
  domain terms). They are matched case-insensitively.
- Push examples, tables, and walkthroughs into deep-dive files, not
  SKILL.md.
- Skill files are read at runtime — they ship with the extension; no
  rebuild required after editing.

## Why not embeddings / vector store?

- Setup cost is high (index, embedder, persistence) for what's currently
  a corpus of ~20 files.
- BM25-ish keyword search over ~30 KB of markdown is fast (<1ms) and
  predictable.
- Embeddings can be added later as a drop-in replacement of
  `search_skills` — the agent doesn't know the implementation.

## Why one big SKILL.md per topic instead of many small files?

- Keeps `list_skills` output short and scannable.
- The agent's first decision is "which topic?", not "which paragraph?"
- Once a topic is selected, the deep-dive files become the unit of read.
