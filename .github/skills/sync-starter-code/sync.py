"""Sync starter application code from the finished tree.

For each exercise where both a finished and a starter folder exist, mirror the
application code under ``finished/<topic>/<exercise>/python/`` into
``starter/<starter_topic>/<starter_slug>/python/``. Files that are deployment
artifacts (``azdeploy.py``, ``.env``, ``.env.ps1``, resolved site-container
specifications) or build/venv detritus
(``__pycache__/``, ``.venv/``, ``*.pyc``) are never touched.

For Python files (``*.py``), any code between matching ``# BEGIN <TAG>`` and
``# END <TAG>`` marker lines is replaced with three blank lines so students
have empty space to paste code from the instructions. Marker lines themselves
are preserved verbatim (including their indentation).

Finished is the source of truth. This script never writes to ``finished/``.

Runs in dry-run mode by default. Use ``--apply`` to write changes.
"""
import argparse
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
INVENTORY_SCRIPT = REPO_ROOT / ".github/skills/exercise-inventory/inventory.py"

EXCLUDED_FILE_NAMES = frozenset({
    "azdeploy.py",
    ".env",
    ".env.ps1",
    "sitecontainers-spec.json",
    ".DS_Store",
    "Thumbs.db",
})

EXCLUDED_FILE_SUFFIXES = frozenset({".pyc", ".md", ".markdown"})

EXCLUDED_DIR_NAMES = frozenset({
    "__pycache__",
    ".venv",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
})

BEGIN_RE = re.compile(r"^(?P<indent>[ \t]*)# BEGIN (?P<tag>.+?)\s*$")
END_RE = re.compile(r"^(?P<indent>[ \t]*)# END (?P<tag>.+?)\s*$")

BLANK_BLOCK_LINES = 3


def load_inventory() -> list[dict]:
    result = subprocess.run(
        [sys.executable, str(INVENTORY_SCRIPT)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    return payload["exercises"]


def is_excluded(path: Path, base: Path) -> bool:
    """Return True if ``path`` should be skipped when walking ``base``."""
    rel_parts = path.relative_to(base).parts
    if any(part in EXCLUDED_DIR_NAMES for part in rel_parts[:-1]):
        return True
    name = path.name
    if name in EXCLUDED_FILE_NAMES:
        return True
    if path.suffix.lower() in EXCLUDED_FILE_SUFFIXES:
        return True
    return False


def iter_source_files(base: Path) -> Iterable[Path]:
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        if is_excluded(path, base):
            continue
        yield path


def normalize_python_blocks(text: str, source_hint: str) -> tuple[str, list[str]]:
    """Replace content between ``# BEGIN``/``# END`` markers with blank lines.

    Returns ``(new_text, warnings)``. Marker lines are preserved verbatim.
    Content strictly between a matched pair is replaced with
    ``BLANK_BLOCK_LINES`` blank lines. Unmatched markers cause a warning and
    the affected region is left untouched.
    """
    warnings: list[str] = []
    lines = text.splitlines(keepends=True)
    output: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        begin_match = BEGIN_RE.match(line.rstrip("\r\n"))
        if not begin_match:
            output.append(line)
            i += 1
            continue

        tag = begin_match.group("tag").strip()
        end_index: Optional[int] = None
        for j in range(i + 1, len(lines)):
            end_match = END_RE.match(lines[j].rstrip("\r\n"))
            if end_match and end_match.group("tag").strip() == tag:
                end_index = j
                break
            other_begin = BEGIN_RE.match(lines[j].rstrip("\r\n"))
            if other_begin:
                warnings.append(
                    f"{source_hint}: nested/unclosed '# BEGIN {tag}' before matching '# END'"
                )
                break

        if end_index is None:
            warnings.append(
                f"{source_hint}: no matching '# END {tag}' found; leaving block untouched"
            )
            output.append(line)
            i += 1
            continue

        output.append(line)
        output.extend(["\n"] * BLANK_BLOCK_LINES)
        output.append(lines[end_index])
        i = end_index + 1

    return "".join(output), warnings


def compute_starter_text(finished_file: Path) -> tuple[str, list[str]]:
    raw = finished_file.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1"), []

    if finished_file.suffix == ".py":
        rel = finished_file.relative_to(REPO_ROOT)
        return normalize_python_blocks(text, str(rel))
    return text, []


def sync_file(
    finished_file: Path,
    starter_file: Path,
    apply: bool,
    show_diff: bool,
) -> tuple[str, list[str]]:
    new_text, warnings = compute_starter_text(finished_file)

    if not starter_file.is_file():
        if apply:
            starter_file.parent.mkdir(parents=True, exist_ok=True)
            starter_file.write_text(new_text, encoding="utf-8")
            return "created", warnings
        return "would create", warnings

    existing = starter_file.read_text(encoding="utf-8", errors="replace")
    if existing == new_text:
        return "unchanged", warnings

    if show_diff:
        diff = difflib.unified_diff(
            existing.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=str(starter_file.relative_to(REPO_ROOT)),
            tofile=str(starter_file.relative_to(REPO_ROOT)) + " (updated)",
        )
        sys.stdout.write("".join(diff))

    if apply:
        starter_file.write_text(new_text, encoding="utf-8")
        return "updated", warnings
    return "would update", warnings


def sync_exercise(exercise: dict, apply: bool, show_diff: bool) -> list[str]:
    reports: list[str] = []
    starter_dir = exercise.get("starter_dir")
    if not starter_dir:
        return reports

    finished_python = REPO_ROOT / exercise["finished_dir"] / "python"
    starter_python = REPO_ROOT / starter_dir / "python"

    if not finished_python.is_dir():
        reports.append(f"  skip: {finished_python.relative_to(REPO_ROOT)} does not exist")
        return reports

    finished_rel_set: set[Path] = set()

    for finished_file in iter_source_files(finished_python):
        rel = finished_file.relative_to(finished_python)
        finished_rel_set.add(rel)
        starter_file = starter_python / rel
        status, warnings = sync_file(finished_file, starter_file, apply, show_diff)
        rel_starter = starter_file.relative_to(REPO_ROOT)
        reports.append(f"  {rel_starter}: {status}")
        for warning in warnings:
            reports.append(f"    warning: {warning}")

    if starter_python.is_dir():
        for starter_file in iter_source_files(starter_python):
            rel = starter_file.relative_to(starter_python)
            if rel in finished_rel_set:
                continue
            rel_starter = starter_file.relative_to(REPO_ROOT)
            reports.append(f"  {rel_starter}: extra in starter (not in finished; left alone)")

    return reports


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes. Default is dry-run.",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Print a unified diff for every file that would change.",
    )
    parser.add_argument(
        "--only",
        metavar="EXERCISE_ID",
        help=(
            "Limit to a single exercise id (e.g. 'cosmosdb/build-query'). "
            "By default every exercise with a starter is processed."
        ),
    )
    parser.add_argument(
        "--topic",
        metavar="TOPIC_SLUG",
        help=(
            "Limit to a single topic slug (e.g. 'cosmosdb'). Runs every "
            "exercise under that topic. Mutually exclusive with --only."
        ),
    )
    args = parser.parse_args()

    if args.only and args.topic:
        print("Error: --only and --topic are mutually exclusive.", file=sys.stderr)
        return 1

    exercises = load_inventory()
    if args.only:
        exercises = [ex for ex in exercises if ex["id"] == args.only]
        if not exercises:
            print(f"Error: no exercise with id '{args.only}'", file=sys.stderr)
            return 1
    elif args.topic:
        exercises = [ex for ex in exercises if ex["topic"] == args.topic]
        if not exercises:
            print(f"Error: no exercises under topic '{args.topic}'", file=sys.stderr)
            return 1

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"Mode: {mode}")
    print(f"Repo root: {REPO_ROOT}")
    print()

    counters = {
        "updated": 0,
        "unchanged": 0,
        "created": 0,
        "skipped": 0,
        "extra": 0,
        "warnings": 0,
    }

    for exercise in exercises:
        if not exercise.get("starter_dir"):
            continue
        print(f"{exercise['id']}:")
        reports = sync_exercise(exercise, args.apply, args.diff)
        if not reports:
            print("  (nothing to do)")
            continue
        for line in reports:
            print(line)
            if ": updated" in line or ": would update" in line:
                counters["updated"] += 1
            elif ": unchanged" in line:
                counters["unchanged"] += 1
            elif ": created" in line or ": would create" in line:
                counters["created"] += 1
            elif ": skip" in line:
                counters["skipped"] += 1
            elif ": extra in starter" in line:
                counters["extra"] += 1
            elif "warning:" in line:
                counters["warnings"] += 1

    print()
    print("Summary:")
    print(f"  Files to update/updated: {counters['updated']}")
    print(f"  Files unchanged:         {counters['unchanged']}")
    print(f"  Files to create/created: {counters['created']}")
    print(f"  Files skipped:           {counters['skipped']}")
    print(f"  Extra files in starter:  {counters['extra']}")
    print(f"  Warnings:                {counters['warnings']}")
    if not args.apply:
        print()
        print("Dry-run only. Re-run with --apply to write changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
