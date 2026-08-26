# CHATGPT.md

**The behavioural contract for this repository is [`CLAUDE.md`](CLAUDE.md). Read that file.**

This pointer exists so ChatGPT / Codex finds the guidance under a filename it looks for. It is deliberately
not a copy.

CSA's previous MCP server shipped a duplicate agent-instruction file, and it drifted until it
stated the opposite of reality on tooling — a stale guidance file misleads silently, which is worse
than having none. One file is kept correct instead.

Nothing in `CLAUDE.md` is Claude-specific. It covers what the repository is, the routing rule that
governs the whole design, the invariants that fail silently, data hygiene around learner PII, and
the upstream-drift discipline. All of it applies to any agent working here.
