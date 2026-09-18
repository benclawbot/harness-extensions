# AGENTS.md

`~/Work` — small tooling experiments. One subproject lives here so far:

- `harness-extensions/` — three independent Python CLIs that close the
  top-3 gaps identified in the `coding-agent-harnesses-trends` deep
  research (sandbox, AGENTS.md loader, hook primitives). See
  [`harness-extensions/README.md`](./harness-extensions/README.md).

## Toolchain

- [`mise`](https://mise.jdx.dev/) is the tool version manager (config in `.mise.toml`).
- `_.path = "{{ cwd }}/bin"` is set, so repo-local scripts in `bin/` shadow system tools on `PATH`.
- Runtime tools in use: Python 3.14, Node 26, bubblewrap, jq. All already on `PATH` on this machine.
- `harness-extensions/` has no language-specific runtime requirements beyond Python 3.10+.

## Setup commands

- Install toolchain: `mise install` (no-op until tools are pinned)
- Run all tests:    `bash harness-extensions/tests/run-all.sh`

## Project layout

- `bin/` — repo-local scripts (on `PATH` via mise)
- `tries/` — scratch / experimental subprojects
- `harness-extensions/` — three Python CLIs (`sandbox-bash`, `agents-md`, `agent-hooks`) plus tests

## Code style

- Python 3.10+ stdlib only; no third-party dependencies.
- Type hints on function signatures.
- Bash for tests and the `bin/` scripts; shebang `#!/usr/bin/env bash`.
- Prefer explicit pass/fail assertions in tests over `set -e`.

## Testing instructions

- All component tests: `bash harness-extensions/tests/run-all.sh`
- Per-component tests: `bash harness-extensions/tests/test-<name>.sh`
- Tests create isolated temp dirs under `/tmp` and clean up on EXIT.
- A test must exit non-zero on the first assertion failure.

## PR & commit conventions

- Branch from `main`; never push to it directly.
- Commit message: conventional commits (`feat:` / `fix:` / `docs:` / `refactor:` / `chore:`).
- One logical change per commit.

## Security

- Never commit secrets — keep `.env` out of git.
- `harness-extensions/sandbox-bash/` is itself a security primitive; treat changes there with extra review.
- Hooks in `harness-extensions/agent-hooks/` execute arbitrary shell with the calling user's privileges — do not point `HOOK_FAIL_OPEN` at untrusted code paths.
