#!/usr/bin/env python3
"""agents-md — hierarchical AGENTS.md loader with CLAUDE.md bridge.

Walks from cwd to /, collects every AGENTS.md and CLAUDE.md in order
from deepest to shallow, follows the CLAUDE.md → @AGENTS.md reference,
and emits either a merged instruction block (collect) or a Harness Card
JSON describing what was loaded (card).

See ../PLAN.md §2 for the contract.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Cap per-file and total length. The community-converged sweet spot for
# AGENTS.md is 200–500 lines; the loader enforces 500/file, 2000 total
# unless overridden.
DEFAULT_PER_FILE_CAP = 500
DEFAULT_TOTAL_CAP = 2000

# Pattern for the @AGENTS.md bridge reference inside CLAUDE.md.
# Anthropic's docs: "create a CLAUDE.md that imports it so both tools
# read the same instructions without duplicating them."
BRIDGE_RE = re.compile(r"@AGENTS\.md")


def find_agents_files(start: Path) -> list[Path]:
    """Walk from start up to /, returning every AGENTS.md and CLAUDE.md
    in order from deepest to shallowest. Symlinks are not followed."""
    found: list[Path] = []
    seen_dirs: set[Path] = set()
    cur = start.resolve()
    if cur.is_file():
        cur = cur.parent
    while True:
        if cur in seen_dirs:
            break
        seen_dirs.add(cur)
        for name in ("AGENTS.md", "agents.md", "CLAUDE.md", "claude.md"):
            p = cur / name
            if p.is_file():
                found.append(p)
        if cur == cur.parent:
            break
        cur = cur.parent
    return found


def read_capped(path: Path, cap: int) -> tuple[str, bool]:
    """Read a file, truncating to `cap` lines. Returns (text, truncated)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if len(lines) > cap:
        return "\n".join(lines[:cap]), True
    return text, False


def render_bridge(content: str, base_dir: Path) -> tuple[str, list[str]]:
    """Resolve @AGENTS.md references inside a CLAUDE.md. Returns the
    resolved text plus the list of expanded file paths."""
    expanded: list[str] = []
    # Only do at-most-one level of expansion; recursive expansion is an
    # explicit out-of-scope (loop protection).
    if not BRIDGE_RE.search(content):
        return content, expanded
    target = base_dir / "AGENTS.md"
    if not target.is_file():
        return content, expanded
    expanded.append(str(target))
    bridge_text, _ = read_capped(target, DEFAULT_PER_FILE_CAP)
    # Replace the @AGENTS.md reference with the actual file contents,
    # wrapped so it's obvious what came from the bridge.
    resolved = BRIDGE_RE.sub(
        f"<!-- @AGENTS.md → {target} -->\n{bridge_text}\n<!-- end @AGENTS.md -->",
        content,
        count=1,
    )
    return resolved, expanded


def collect(start: Path, per_file_cap: int, total_cap: int) -> dict:
    """Return a structured payload: merged text + metadata."""
    files = find_agents_files(start)
    sections: list[dict] = []
    total_lines = 0
    truncated_any = False
    bridge_expansions: list[str] = []

    for path in files:
        text, truncated = read_capped(path, per_file_cap)
        truncated_any = truncated or truncated_any
        if path.name.lower() == "claude.md":
            text, expanded = render_bridge(text, path.parent)
            bridge_expansions.extend(expanded)
        line_count = text.count("\n") + 1
        total_lines += line_count
        sections.append(
            {
                "path": str(path),
                "name": path.name,
                "lines": line_count,
                "truncated": truncated,
            }
        )
        if total_lines >= total_cap:
            break

    merged_parts: list[str] = []
    for section, path in zip(sections, files):
        text, _ = read_capped(path, per_file_cap)
        if path.name.lower() == "claude.md":
            text, _ = render_bridge(text, path.parent)
        header = (
            f"# >>> {path.name}: {path}\n"
            f"# ({section['lines']} lines"
            + (" [truncated]" if section["truncated"] else "")
            + ")\n"
        )
        merged_parts.append(header + text.rstrip() + "\n# <<< END " + path.name + "\n")

    return {
        "files": sections,
        "bridge_expansions": bridge_expansions,
        "total_lines": total_lines,
        "truncated": truncated_any,
        "merged": "\n".join(merged_parts).rstrip() + "\n",
    }


def next_steps(start: Path) -> list[str]:
    """Suggestions for an empty workspace."""
    return [
        "No AGENTS.md or CLAUDE.md found.",
        f"Run `mcode init {start}` to bootstrap one from the codebase.",
        "Or run `agents-md init` to scaffold a starter file.",
    ]


def cmd_collect(ns: argparse.Namespace) -> int:
    payload = collect(Path(ns.cwd), ns.per_file_cap, ns.total_cap)
    if not payload["files"]:
        if not ns.quiet:
            for line in next_steps(Path(ns.cwd)):
                print(f"# {line}", file=sys.stderr)
        return 1
    sys.stdout.write(payload["merged"])
    return 0


def cmd_card(ns: argparse.Namespace) -> int:
    payload = collect(Path(ns.cwd), ns.per_file_cap, ns.total_cap)
    card = {
        "cwd": str(Path(ns.cwd).resolve()),
        "loaded": [
            {"path": f["path"], "name": f["name"], "lines": f["lines"], "truncated": f["truncated"]}
            for f in payload["files"]
        ],
        "bridge_expansions": payload["bridge_expansions"],
        "total_lines": payload["total_lines"],
        "truncated": payload["truncated"],
    }
    if not payload["files"]:
        card["next_steps"] = next_steps(Path(ns.cwd))
    sys.stdout.write(json.dumps(card, indent=2, sort_keys=True) + "\n")
    return 0


def cmd_show(ns: argparse.Namespace) -> int:
    payload = collect(Path(ns.cwd), ns.per_file_cap, ns.total_cap)
    if not payload["files"]:
        print("(no AGENTS.md or CLAUDE.md found)", file=sys.stderr)
        return 1
    for f in payload["files"]:
        marker = " [truncated]" if f["truncated"] else ""
        print(f"{f['lines']:>5}  {f['path']}{marker}")
    if payload["bridge_expansions"]:
        print("\nCLAUDE.md → @AGENTS.md bridge expansions:")
        for e in payload["bridge_expansions"]:
            print(f"  → {e}")
    print(f"\nTotal: {payload['total_lines']} lines across {len(payload['files'])} file(s)")
    return 0


def cmd_init(ns: argparse.Namespace) -> int:
    """Scaffold a starter AGENTS.md if none exists."""
    target = Path(ns.cwd).resolve() / "AGENTS.md"
    if target.exists() and not ns.force:
        print(f"{target} already exists; use --force to overwrite", file=sys.stderr)
        return 1
    starter = (
        "# AGENTS.md\n"
        "\n"
        "Scaffold for an AI coding agent working in this repository.\n"
        "Replace each section with your project's specifics.\n"
        "\n"
        "## Setup commands\n"
        "- Install deps: `<fill in>`\n"
        "- Build:        `<fill in>`\n"
        "- Test:         `<fill in>`\n"
        "- Lint:         `<fill in>`\n"
        "\n"
        "## Project layout\n"
        "- `<fill in top-level directories>`\n"
        "\n"
        "## Code style\n"
        "- `<fill in>`\n"
        "\n"
        "## Testing instructions\n"
        "- `<fill in>`\n"
        "\n"
        "## PR & commit conventions\n"
        "- Branch from `<default-branch>`.\n"
        "- Conventional commits (`feat:` / `fix:` / `docs:` / `refactor:`).\n"
        "\n"
        "## Security\n"
        "- Never commit secrets.\n"
        "- `<add project-specific notes>`\n"
    )
    target.write_text(starter, encoding="utf-8")
    print(f"wrote {target}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agents-md", description="AGENTS.md hierarchical loader")
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--per-file-cap", type=int, default=DEFAULT_PER_FILE_CAP)
    parser.add_argument("--total-cap", type=int, default=DEFAULT_TOTAL_CAP)
    parser.add_argument("--quiet", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_collect = sub.add_parser("collect", help="Emit merged AGENTS.md/CLAUDE.md block")
    p_collect.set_defaults(func=cmd_collect)

    p_card = sub.add_parser("card", help="Emit a Harness Card (JSON) describing what was loaded")
    p_card.set_defaults(func=cmd_card)

    p_show = sub.add_parser("show", help="List discovered files with line counts")
    p_show.set_defaults(func=cmd_show)

    p_init = sub.add_parser("init", help="Scaffold a starter AGENTS.md if missing")
    p_init.add_argument("--force", action="store_true")
    p_init.set_defaults(func=cmd_init)

    ns = parser.parse_args(argv)
    return ns.func(ns)


if __name__ == "__main__":
    sys.exit(main())
