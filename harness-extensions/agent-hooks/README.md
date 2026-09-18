# `agent-hooks`

Pre/post tool-execution hook primitives for any coding agent harness.

Backs the hook gap identified in the
`coding-agent-harnesses-trends` research. Anthropic ships Hooks as a
top-line Claude Code feature; Agent Plugins 1.0 preserves hooks
alongside Skills and MCP servers. mcode has no documented hook API.

## Hook discovery

Hooks live in any of these directories; closest wins:

1. `<cwd>/.mcode-hooks/`
2. `~/.minimax/hooks/`
3. `/etc/mcode/hooks/`

File naming convention:

```
<phase>[.<tool>][.sh|.py]
```

Examples (all valid):

| File                            | Phase      | Tool  | Lang  |
| ------------------------------- | ---------- | ----- | ----- |
| `pre-tool.sh`                   | pre-tool   | all   | shell |
| `pre-tool.bash`                 | pre-tool   | bash  | shell |
| `pre-tool.bash.sh`              | pre-tool   | bash  | shell |
| `pre-tool.bash.py`              | pre-tool   | bash  | py    |
| `post-tool.edit.sh`             | post-tool  | edit  | shell |

## Hook contract

The hook receives a JSON payload on stdin:

```json
{
  "phase": "pre-tool",
  "tool": "bash",
  "cwd": "/home/tom",
  "args": {"raw": "rm -rf /"},
  "result": null,
  "ts": 1789751290.63
}
```

`post-tool` calls also include `"result": {...}` with the tool's
return value.

### Exit code semantics

| Exit | Meaning    | Harness behavior                                    |
| ---- | ---------- | --------------------------------------------------- |
| 0    | allow      | proceed with the tool call                          |
| 1    | warn       | proceed, surface hook's stderr as a warning         |
| 2    | block      | abort the tool call, surface stderr as tool error   |
| other | error    | treated as block unless `HOOK_FAIL_OPEN=1`          |

## Usage

```bash
./agent-hooks run pre-tool bash --arg "echo hi"
./agent-hooks run post-tool read --result '{"exit":0}'
./agent-hooks run pre-tool bash --arg "..." --log /var/log/hooks.jsonl
./agent-hooks list --cwd /path/to/repo
```

## Output

The CLI prints one JSON event per hook to stderr, then a final
verdict JSON to stdout:

```json
{"hook": "/repo/.mcode-hooks/pre-tool.bash", "exit": 2, "outcome": "block",
 "stderr": "blocking rm -rf calls\n", "stdout": ""}
```

```json
{"phase": "pre-tool", "tool": "bash", "verdict": "block",
 "message": "blocking rm -rf calls"}
```

A harness can parse the verdict cheaply (last stdout line) and treat
the rest as a structured event log.

## Audit log

`--log <file>` appends one JSON line per hook invocation:

```json
{"tool": "agent-hooks", "phase": "pre-tool", "target_tool": "bash",
 "hook": "/repo/.mcode-hooks/pre-tool.bash", "exit": 2, "outcome": "block",
 "stderr": "blocking rm -rf calls\n", "stdout": ""}
```

For tamper-evident audit, hash-chain this log yourself; this satisfies
the NSA CSI's "tamper-evident audit for every agent action" baseline.

## Environment

- `HOOK_FAIL_OPEN=1` — treat any non-zero, non-2 exit as warn instead
  of block. Useful for early-stage hook development.

## Exit codes

- `0` — all hooks allowed
- `2` — at least one hook blocked
- `2` for CLI usage errors
