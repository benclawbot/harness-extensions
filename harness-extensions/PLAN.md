# Harness Extensions Plan

Three shipping increments that close the top-3 gaps identified in the
`coding-agent-harnesses-trends` research: kernel-level sandbox for `bash`,
an `AGENTS.md` loader with `CLAUDE.md` bridge and Harness Card output, and
hook primitives for pre/post tool execution.

**Scope rule.** I am not modifying the mcode binary. These are independent
tools that any agent harness (mcode, Claude Code, Codex CLI, OpenCode, …)
can invoke; nothing is wired into a vendor product yet. Wiring is a
separate step (documented in §Integration).

---

## 1. `sandbox-bash` — kernel-level sandbox for shell execution

**Why.** The NSA's May 20, 2026 Cybersecurity Information Sheet on MCP
security calls for cryptographic message integrity, least-privilege at the
tool-call boundary, tamper-evident audit, and end-to-end trust chains. The
research's headline finding is that the harness — not the model — is the
binding constraint on agent safety. mcode's `bash` tool today runs in user
space with no isolation. This is the highest-leverage missing primitive.

**Approach.** Wrap arbitrary shell commands with `bubblewrap (bwrap)`,
which is installed at `/usr/bin/bwrap` on this system. User namespaces are
enabled (`kernel.unprivileged_userns_clone=1`,
`max_user_namespaces=62457`). bwrap is the same primitive Codex CLI uses
under Seatbelt on macOS and Landlock on Linux.

**Default profile.**

| Resource       | Default            | Flag             |
| -------------- | ------------------ | ---------------- |
| `/` (root fs)  | read-only          | `--ro-bind / /`  |
| `cwd`          | read-write         | `--bind $PWD /workspace` |
| `/tmp`         | writable private   | `--tmpfs /tmp`   |
| `/home`        | read-only          | `--ro-bind /home /home`   |
| Network        | **off**            | `--unshare-net`  |
| Capabilities   | all dropped        | `--cap-drop ALL` |
| New session    | isolated           | `--new-session`  |
| Dies on parent | yes                | `--die-with-parent` |

**Overrides.**

- `--allow-net` — share host network namespace
- `--allow-home` — make `/home` writable
- `--allow-path <path>` — bind an extra path read-write (repeatable)
- `--ro-path <path>` — bind an extra path read-only (repeatable)
- `--profile <name>` — `strict` (default) | `dev` (cwd + network) | `ci`
- `--log <file>` — append JSON audit record of the invocation

**Output.** Audit log line on stdout (when `--log` is set), exit code of
the wrapped command, no other changes to its stdout/stderr.

**Acceptance.**

1. `sandbox-bash echo hello` prints `hello` and exits 0.
2. `sandbox-bash --allow-net false -- sh -c 'echo ok > /etc/test'` fails
   with a bwrap error because `/` is read-only.
3. `sandbox-bash sh -c 'echo hi > /tmp/x && cat /tmp/x'` works (tmpfs).
4. `sandbox-bash --allow-net curl https://example.invalid` fails because
   the default profile has no network.
5. `sandbox-bash --allow-net curl https://example.com` succeeds.
6. `sandbox-bash --log /tmp/audit.jsonl sh -c 'exit 7'` exits 7 and
   appends a JSON record with cmd, cwd, profile, exit, started_at.

---

## 2. `agents-md` — hierarchical AGENTS.md loader with CLAUDE.md bridge

**Why.** AGENTS.md is the de facto project-instructions standard: 60,000+
repos on GitHub, foundation-stewarded under AAIF since December 9, 2025,
parsed by 9 of the 10 most-deployed coding agents (Claude Code is the
holdout and bridges via `@AGENTS.md` or a symlink). The research treats
supporting AGENTS.md as a procurement gate for enterprise. mcode today
generates AGENTS.md via `mcode init` but does not appear to load it as
runtime instructions. This tool is the missing ingest side.

**Approach.** Standalone Python script + library. Walk from cwd to `/`,
collect every `AGENTS.md` and `CLAUDE.md` along the way, prefer the nearest
file (research's documented precedence: *the nearest file to the edited
path wins*), and emit either a concatenated instruction block or a
machine-readable Harness Card.

**Behavior.**

- Default: walk from cwd to `/`, list every file in order from deepest to
  shallow, with the *closest* file winning on conflict. Per the AGENTS.md
  spec, nested files override the root.
- Optional flag: also follow `CLAUDE.md` → if a `CLAUDE.md` references
  `@AGENTS.md`, expand it (Anthropic's bridge pattern).
- Concatenate with section markers:
  ```
  # >>> AGENTS.md: /home/tom/Work/harness-extensions/agents-md/AGENTS.md
  <contents>
  # <<< END AGENTS.md
  ```
- Default cap: 500 lines per file, 2000 total (research sweet spot).

**Subcommands.**

- `agents-md collect [--cwd PATH]` — print the merged instruction block.
- `agents-md card [--cwd PATH]` — print a Harness Card (JSON) describing
  which files were loaded, in what order, total size, and any
  conflicts/overrides.
- `agents-md show [--cwd PATH]` — list discovered files with paths and
  sizes, no contents.

**Acceptance.**

1. From a directory with `AGENTS.md` at the root and one nested, `collect`
   returns both, deepest first.
2. From a directory with only `CLAUDE.md`, `card` shows it was loaded
   via the CLAUDE.md→AGENTS.md bridge path.
3. From a directory with neither, `card` returns a JSON object with
   `loaded: []` and a `next_steps` array suggesting `mcode init` or
   `agents-md init`.
4. `agents-md card` is stable JSON — keys don't change across runs on
   the same tree.

---

## 3. `agent-hooks` — pre/post tool execution primitives

**Why.** Hooks are one of the highest-leverage harness features in the
2026 corpus — Anthropic shipped Hooks as a top-line Claude Code feature,
the Agent Plugins 1.0 spec preserves hooks alongside Skills and MCP
servers, and the NSA's per-tool-call least-privilege guidance is
mechanically a hook. mcode has no documented hook API.

**Approach.** A small Python framework that:

1. Discovers hooks from a fixed set of locations (closest wins):
   - `<cwd>/.mcode-hooks/<hook-name>.{sh,py}`
   - `~/.minimax/hooks/<hook-name>.{sh,py}`
   - `/etc/mcode/hooks/<hook-name>.{sh,py}`
2. Defines two hook phases: `pre-tool` and `post-tool`.
3. Exposes a CLI `agent-hooks run <phase> <tool-name> [args...]` and a
   Python `dispatch()` API.
4. Captures each hook's stdout/stderr/exit; aggregates; respects
   `HOOK_FAIL_OPEN` env var.

**Hook contract.**

- Hooks are executable scripts receiving JSON on stdin:
  ```json
  {"phase":"pre-tool","tool":"bash","cwd":"/path","args":{"cmd":"…"}}
  ```
- Exit 0 = allow, exit 2 = block (with stderr message), exit 1 =
  warn-and-allow, other = error.
- `post-tool` hooks also receive `"result": {...}`.
- Each invocation is logged to stderr in a structured line; a
  `--log <file>` flag mirrors it to a file.

**Acceptance.**

1. With no hooks configured, `agent-hooks run pre-tool bash echo hi`
   is a no-op and exits 0.
2. With a pre-tool hook in `cwd/.mcode-hooks/pre-tool.bash` that prints
   to stderr and exits 2, the same invocation is blocked and the hook
   message is forwarded.
3. With `HOOK_FAIL_OPEN=1`, a failing pre-tool hook warns but does not
   block.
4. The framework never invokes hooks as root and never executes from
   outside the discovery list.

---

## Cross-cutting

**Tests.** Each component gets a `tests/test_<name>.sh` that exercises
the acceptance criteria above with real shell processes (no mocking of
the sandbox). Tests run in any directory, fail loudly, and exit non-zero
on the first assertion that fails.

**Documentation.** Top-level `README.md` (one page) + per-component
`README.md` in each subdirectory.

**Git.** Three commits at the end, one per component, plus a final
amend of `AGENTS.md` so future agent runs pick it up automatically.

**Out of scope (this pass).**

- Modifying the mcode binary.
- Adding MCP server mode (the research gap, but separate workstream).
- Foundation-governance donation (requires external coordination).
- Hooks that themselves spawn sandboxed subprocesses (recursion is a
  separate design problem).

---

## Integration story (not implemented this pass)

When a future agent harness wants to use these:

1. Replace the harness's `bash` tool implementation with
   `subprocess.run(["sandbox-bash", "--profile", "dev", "--cwd",
   cwd, "--", cmd])`.
2. On session start, run `agents-md collect --cwd $cwd` and prepend
   the output to the system prompt; expose `/harness` returning
   `agents-md card --cwd $cwd` for the Harness Card UI.
3. Wrap every tool invocation with `agent-hooks run pre-tool <name> …`
   before and `post-tool <name> …` after. Surface blocked
   invocations as a structured tool error, not a crash.
