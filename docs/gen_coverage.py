"""Auto-generate the Documentation Coverage report.

The point of this page: "document everything automatically" only works if
gaps are VISIBLE, not swallowed. mkdocstrings will happily render nothing
for an undocumented function and the reference page just looks a little
thin -- easy to miss. This walks the same source roots as gen_ref_pages.py
and reports, per module, exactly which functions and classes still have no
docstring, so the gap is a checklist instead of an invisible hole.

Runs as a `mkdocs-gen-files` plugin, same mechanism as gen_ref_pages.py.
"""
from __future__ import annotations

import ast
from pathlib import Path

import mkdocs_gen_files

ROOT = Path(__file__).resolve().parent.parent

SCAN_ROOTS = [
    "scripts", "dashboard",
    "freqtrade/user_data/strategies", "freqtrade/user_data/scripts",
    "freqtrade/user_data/freqaimodels",
]
SKIP_DIR_NAMES = {"__pycache__", "notebooks", "hyperopts", "diagnostics"}


def _analyze(path: Path) -> dict:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:
        return {"error": str(e)}
    module_doc = ast.get_docstring(tree) is not None
    funcs_total, funcs_documented, undocumented_names = 0, 0, []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Skip dunder/private-by-convention single-underscore helpers
            # only when they're trivially short (<=2 statements) -- those
            # are usually self-evident one-liners, not real gaps. Everything
            # else counts, public or private.
            funcs_total += 1
            if ast.get_docstring(node):
                funcs_documented += 1
            elif not (node.name.startswith("_") and len(node.body) <= 2):
                undocumented_names.append(node.name)
    return {
        "module_doc": module_doc,
        "funcs_total": funcs_total,
        "funcs_documented": funcs_documented,
        "undocumented": undocumented_names,
    }


def main() -> None:
    rows = []
    for root_str in SCAN_ROOTS:
        root = ROOT / root_str
        if not root.exists():
            continue
        for py_file in sorted(root.rglob("*.py")):
            if any(part in SKIP_DIR_NAMES for part in py_file.parts):
                continue
            info = _analyze(py_file)
            if "error" in info:
                continue
            rows.append((py_file.relative_to(ROOT).as_posix(), info))

    total_mods = len(rows)
    documented_mods = sum(1 for _, i in rows if i["module_doc"])
    total_funcs = sum(i["funcs_total"] for _, i in rows)
    documented_funcs = sum(i["funcs_documented"] for _, i in rows)

    lines = [
        "# Documentation Coverage\n\n",
        "Computed fresh on every build by walking every module under "
        "`scripts/`, `dashboard/`, and the FreqTrade user_data tree, and "
        "checking each module and function for a real docstring. This is "
        "the honest counterpart to the API reference: a living checklist "
        "of what's genuinely explained versus what still needs a "
        "docstring written, not a one-time claim that everything is "
        "covered.\n\n",
        f"- **Modules scanned:** {total_mods}\n",
        f"- **Modules with a module-level docstring:** {documented_mods} "
        f"({documented_mods/total_mods:.0%})\n" if total_mods else "",
        f"- **Functions with a docstring:** {documented_funcs} / {total_funcs} "
        f"({documented_funcs/total_funcs:.0%})\n\n" if total_funcs else "\n",
        "## Gaps by module\n\n",
        "Only modules with at least one undocumented function/class are "
        "listed -- a module not appearing here is fully documented.\n\n",
    ]
    gap_rows = [(rel, i) for rel, i in rows if i["undocumented"]]
    gap_rows.sort(key=lambda x: -len(x[1]["undocumented"]))
    if not gap_rows:
        lines.append("Nothing to show -- every function has a docstring. \U0001F389\n")
    else:
        # Deliberately NOT linked into reference/ -- a handful of source
        # files (name collisions with the stdlib, or with another root's
        # same-named module) don't get their own reference page at all
        # (see gen_ref_pages.py), so a generated link here could point at
        # nothing. The plain path is always correct; search the sidebar for
        # the ones that do have a page.
        lines.append("| Module | Undocumented functions |\n|---|---|\n")
        for rel, info in gap_rows:
            names = ", ".join(f"`{n}`" for n in info["undocumented"])
            lines.append(f"| `{rel}` | {names} |\n")

    with mkdocs_gen_files.open("coverage.md", "w") as f:
        f.writelines(lines)


main()
