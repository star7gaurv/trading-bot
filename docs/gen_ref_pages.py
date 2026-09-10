"""Auto-generate the full API Reference nav from source, at every build.

This is the "Scribe for Python" piece: instead of hand-writing a doc page per
module (which silently goes stale the moment a new script is added, or a
function is renamed), this walks every real source root in the project and
emits one virtual markdown page per Python module, each containing nothing
but a `::: package.module` mkdocstrings directive. mkdocstrings then renders
every class, function, and docstring in that module automatically. Add a new
.py file anywhere under one of the roots below, run `mkdocs build` (or let
the docs-refresh cron do it), and it appears in the reference nav with zero
manual editing — that's the actual fix for "nothing can be left out of the
documentation."

Runs as a `mkdocs-gen-files` plugin (see mkdocs.yml `plugins: gen-files`).
Nav for this generated tree comes from `mkdocs-literate-nav` reading the
SUMMARY.md this script also writes — so the reference section's nav is
ALSO auto-generated, not hand-maintained.
"""
from __future__ import annotations

import sys
from pathlib import Path

import mkdocs_gen_files

# Directories whose bare name shadows a Python standard-library module --
# `import scripts.platform.db` works, but `import platform.db` (which is
# what this generator would otherwise emit once scripts/ is on sys.path)
# silently resolves to the STDLIB platform module instead, since stdlib
# takes priority. This is a real, pre-existing latent-bug risk in the
# codebase itself (any script that does a bare `import platform` while
# scripts/ is on its path gets whichever one sys.path happens to favor),
# not just a docs-generation inconvenience -- worth renaming the directory
# eventually. Checked against sys.stdlib_module_names so any FUTURE
# directory that happens to pick a stdlib name is caught automatically,
# not just this one instance.
STDLIB_SHADOW_NAMES = set(sys.stdlib_module_names)

nav = mkdocs_gen_files.Nav()

# Every real Python source root in the project, and the "package name" each
# should be documented under in the reference tree. Order matters for the
# nav only cosmetically. Add a new root here if a new top-level code area is
# ever introduced — that is the ONLY manual step this generator ever needs.
ROOTS: list[tuple[Path, str]] = [
    (Path("scripts"), "scripts"),
    (Path("dashboard"), "dashboard"),
    (Path("freqtrade/user_data/strategies"), "strategies"),
    (Path("freqtrade/user_data/scripts"), "freqtrade-scripts"),
    (Path("freqtrade/user_data/freqaimodels"), "freqaimodels"),
]

# Directories that are never source of truth for hand-written or generated
# logic — noise to exclude from the reference tree.
SKIP_DIR_NAMES = {"__pycache__", "notebooks", "hyperopts", "diagnostics"}


def _module_dotted_path(py_file: Path, root: Path, package_label: str) -> tuple[str, ...]:
    """Return the nav-path parts for one file, e.g. scripts/brain/runner.py
    under root scripts/ -> ("scripts", "brain", "runner")."""
    rel = py_file.relative_to(root).with_suffix("")
    parts = (package_label, *rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return parts


# Every root gets added to mkdocstrings' shared `paths:` (see mkdocs.yml), so
# a bare top-level name (a flat .py file, or a subpackage directory) that
# exists directly under TWO DIFFERENT roots is genuinely ambiguous to
# Python's import resolution -- whichever root sorts first on sys.path wins
# for BOTH pages, silently rendering one file's docstrings under the other's
# page. This is checked at (root, top-level-name) granularity ONLY: every
# file inside the SAME root's same subpackage (e.g. every scripts/brain/*.py
# under the one "brain" package) legitimately shares that top-level name and
# is fine -- Python resolves brain.analyst vs brain.promote just fine. The
# collision only exists across roots. First-seen-root wins (ROOTS order
# above is the tiebreak, deliberately putting scripts/ -- this project's
# canonical location per its own conventions -- first); later collisions are
# skipped with a visible build-time warning instead of silently
# mis-rendering. Found real instances during the 2026-09-10 docs build:
# scripts/build_historical_regime.py vs a different, apparently stale copy
# at freqtrade/user_data/scripts/build_historical_regime.py, and a whole
# scripts/karpathy/ vs freqtrade/user_data/scripts/karpathy/ pair of
# same-named packages -- worth Gaurav deciding whether either stale copy
# should just be deleted; this generator just makes sure docs never silently
# show the wrong file's content for either.
_root_claims: dict[str, Path] = {}  # top-level name -> the root that owns it

for root, package_label in ROOTS:
    if not root.exists():
        continue
    for py_file in sorted(root.rglob("*.py")):
        if any(part in SKIP_DIR_NAMES for part in py_file.parts):
            continue
        if py_file.name == "__init__.py" and not any(py_file.parent.glob("*.py")):
            continue  # empty package marker, nothing to render

        top_level_module = py_file.relative_to(root).parts[0].removesuffix(".py")
        if top_level_module in STDLIB_SHADOW_NAMES:
            print(f"WARNING: skipping {py_file} -- top-level name "
                  f"'{top_level_module}' shadows a Python stdlib module; "
                  f"cannot be imported as '{top_level_module}.*' while this "
                  f"root is on sys.path. Worth renaming the directory.")
            continue
        claimed_by = _root_claims.get(top_level_module)
        if claimed_by is not None and claimed_by != root:
            print(f"WARNING: skipping duplicate-name module page for {py_file} "
                  f"(top-level name '{top_level_module}' already claimed by root "
                  f"'{claimed_by}' -- same name, ambiguous import path if both "
                  f"roots are on sys.path together)")
            continue
        _root_claims[top_level_module] = root

        parts = _module_dotted_path(py_file, root, package_label)
        doc_path = Path("reference", *parts).with_suffix(".md")
        # Import path mkdocstrings needs to actually import the module. Since
        # these scripts aren't installed as a package, we point mkdocstrings
        # at the ROOT directory (via mkdocs.yml paths:) and use the path
        # relative to that root, dotted. __init__ is not a real import target
        # (import foo.__init__ fails) -- the package itself (foo) is.
        import_parts = py_file.relative_to(root).with_suffix("").parts
        if import_parts[-1] == "__init__":
            import_parts = import_parts[:-1]
        import_path = ".".join(import_parts)

        with mkdocs_gen_files.open(doc_path, "w") as fd:
            title = parts[-1]
            fd.write(f"# `{'/'.join(parts)}`\n\n")
            fd.write(f"::: {import_path}\n")
            fd.write("    options:\n")
            fd.write(f"      show_root_full_path: false\n")

        nav[parts] = doc_path.relative_to("reference").as_posix()
        mkdocs_gen_files.set_edit_path(doc_path, py_file)

with mkdocs_gen_files.open("reference/SUMMARY.md", "w") as nav_file:
    # A hand-written landing page (docs/reference/index.md) explains what
    # this section is; mkdocs-section-index makes the "Reference" tab click
    # straight through to it when it's the section's first nav entry.
    nav_file.write("* [Reference](index.md)\n")
    nav_file.writelines(nav.build_literate_nav())
