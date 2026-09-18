# `agents-md`

Hierarchical loader for `AGENTS.md` and `CLAUDE.md`, with the
`CLAUDE.md → @AGENTS.md` bridge and a Harness Card (JSON) describing
what was loaded.

Backs the AGENTS.md ingest gap identified in the
`coding-agent-harnesses-trends` research. AGENTS.md is foundation-
stewarded under AAIF (since December 9, 2025) and parsed natively by
9 of the 10 most-deployed coding agents. Claude Code bridges via
`@AGENTS.md` or a symlink — this loader follows that pattern.

## Usage

```bash
./agents-md card   --cwd /path/to/repo   # JSON Harness Card
./agents-md show   --cwd /path/to/repo   # file list with line counts
./agents-md collect --cwd /path/to/repo  # merged instruction block
./agents-md init   --cwd /path/to/repo   # scaffold a starter AGENTS.md
```

## Precedence

Files are walked from `cwd` to `/`. The deepest (closest to the edited
path) file wins on conflict. Output order in `collect` is deepest
first, so the most specific instructions appear at the top of the
merged block.

## CLAUDE.md bridge

If a `CLAUDE.md` contains `@AGENTS.md`, the loader expands the
reference inline:

```markdown
# CLAUDE.md (before)
Importing: @AGENTS.md

# CLAUDE.md (after bridge expansion)
Importing: <!-- @AGENTS.md → /path/to/AGENTS.md -->
<contents of AGENTS.md>
<!-- end @AGENTS.md -->
```

The card reports which AGENTS.md files were expanded via the bridge
so the harness can show the user what was loaded.

## Harness Card

```json
{
  "cwd": "/home/tom/Work",
  "loaded": [
    {
      "lines": 45,
      "name": "AGENTS.md",
      "path": "/home/tom/Work/AGENTS.md",
      "truncated": false
    }
  ],
  "bridge_expansions": [],
  "total_lines": 45,
  "truncated": false
}
```

Empty workspaces include `next_steps` suggesting `mcode init` or
`agents-md init`. The card is the recommended surface for a harness's
`/harness` or `/status` command — it answers "what scaffolding am I
running under?" in one stable JSON shape.

## Caps

`--per-file-cap` (default 500) and `--total-cap` (default 2000) bound
output length. Files over the per-file cap are truncated and the
loader reports `truncated: true` in both the card and the merged
block's section header.

## Exit codes

- `0` on success (files found and emitted)
- `1` on empty workspace (`collect` writes nothing; `card` writes a
  card with `next_steps`)
