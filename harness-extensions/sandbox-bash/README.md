# `sandbox-bash`

Wrap any shell command in a [bubblewrap](https://github.com/containers/bubblewrap)
sandbox with sensible defaults: read-only root, writable cwd, private
`/tmp`, all capabilities dropped, network off by default.

Backs the kernel-level sandbox gap identified in the
`coding-agent-harnesses-trends` research (NSA CSI, May 20, 2026).

## Usage

```bash
./sandbox-bash echo hello                    # basic
./sandbox-bash sh -c 'echo hi > /tmp/x'      # writable /tmp
./sandbox-bash --allow-net curl https://example.com
./sandbox-bash --allow-home --profile dev npm test
./sandbox-bash --allow-path /opt/mytool -- my-tool --flag
./sandbox-bash --log /var/log/sandbox.jsonl sh -c 'exit 7'   # audit
./sandbox-bash --print-bwrap -- echo hi      # debug: show the bwrap command
```

## Profiles

| Profile  | Network | `/home`     | `/tmp`    | Use case                          |
| -------- | ------- | ----------- | --------- | --------------------------------- |
| `strict` | off     | read-only   | private   | default; untrusted code execution |
| `dev`    | on      | read-only   | private   | day-to-day shell work             |
| `ci`     | off     | read-only   | private   | CI build / test runners           |

## Audit log

When `--log <file>` is set, `sandbox-bash` appends a JSON line per
invocation:

```json
{
  "tool": "sandbox-bash",
  "cmd": ["sh", "-c", "exit 7"],
  "cwd": "/home/tom",
  "profile": "strict",
  "allow_net": true,
  "allow_home": false,
  "exit": 7,
  "started_at": 1789751290.63,
  "finished_at": 1789751290.64,
  "duration_ms": 8
}
```

The harness wrapper can pipe this into a tamper-evident log store to
satisfy the NSA CSI's "tamper-evident audit for every agent action"
requirement.

## Exit codes

- Wrapper exit matches the wrapped command's exit code.
- `2` for usage errors (no command, missing cwd).
- `127` if `bwrap` is not on `PATH`.

## Limitations

- Uses user namespaces, so rootful / no-new-privs hosts will fail.
- `/home` is always either fully read-only or fully writable per the
  caller's `$HOME`; per-user granularity requires per-path flags.
- Audit log is append-only at the OS level; for cryptographic
  tamper-evidence, hash-chain the log yourself.
