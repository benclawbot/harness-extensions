# harness-extensions

Three independent Python CLIs that close the top gaps identified in a
[September 2026 survey of coding-agent-harness trends](https://github.com/benclawbot/harness-extensions/blob/master/harness-extensions/PLAN.md):
**kernel-level sandbox** for shell execution, an **`AGENTS.md` loader**
with `CLAUDE.md` bridge and Harness Card, and **pre/post tool hook
primitives**.

| Component       | Closes the gap…                                              | Doc                                       |
| --------------- | ------------------------------------------------------------ | ----------------------------------------- |
| `sandbox-bash`  | …where shell tools run in user space with no isolation (NSA CSI, May 2026). | [README](./harness-extensions/sandbox-bash/README.md) |
| `agents-md`     | …where AGENTS.md is written but never ingested as runtime instructions. | [README](./harness-extensions/agents-md/README.md) |
| `agent-hooks`   | …where there's no documented pre/post tool hook API.        | [README](./harness-extensions/agent-hooks/README.md) |

## Why

The survey of harness trends ([full text](https://github.com/benclawbot/harness-extensions/blob/master/harness-extensions/PLAN.md))
identified seven trend axes; the top three by leverage × evidence were:

1. **Sandbox as first-class.** The NSA's May 20, 2026 Cybersecurity
   Information Sheet on MCP security calls for cryptographic message
   integrity, per-tool-call least-privilege, tamper-evident audit, and
   end-to-end trust chains.
2. **AGENTS.md ingest.** AGENTS.md is the de facto project-instructions
   standard: 60,000+ repos, foundation-stewarded under AAIF since
   December 9, 2025, parsed natively by 9 of the 10 most-deployed
   coding agents.
3. **Hook primitives.** Anthropic ships Hooks as a top-line Claude Code
   feature; Agent Plugins 1.0 preserves hooks alongside Skills and MCP
   servers; the NSA's per-tool-call least-privilege guidance is
   mechanically a hook.

These three are not product features of any one vendor — they're
primitive layers any harness can adopt. This repo is the reference
implementation.

## Quick start

```bash
git clone https://github.com/benclawbot/harness-extensions
cd harness-extensions/harness-extensions

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

## Requirements

- Python 3.10+
- Linux with `bubblewrap` (`bwrap`) on `PATH` (for `sandbox-bash`)
- `jq` (for tests)

Tested on Linux kernel 7.x with unprivileged user namespaces enabled
(the default on most distros).

## Installation

The tools are self-contained Python scripts. Either invoke them
directly from a clone of this repo, or symlink them onto your `PATH`:

```bash
git clone https://github.com/benclawbot/harness-extensions /opt/harness-extensions
for tool in sandbox-bash agents-md agent-hooks; do
    ln -sf /opt/harness-extensions/harness-extensions/$tool/$tool.py \
           /usr/local/bin/$tool
done
```

No `pip install` step; no third-party Python dependencies.

## Usage

### `sandbox-bash`

Wrap any shell command in a bubblewrap sandbox. Default profile
isolates `/`, makes cwd read-write, drops all capabilities, turns off
network, and gives you a private `/tmp`.

```bash
sandbox-bash echo hello                    # basic
sandbox-bash sh -c 'echo hi > /tmp/x'      # writable /tmp
sandbox-bash --allow-net curl https://example.com
sandbox-bash --allow-home --profile dev npm test
sandbox-bash --log /var/log/sandbox.jsonl sh -c 'exit 7'   # audit
sandbox-bash --print-bwrap -- echo hi      # debug: show the bwrap command
```

Profiles: `strict` (default; no net), `dev` (net on), `ci` (no net, no
home). `--log` emits one JSON record per invocation, suitable for
ingestion into a tamper-evident log store.

See [sandbox-bash/README.md](./harness-extensions/sandbox-bash/README.md)
for the full contract.

### `agents-md`

Hierarchical loader for `AGENTS.md` and `CLAUDE.md` with the
`CLAUDE.md → @AGENTS.md` bridge and a Harness Card.

```bash
agents-md card   --cwd /path/to/repo   # JSON Harness Card
agents-md show   --cwd /path/to/repo   # file list with line counts
agents-md collect --cwd /path/to/repo  # merged instruction block
agents-md init   --cwd /path/to/repo   # scaffold a starter AGENTS.md
```

Files are walked from cwd to `/`; the deepest file wins on conflict.
The card is a stable JSON shape — the recommended surface for a
harness's `/harness` or `/status` command.

See [agents-md/README.md](./harness-extensions/agents-md/README.md).

### `agent-hooks`

Pre/post tool-execution hook primitives. Hooks are executable scripts
discovered from:

1. `<cwd>/.mcode-hooks/`
2. `~/.minimax/hooks/`
3. `/etc/mcode/hooks/`

File naming convention: `<phase>[.<tool>][.sh|.py]`. Examples:
`pre-tool.bash`, `pre-tool.bash.sh`, `post-tool.edit.py`.

```bash
agent-hooks run pre-tool bash --arg "echo hi"
agent-hooks run post-tool read --result '{"exit":0}'
agent-hooks run pre-tool bash --arg "..." --log /var/log/hooks.jsonl
agent-hooks list --cwd /path/to/repo
```

Exit codes: `0` allow, `1` warn, `2` block, other = error (treated as
block unless `HOOK_FAIL_OPEN=1`).

See [agent-hooks/README.md](./harness-extensions/agent-hooks/README.md).

## Running tests

```bash
cd harness-extensions
bash tests/run-all.sh
```

22 acceptance tests across the three components. Tests create isolated
temp dirs under `/tmp` and clean up on EXIT.

## Project layout

```
harness-extensions/
├── PLAN.md                # design contract, acceptance criteria, integration plan
├── README.md              # you are here (at the repo root)
├── sandbox-bash/
│   ├── sandbox_bash.py
│   └── README.md
├── agents-md/
│   ├── agents_md.py
│   └── README.md
├── agent-hooks/
│   ├── agent_hooks.py
│   └── README.md
└── tests/
    ├── run-all.sh
    ├── test-sandbox-bash.sh
    ├── test-agents-md.sh
    └── test-agent-hooks.sh
```

## Integration story

The primitives are independent tools today. Wiring them into a harness
is a separate step (see [`PLAN.md` §Integration](./harness-extensions/PLAN.md#integration-story-not-implemented-this-pass)):

1. Replace the harness's `bash` tool with
   `subprocess.run(["sandbox-bash", "--profile", "dev", "--cwd", cwd, "--", cmd])`.
2. On session start, run `agents-md collect --cwd $cwd` and prepend
   the output to the system prompt; expose `/harness` returning
   `agents-md card --cwd $cwd` for the Harness Card UI.
3. Wrap every tool invocation with
   `agent-hooks run pre-tool <name> …` before and
   `post-tool <name> …` after. Surface blocked invocations as a
   structured tool error, not a crash.

None of these require modifying vendor code; they can live in a
wrapper layer or in a vendor-side patch.

## Contributing

Bug reports and PRs welcome. Each component has its own `README.md`
and acceptance tests; please add a test for any new behavior.

## License

[MIT](./LICENSE).

## References

- [The harness-trend survey that motivated this work](https://github.com/benclawbot/harness-extensions/blob/master/harness-extensions/PLAN.md)
- [NSA CSI on MCP security (May 20, 2026)](https://www.nsa.gov/Press-Room/Press-Releases-Statements/Press-Release-View/Article/4496698/nsa-releases-security-design-considerations-for-ai-driven-automation-leveraging/)
- [Agent Plugins 1.0 specification](https://github.com/agentplugins/agent-plugins-spec)
- [agents.md standard](https://agents.md)
- [Model Context Protocol](https://modelcontextprotocol.io)
