"""Auto-generate the Cron Reference page from the live crontab + each
script's own module docstring.

There's no Scribe-equivalent for "document my crontab" in any language --
this is a project-specific version of the same idea: introspect the actual
running system rather than hand-maintain a table that drifts the moment a
schedule changes (this project has hit that exact drift before -- see
CLAUDE.md's "Cron rule" callout about a per-pair funding cron that was dead
for a week because nothing was watching it). Every entry below is read live
from `crontab -l` at build time, so this page is never more than one
`mkdocs build` behind the truth.

Runs as a `mkdocs-gen-files` plugin, same mechanism as gen_ref_pages.py.
"""
from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import mkdocs_gen_files

ROOT = Path(__file__).resolve().parent.parent

CRON_LINE_RE = re.compile(
    r"^(?P<schedule>(?:\S+\s+){4}\S+)\s+(?P<command>.+)$"
)
# Pull the first thing in the command that looks like a project-relative
# script path (.py or .sh) so we can go find its docstring/header comment.
SCRIPT_RE = re.compile(r"([./\w-]+\.(?:py|sh))")


def _module_docstring(py_path: Path) -> str | None:
    try:
        tree = ast.parse(py_path.read_text(encoding="utf-8", errors="replace"))
        doc = ast.get_docstring(tree)
        if doc:
            # First paragraph only -- keep the reference table skimmable;
            # the full docstring is one click away via the API reference.
            return doc.strip().split("\n\n")[0].replace("\n", " ")
    except Exception:
        pass
    return None


def _shell_script_summary(sh_path: Path) -> str | None:
    """Best-effort: the first contiguous block of leading `#` comment lines
    after the shebang, which is this project's de facto header-comment
    convention for .sh scripts (see walkforward_daily.sh, brain_cleanup.py's
    counterparts, etc.)."""
    lines = sh_path.read_text(encoding="utf-8", errors="replace").splitlines()
    out = []
    started = False
    for line in lines:
        if line.startswith("#!"):
            continue
        if line.startswith("#"):
            started = True
            out.append(line.lstrip("#").strip())
        elif started:
            break
    return " ".join(out) if out else None


def _describe(script_path_str: str) -> str:
    # Resolve relative to ROOT regardless of how the crontab line phrased it
    # (absolute path, `cd ROOT && python3 relative/path`, etc.)
    candidate = Path(script_path_str)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    else:
        try:
            candidate = candidate.relative_to("/").resolve()
            candidate = Path("/") / candidate
        except Exception:
            pass
    if not candidate.exists():
        return "*(script not found on disk -- possibly stale/removed)*"
    if candidate.suffix == ".py":
        doc = _module_docstring(candidate)
    else:
        doc = _shell_script_summary(candidate)
    return doc or "*(no module docstring / header comment found)*"


def _parse_crontab() -> list[dict]:
    try:
        raw = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=True).stdout
    except Exception as e:
        return [{"schedule": "?", "command": f"(crontab -l failed: {e})", "description": "", "script": None}]

    rows = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = CRON_LINE_RE.match(line)
        if not m:
            continue
        command = m.group("command")
        script_match = SCRIPT_RE.search(command)
        script_rel = script_match.group(1) if script_match else None
        desc = _describe(script_rel) if script_rel else ""
        rows.append({
            "schedule": m.group("schedule"),
            "command": command,
            "script": script_rel,
            "description": desc,
        })
    return rows


def main() -> None:
    rows = _parse_crontab()
    lines = [
        "# Cron Reference\n\n",
        "Every entry below is read directly from the server's live `crontab -l` "
        "each time these docs are built -- this page cannot drift from what's "
        "actually scheduled the way a hand-maintained table can. The "
        "description for each row is that script's own module docstring "
        "(Python) or header comment (shell) -- update the script, the "
        "description updates here automatically on the next build.\n\n",
        f"**{len(rows)} scheduled jobs** as of this build.\n\n",
        "| Schedule | Script | What it does |\n",
        "|---|---|---|\n",
    ]
    for r in rows:
        script_label = f"`{r['script']}`" if r["script"] else "*(no script path detected)*"
        desc = r["description"].replace("|", "\\|")
        lines.append(f"| `{r['schedule']}` | {script_label} | {desc} |\n")

    with mkdocs_gen_files.open("operations/cron-reference.md", "w") as f:
        f.writelines(lines)


main()
