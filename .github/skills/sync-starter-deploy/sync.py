"""Sync starter deployment scripts from the finished tree.

For each exercise where both a finished and a starter folder exist, copy the
region below the DON'T-CHANGE divider from finished/<exercise>/python/azdeploy.py
into the matching starter file. The region above the divider (the header block
students edit) is preserved verbatim in the starter file.

Finished is the source of truth. This script never writes to finished/.

Runs in dry-run mode by default. Use --apply to write changes.
"""
import argparse
import difflib
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
INVENTORY_SCRIPT = REPO_ROOT / ".github/skills/exercise-inventory/inventory.py"

DEPLOY_FILENAMES = ("azdeploy.py",)

DIVIDER_LINE = "# DON'T CHANGE ANYTHING BELOW THIS LINE."


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


def split_at_divider(text: str) -> Optional[tuple[str, str]]:
    """Split the file at the DON'T-CHANGE divider.

    Returns (header_including_divider_block, body_below_divider) or None if the
    divider isn't found. The divider block is the three consecutive lines
    (=== / DON'T CHANGE... / ===) that appear together; we split just after the
    trailing === line so the returned header ends with the closing ===.
    """
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.strip() == DIVIDER_LINE:
            # Expect the divider comment to sit between two === comment rules.
            # Split *after* the line immediately following the DON'T CHANGE line
            # (the closing === rule).
            split_index = index + 2
            if split_index > len(lines):
                split_index = len(lines)
            header = "".join(lines[:split_index])
            body = "".join(lines[split_index:])
            return header, body
    return None


def sync_pair(
    finished_file: Path,
    starter_file: Path,
    apply: bool,
    show_diff: bool,
) -> str:
    """Return a short status string describing what happened (or would happen)."""
    if not finished_file.is_file():
        return "skip: finished file missing"

    finished_text = finished_file.read_text(encoding="utf-8")
    finished_split = split_at_divider(finished_text)
    if finished_split is None:
        return "skip: divider missing in finished"
    _, finished_body = finished_split

    if not starter_file.is_file():
        if apply:
            starter_file.parent.mkdir(parents=True, exist_ok=True)
            starter_file.write_text(finished_text, encoding="utf-8")
            return "created: copied entire finished file (starter did not exist)"
        return "would create: entire finished file (starter did not exist)"

    starter_text = starter_file.read_text(encoding="utf-8")
    starter_split = split_at_divider(starter_text)
    if starter_split is None:
        return "skip: divider missing in starter"
    starter_header, starter_body = starter_split

    if starter_body == finished_body:
        return "unchanged"

    new_starter_text = starter_header + finished_body

    if show_diff:
        diff = difflib.unified_diff(
            starter_text.splitlines(keepends=True),
            new_starter_text.splitlines(keepends=True),
            fromfile=str(starter_file.relative_to(REPO_ROOT)),
            tofile=str(starter_file.relative_to(REPO_ROOT)) + " (updated)",
        )
        sys.stdout.write("".join(diff))

    if apply:
        starter_file.write_text(new_starter_text, encoding="utf-8")
        return "updated"
    return "would update"


def sync_exercise(exercise: dict, apply: bool, show_diff: bool) -> list[str]:
    reports: list[str] = []
    starter_dir = exercise.get("starter_dir")
    if not starter_dir:
        reports.append(f"  (no starter dir; skipping exercise)")
        return reports

    finished_python = REPO_ROOT / exercise["finished_dir"] / "python"
    starter_python = REPO_ROOT / starter_dir / "python"

    if not finished_python.is_dir():
        reports.append(f"  skip: {finished_python} does not exist")
        return reports
    if not starter_python.is_dir():
        reports.append(f"  skip: {starter_python} does not exist")
        return reports

    for filename in DEPLOY_FILENAMES:
        finished_file = finished_python / filename
        starter_file = starter_python / filename
        if not finished_file.is_file() and not starter_file.is_file():
            continue
        status = sync_pair(finished_file, starter_file, apply, show_diff)
        rel_starter = starter_file.relative_to(REPO_ROOT)
        reports.append(f"  {rel_starter}: {status}")
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
            "Limit to a single exercise id (e.g. 'postgresql/build-agent'). "
            "By default every exercise with a starter is processed."
        ),
    )
    parser.add_argument(
        "--topic",
        metavar="TOPIC_SLUG",
        help=(
            "Limit to a single topic slug (e.g. 'postgresql'). Runs every "
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

    total_updated = 0
    total_unchanged = 0
    total_skipped = 0
    total_created = 0

    for exercise in exercises:
        print(f"{exercise['id']}:")
        reports = sync_exercise(exercise, args.apply, args.diff)
        for line in reports:
            print(line)
            if ": updated" in line or ": would update" in line:
                total_updated += 1
            elif ": unchanged" in line:
                total_unchanged += 1
            elif ": created" in line or ": would create" in line:
                total_created += 1
            elif ": skip" in line:
                total_skipped += 1

    print()
    print("Summary:")
    print(f"  Files to update/updated: {total_updated}")
    print(f"  Files unchanged:         {total_unchanged}")
    print(f"  Files to create/created: {total_created}")
    print(f"  Files skipped:           {total_skipped}")
    if not args.apply:
        print()
        print("Dry-run only. Re-run with --apply to write changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
