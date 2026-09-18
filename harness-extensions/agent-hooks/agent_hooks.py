#!/usr/bin/env python3
"""agent-hooks — pre/post tool execution hook primitives.

Two phases: pre-tool (run before the tool call) and post-tool (run
after). Hooks are discovered from a fixed search path (closest wins):

  1. <cwd>/.mcode-hooks/<name>.{sh,py}
  2. ~/.minimax/hooks/<name>.{sh,py}
  3. /etc/mcode/hooks/<name>.{sh,py}

The hook receives a JSON payload on stdin describing the tool call.
Exit code contract:

  0  — allow (the harness proceeds with the tool call)
  1  — warn-and-allow (stderr message surfaced as a warning)
  2  — block (stderr message surfaced as a structured tool error)
  any other — error; treated like 2 unless HOOK_FAIL_OPEN=1

See ../PLAN.md §3 for the contract.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PHASES = ("pre-tool", "post-tool")

# Discovery order: project first, user second, system third.
SEARCH_PATHS = [
    Path(".mcode-hooks"),
    Path.home() / ".minimax" / "hooks",
    Path("/etc/mcode/hooks"),
]

HOOK_FAIL_OPEN_DEFAULT = False


def find_hooks(cwd: Path, phase: str, tool_name: str) -> list[Path]:
    """Return matching hook scripts in discovery order.

    File naming convention:
      <phase>[.<tool>][.sh|.py]

    Examples (in order of specificity, all valid):
      pre-tool.bash.sh
      pre-tool.bash.py
      pre-tool.bash            (treated as shell)
      pre-tool.sh
      pre-tool.py
      pre-tool                 (treated as shell, applies to every tool)
    """
    matches: list[Path] = []
    suffixes = ("", ".sh", ".py")
    candidates_for_base: list[str] = []
    # Tool-specific candidates.
    for ext in suffixes:
        candidates_for_base.append(f"{phase}.{tool_name}{ext}")
    # Generic phase candidates.
    for ext in suffixes:
        candidates_for_base.append(f"{phase}{ext}")
    for base in SEARCH_PATHS:
        full = cwd / base if base == Path(".mcode-hooks") else base
        if not full.is_dir():
            continue
        for name in candidates_for_base:
            p = full / name
            if p.is_file():
                matches.append(p)
    return matches


def build_payload(phase: str, tool_name: str, args: dict, result: dict | None) -> dict:
    return {
        "phase": phase,
        "tool": tool_name,
        "cwd": os.getcwd(),
        "args": args,
        "result": result,
        "ts": __import__("time").time(),
    }


def run_hook(hook: Path, payload: dict) -> tuple[int, str, str]:
    """Run a hook with payload on stdin. Returns (exit, stdout, stderr)."""
    if hook.suffix == ".py":
        interp = sys.executable
        argv = [interp, str(hook)]
    else:
        interp = "/bin/sh"
        argv = [interp, str(hook)]
    proc = subprocess.run(
        argv,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def dispatch(
    cwd: Path,
    phase: str,
    tool_name: str,
    args: dict,
    result: dict | None = None,
    log_path: Path | None = None,
    fail_open: bool | None = None,
) -> tuple[bool, list[dict]]:
    """Run all matching hooks. Returns (allowed, events).

    `events` is a list of {"hook": path, "exit": int, "stdout": str,
    "stderr": str, "outcome": "allow|warn|block|error"} records.
    """
    if phase not in PHASES:
        raise ValueError(f"unknown phase {phase!r}; expected one of {PHASES}")
    if fail_open is None:
        fail_open = os.environ.get("HOOK_FAIL_OPEN") in ("1", "true", "yes")

    hooks = find_hooks(cwd, phase, tool_name)
    payload = build_payload(phase, tool_name, args, result)
    events: list[dict] = []
    allowed = True
    block_message: str | None = None

    for hook in hooks:
        exit_code, stdout, stderr = run_hook(hook, payload)
        outcome = {0: "allow", 1: "warn", 2: "block"}.get(exit_code, "error")
        events.append(
            {
                "hook": str(hook),
                "exit": exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "outcome": outcome,
            }
        )
        if outcome == "block":
            allowed = False
            block_message = stderr.strip() or f"{hook} blocked the call (exit 2)"
        elif outcome == "error":
            if not fail_open:
                allowed = False
                block_message = stderr.strip() or f"{hook} failed (exit {exit_code})"

    # Log structured line(s).
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            for ev in events:
                fh.write(
                    json.dumps(
                        {
                            "tool": "agent-hooks",
                            "phase": phase,
                            "target_tool": tool_name,
                            **ev,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )

    return allowed, events


def cmd_run(ns: argparse.Namespace) -> int:
    args = {"raw": ns.tool_args} if ns.tool_args else {}
    try:
        result = json.loads(ns.result) if ns.result else None
    except json.JSONDecodeError as e:
        print(f"agent-hooks: --result must be valid JSON: {e}", file=sys.stderr)
        return 2

    cwd = Path(ns.cwd).resolve()
    allowed, events = dispatch(
        cwd=cwd,
        phase=ns.phase,
        tool_name=ns.tool,
        args=args,
        result=result,
        log_path=Path(ns.log) if ns.log else None,
    )

    # Emit structured events to stderr (one JSON per line), and a final
    # verdict on stdout that the harness can parse cheaply.
    for ev in events:
        print(json.dumps(ev, sort_keys=True), file=sys.stderr)

    if allowed:
        print(json.dumps({"verdict": "allow", "phase": ns.phase, "tool": ns.tool}, sort_keys=True))
        return 0
    # Block: collect the first block message.
    msg = next(
        (e["stderr"].strip() for e in events if e["outcome"] in ("block", "error") and e["stderr"].strip()),
        "blocked",
    )
    print(json.dumps({"verdict": "block", "phase": ns.phase, "tool": ns.tool, "message": msg}, sort_keys=True))
    return 2


def cmd_list(ns: argparse.Namespace) -> int:
    cwd = Path(ns.cwd).resolve()
    for phase in PHASES:
        # We have to peek into the search paths to enumerate by tool;
        # for `list`, just enumerate the generic phase hooks plus every
        # tool-specific hook in cwd.
        hooks = []
        for base in SEARCH_PATHS:
            full = cwd / base if base == Path(".mcode-hooks") else base
            if not full.is_dir():
                continue
            for f in sorted(full.iterdir()):
                if f.is_file() and (f.suffix in (".sh", ".py")):
                    hooks.append(f)
        if hooks:
            print(f"--- {phase} ---")
            for h in hooks:
                print(f"  {h}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent-hooks", description="Pre/post tool execution hooks")
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--log", help="Append structured events to this file")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Dispatch hooks for one tool invocation")
    p_run.add_argument("phase", choices=PHASES)
    p_run.add_argument("tool", help="Tool name (e.g. bash, read, edit)")
    p_run.add_argument("--arg", dest="tool_args", help="Tool argument string (raw)")
    p_run.add_argument("--result", help="Tool result JSON (post-tool only)")
    p_run.set_defaults(func=cmd_run)

    p_list = sub.add_parser("list", help="List discovered hooks")
    p_list.set_defaults(func=cmd_list)

    ns = parser.parse_args(argv)
    return ns.func(ns)


if __name__ == "__main__":
    sys.exit(main())
