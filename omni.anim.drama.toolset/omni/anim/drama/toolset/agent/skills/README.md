# Agent Skills

This directory holds compressed "domain manuals" loaded on-demand by the agent
through `list_skills` / `search_skills` / `read_skill` tools.

Format:

- One subdirectory per skill (kebab-case id).
- Each subdirectory MUST contain a `SKILL.md` with optional YAML-ish frontmatter:

```
---
id: my-skill-id
title: Human Title
triggers: [keyword1, keyword2, ...]
related_files: [deep-dive-1.md, deep-dive-2.md]
---

Short summary body. <= ~800 chars. Tell the agent:
- when to read me
- what concepts I cover
- which related_file to read for details
```

- Other `.md` files in the same directory are picked up automatically as
  `related_files` (you don't need to list them manually).

Body length per file is truncated to 12,000 chars at read time. Keep `SKILL.md`
**short** — it is the index card. Push details to related files.
