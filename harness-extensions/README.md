# Harness Extensions

Three independent tools that close the top-3 gaps identified in the
[`coding-agent-harnesses-trends`](../../../../tmp/mavis-deep-research/20260918_185545_coding_agent_harness_trends/final_turn_001.md)
deep research:

| Component       | Gap closed                                              | Location              |
| --------------- | ------------------------------------------------------- | --------------------- |
| `sandbox-bash`  | kernel-level sandbox for `bash` (NSA CSI baseline)      | [`sandbox-bash/`](./sandbox-bash/) |
| `agents-md`     | AGENTS.md loader + CLAUDE.md bridge + Harness Card      | [`agents-md/`](./agents-md/)       |
| `agent-hooks`   | pre/post tool-execution hook primitives                 | [`agent-hooks/`](./agent-hooks/)   |

See [PLAN.md](./PLAN.md) for the full design contract and acceptance
criteria.

## Quick start

```bash
# Sandbox a shell command (read-only root, no network, writable cwd).
./sandbox-bash/sandbox_bash.py echo hello
./sandbox-bash/sandbox_bash.py --allow-net --profile dev -- npm test

# Load AGENTS.md instructions and inspect the Harness Card.
./agents-md/agents_md.py --cwd /path/to/repo card
./agents-md/agents_md.py --cwd /path/to/repo collect

# Run hooks around a tool invocation.
./agent-hooks/agent_hooks.py run pre-tool bash --arg "rm -rf /"
./agent-hooks/agent_hooks.py run post-tool read --result '{"exit":0}'
```

## Why these three

The research identified seven trend axes; the top three by leverage ×
evidence were:

1. **Sandbox as first-class.** The NSA's May 20, 2026 Cybersecurity
   Information Sheet on MCP security calls for cryptographic message
   integrity, per-tool-call least-privilege, tamper-evident audit,
   and end-to-end trust chains. mcode's `bash` tool today runs in
   user space with no isolation — this is the highest-leverage
   missing primitive.

2. **AGENTS.md ingest.** AGENTS.md is the de facto project-instructions
   standard: 60,000+ repos, foundation-stewarded under AAIF, parsed by
   9 of the 10 most-deployed coding agents. mcode writes AGENTS.md via
   `mcode init` but doesn't appear to load it as runtime instructions.
   This tool is the missing ingest side, with the CLAUDE.md → `@AGENTS.md`
   bridge for teams that already use Claude Code.

3. **Hook primitives.** Hooks are one of the highest-leverage harness
   features in the 2026 corpus: Anthropic's Hooks are top-line in
   Claude Code, Agent Plugins 1.0 preserves them, and the NSA's
   per-tool-call least-privilege guidance is mechanically a hook.

## Not modified

The mcode binary is unchanged. These are independent tools any harness
can call. Wiring them into mcode is a separate workstream (see
[PLAN.md §Integration](./PLAN.md#integration-story-not-implemented-this-pass)).

## Tests

```bash
./tests/run-all.sh
```

Each component has its own test script:

- [`tests/test-sandbox-bash.sh`](./tests/test-sandbox-bash.sh)
- [`tests/test-agents-md.sh`](./tests/test-agents-md.sh)
- [`tests/test-agent-hooks.sh`](./tests/test-agent-hooks.sh)

## License

Internal scaffolding; not yet released.
