# Anim Drama Toolset Agent — Developer Docs

This directory documents the design of the **Copilot Agent** layer inside the
`omni.anim.drama.toolset` extension. It is targeted at developers extending
the agent (adding tools, skills, new agents), not end users.

For end-user features see `../README.md` and `../Overview.md`.

## Read order

1. [`ARCHITECTURE.md`](./ARCHITECTURE.md) — high-level layering and where each
   piece lives.
2. [`PHASES.md`](./PHASES.md) — the soft state machine
   `plan -> gather -> act -> verify -> summary` and how it is enforced.
3. [`META_TOOLS.md`](./META_TOOLS.md) — USD prim introspection + Kit command
   introspection (the L1 / discovery layer).
4. [`SKILLS.md`](./SKILLS.md) — the on-demand domain knowledge layer; skill
   format, where files live, how the agent searches them.
5. [`VERIFICATION.md`](./VERIFICATION.md) — `verify_with` contract and
   `__verify_hint__` injection, how to wire a new MUTATE tool into it.
6. [`MCP_INTEGRATION.md`](./MCP_INTEGRATION.md) — bridging external MCP servers
   (NVIDIA Kit MCP / USD Code MCP / OmniUI MCP / your own) into our
   `ToolRegistry` so the agent can call them transparently.
7. [`ADDING_A_TOOL.md`](./ADDING_A_TOOL.md) — concrete step-by-step recipe for
   adding a new tool or a new skill.
8. [`CHANGELOG.md`](./CHANGELOG.md) — agent-layer change log (separate from
   the extension-wide `docs/CHANGELOG.md`).

## Design principles (north stars)

1. **Tool-use is not a downgrade.** Every modern agent (Claude Code, Cursor,
   Devin, ChatUSD) is a tool-using LLM. "Agentness" comes from the quality of
   tools / loop / knowledge, not from removing tools.
2. **Two layers of tools, not one.** L2 high-level domain tools encode best
   practices. L1 meta-tools let the agent discover and act in unknown
   territory. Both must exist.
3. **Compress knowledge into skills, retrieve on demand.** Don't grow the
   system prompt; grow the skill library.
4. **Plan -> Act -> Verify is a soft contract.** We don't hard-block the LLM
   between phases (that fights model nature). We make the right move easy
   (via tools / hints) and the wrong move visible (via approvals / verify
   hints / UI badges).
5. **Verification is mandatory for MUTATE.** A MUTATE returning success only
   means it didn't raise. Always read back.
6. **Stay single-agent until pain forces a split.** A well-tooled single
   agent beats a poorly-routed multi-agent system in the vast majority of
   real workflows.
