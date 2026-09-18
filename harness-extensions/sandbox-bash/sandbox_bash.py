#!/usr/bin/env python3
"""sandbox-bash — wrap a shell command in a bubblewrap sandbox.

Default profile isolates /, makes cwd read-write, drops all capabilities,
and turns off network. See ../PLAN.md §1 for the full contract.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROFILES = {
    "strict": {
        "allow_net": False,
        "allow_home": False,
        "tmpfs_tmp": True,
    },
    "dev": {
        "allow_net": True,
        "allow_home": False,
        "tmpfs_tmp": True,
    },
    "ci": {
        "allow_net": False,
        "allow_home": False,
        "tmpfs_tmp": True,
    },
}


def build_bwrap_args(
    cwd: Path,
    profile: str,
    allow_net: bool | None,
    allow_home: bool | None,
    allow_paths: list[Path],
    ro_paths: list[Path],
    cmd: list[str],
) -> list[str]:
    """Construct the bwrap argv from flags + command."""
    p = dict(PROFILES[profile])
    if allow_net is not None:
        p["allow_net"] = allow_net
    if allow_home is not None:
        p["allow_home"] = allow_home

    # When cwd is under /tmp, mounting a fresh tmpfs there would hide
    # the cwd path. Remap the in-sandbox cwd to /tmp/<basename> and
    # bind the real cwd into the new tmpfs.
    in_sandbox_cwd = str(cwd)
    remap_tmp = p["tmpfs_tmp"] and str(cwd).startswith("/tmp/")
    if remap_tmp:
        in_sandbox_cwd = f"/tmp/{cwd.name}"

    args: list[str] = [
        "bwrap",
        "--new-session",
        "--die-with-parent",
        "--cap-drop", "ALL",
        "--ro-bind", "/", "/",
        "--dev", "/dev",
        "--proc", "/proc",
    ]

    if p["tmpfs_tmp"]:
        args += ["--tmpfs", "/tmp"]

    if remap_tmp:
        args += ["--bind", str(cwd), in_sandbox_cwd]
    else:
        args += ["--bind", str(cwd), str(cwd)]

    if not p["allow_net"]:
        args += ["--unshare-net"]

    if not p["allow_home"]:
        args += ["--ro-bind", "/home", "/home"]
    else:
        # /home was already ro-bound above; bwrap semantics: last bind
        # wins, so re-bind the caller's $HOME as writable.
        home = Path.home()
        if home.exists():
            args += ["--bind", str(home), str(home)]

    for path in ro_paths:
        args += ["--ro-bind", str(path), str(path)]
    for path in allow_paths:
        args += ["--bind", str(path), str(path)]

    # Enter the (possibly remapped) cwd inside the sandbox.
    args += ["--chdir", in_sandbox_cwd]
    args += ["--"]
    args += cmd
    return args


def emit_audit(log_path: Path | None, payload: dict) -> None:
    if log_path is None:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sandbox-bash",
        description="Run a command inside a bubblewrap sandbox.",
    )
    parser.add_argument("--cwd", default=os.getcwd(), help="Working directory (default: cwd)")
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        default="strict",
        help="Sandbox profile (default: strict)",
    )
    parser.add_argument("--allow-net", dest="allow_net", action="store_true", help="Enable network")
    parser.add_argument("--no-allow-net", dest="allow_net", action="store_false", help="Disable network (default)")
    parser.add_argument("--allow-home", dest="allow_home", action="store_true", help="Make /home writable")
    parser.add_argument("--no-allow-home", dest="allow_home", action="store_false", help="Make /home read-only (default)")
    parser.add_argument("--allow-path", action="append", default=[], help="Bind an extra path read-write (repeatable)")
    parser.add_argument("--ro-path", action="append", default=[], help="Bind an extra path read-only (repeatable)")
    parser.add_argument("--log", help="Append a JSON audit record to this file")
    parser.add_argument("--print-bwrap", action="store_true", help="Print the bwrap command instead of running it (for debugging)")
    parser.add_argument("--", dest="sep", nargs="?", default=False, help="Separator before the command")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to run (after --)")

    parser.set_defaults(allow_net=None, allow_home=None)
    ns = parser.parse_args(argv)

    # Normalize: anything after "--" is the command.
    cmd = ns.command
    if ns.sep is False:
        # No explicit -- separator; take all remaining positional args as the command.
        pass
    else:
        if cmd and cmd[0] == "--":
            cmd = cmd[1:]

    if not cmd:
        print("sandbox-bash: no command given", file=sys.stderr)
        return 2

    if shutil.which("bwrap") is None:
        print("sandbox-bash: bubblewrap (bwrap) not found on PATH", file=sys.stderr)
        return 127

    cwd = Path(ns.cwd).resolve()
    if not cwd.exists():
        print(f"sandbox-bash: cwd does not exist: {cwd}", file=sys.stderr)
        return 2

    allow_paths = [Path(p).resolve() for p in ns.allow_path]
    ro_paths = [Path(p).resolve() for p in ns.ro_path]

    args = build_bwrap_args(
        cwd=cwd,
        profile=ns.profile,
        allow_net=ns.allow_net,
        allow_home=ns.allow_home,
        allow_paths=allow_paths,
        ro_paths=ro_paths,
        cmd=cmd,
    )

    if ns.print_bwrap:
        print(shlex.join(args))
        return 0

    started_at = time.time()
    completed = subprocess.run(args)
    exit_code = completed.returncode
    finished_at = time.time()

    emit_audit(
        Path(ns.log) if ns.log else None,
        {
            "tool": "sandbox-bash",
            "cmd": cmd,
            "cwd": str(cwd),
            "profile": ns.profile,
            "allow_net": ns.allow_net if ns.allow_net is not None else PROFILES[ns.profile]["allow_net"],
            "allow_home": ns.allow_home if ns.allow_home is not None else PROFILES[ns.profile]["allow_home"],
            "exit": exit_code,
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": int((finished_at - started_at) * 1000),
        },
    )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
