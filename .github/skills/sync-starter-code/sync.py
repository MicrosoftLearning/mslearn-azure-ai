"""Build starter files from finished code and student instructions.

Each exercise's registered instruction file determines what students should
receive. Explicit empty-file wording produces an empty starter file, BEGIN/END
steps produce emptied marker regions, and placeholder replacement steps restore
the instructional placeholder. Files students only review or run are copied
from finished. Ambiguous student-edit instructions fail closed.

Files that are deployment artifacts (``azdeploy.py``, ``.env``, ``.env.ps1``,
resolved site-container specifications) or build/venv detritus
(``__pycache__/``, ``.venv/``, ``*.pyc``) are never touched.

The finished implementation supplies source content, while instructions define
student edits. This script never writes to ``finished/`` or ``instructions/``.

Runs in dry-run mode by default. Use ``--apply`` to write changes.
"""
import argparse
import difflib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
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

BEGIN_RE = re.compile(r"^(?P<indent>[ \t]*)# BEGIN(?::|[ \t]+)(?P<tag>.+?)\s*$")
END_RE = re.compile(r"^(?P<indent>[ \t]*)# END(?::|[ \t]+)(?P<tag>.+?)\s*$")
OPEN_FILE_RE = re.compile(
    r"Open (?:the )?(?P<empty>empty )?\*(?P<target>[^*]+?\.[A-Za-z0-9]+)\*",
    re.IGNORECASE,
)
BEGIN_PROSE_RE = re.compile(
    r"\*\*(?:#\s*)?BEGIN:?\s+(?P<tag>[A-Za-z][A-Za-z0-9 _\-/.]+?)\*\*",
    re.IGNORECASE,
)
BOLD_RE = re.compile(r"\*\*(?P<text>[^*\n]+)\*\*")
PLACEHOLDER_RE = re.compile(
    r"\\?<(?P<name>[A-Za-z][A-Za-z0-9_-]*)>"
)
EDIT_CUE_RE = re.compile(
    r"\b(?:add|complete|insert|modify|replace|update)\b",
    re.IGNORECASE,
)
ADD_FOLLOWING_RE = re.compile(r"\badd the following\b", re.IGNORECASE)

BLANK_BLOCK_LINES = 3
MARKER_FILE_SUFFIXES = frozenset({".py", ".yaml", ".yml"})


@dataclass
class InstructionAction:
    target_rel: str
    line_number: int
    explicitly_empty: bool = False
    marker_tags: set[str] = field(default_factory=set)
    placeholder_templates: list[str] = field(default_factory=list)
    edit_cues: list[str] = field(default_factory=list)


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


def resolve_target(finished_root: Path, target_rel: str) -> Optional[Path]:
    direct = finished_root / target_rel
    if direct.is_file() and not is_excluded(direct, finished_root):
        return direct
    basename = Path(target_rel).name
    matches = [
        path
        for path in finished_root.rglob(basename)
        if path.is_file() and not is_excluded(path, finished_root)
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def contextual_placeholder_templates(line: str) -> list[str]:
    templates: list[str] = []
    for match in BOLD_RE.finditer(line):
        text = match.group("text").replace(r"\<", "<")
        placeholders = list(PLACEHOLDER_RE.finditer(text))
        if not placeholders:
            continue
        without_placeholders = PLACEHOLDER_RE.sub("", text)
        if without_placeholders.strip():
            templates.append(text)
    return templates


def analyze_instructions(
    instructions_path: Path,
    finished_root: Path,
) -> dict[str, dict]:
    lines = instructions_path.read_text(encoding="utf-8").splitlines()
    actions: dict[str, InstructionAction] = {}
    current_action: Optional[InstructionAction] = None

    for line_number, line in enumerate(lines, start=1):
        open_match = OPEN_FILE_RE.search(line)
        if open_match:
            target_path = resolve_target(
                finished_root,
                open_match.group("target").strip(),
            )
            if target_path is None:
                current_action = None
                continue
            target_rel = target_path.relative_to(finished_root).as_posix()
            current_action = actions.setdefault(
                target_rel,
                InstructionAction(
                    target_rel=target_rel,
                    line_number=line_number,
                ),
            )
            if open_match.group("empty"):
                current_action.explicitly_empty = True
            if EDIT_CUE_RE.search(line):
                current_action.edit_cues.append(line.strip())
            for template in contextual_placeholder_templates(line):
                if template not in current_action.placeholder_templates:
                    current_action.placeholder_templates.append(template)

        if current_action is None:
            continue

        begin_match = BEGIN_PROSE_RE.search(line)
        if begin_match and EDIT_CUE_RE.search(line):
            tag = re.sub(r"\s+", " ", begin_match.group("tag").strip())
            current_action.marker_tags.add(tag)
            continue

        if (
            line_number - current_action.line_number <= 12
            and re.search(r"\breplace\b", line, re.IGNORECASE)
            and PLACEHOLDER_RE.search(line)
        ):
            current_action.edit_cues.append(line.strip())
            for template in contextual_placeholder_templates(line):
                if template not in current_action.placeholder_templates:
                    current_action.placeholder_templates.append(template)
            continue

        if ADD_FOLLOWING_RE.search(line):
            current_action.edit_cues.append(line.strip())

    policies: dict[str, dict] = {}
    for target_rel, action in actions.items():
        modes = sum((
            action.explicitly_empty,
            bool(action.marker_tags),
            bool(action.placeholder_templates),
        ))
        if modes > 1:
            policies[target_rel] = {
                "mode": "error",
                "message": (
                    f"instructions line {action.line_number} gives conflicting "
                    "empty, marker, or placeholder actions"
                ),
            }
        elif action.explicitly_empty:
            policies[target_rel] = {"mode": "empty"}
        elif action.marker_tags:
            policies[target_rel] = {
                "mode": "strip-markers",
                "tags": sorted(action.marker_tags),
            }
        elif action.placeholder_templates:
            policies[target_rel] = {
                "mode": "template",
                "templates": action.placeholder_templates,
            }
        elif action.edit_cues:
            policies[target_rel] = {
                "mode": "error",
                "message": (
                    f"ambiguous student-edit instruction near line "
                    f"{action.line_number}: {action.edit_cues[0]}"
                ),
            }

    return policies


def normalize_marker_blocks(
    text: str,
    source_hint: str,
    requested_tags: set[str],
) -> tuple[str, list[str]]:
    """Replace content between ``# BEGIN``/``# END`` markers with blank lines.

    Returns ``(new_text, warnings)``. Marker lines are preserved verbatim.
    Content strictly between a matched pair is replaced with
    ``BLANK_BLOCK_LINES`` blank lines. Unmatched markers cause a warning and
    the affected region is left untouched.
    """
    warnings: list[str] = []
    found_tags: set[str] = set()
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
        if tag not in requested_tags:
            output.append(line)
            i += 1
            continue

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
        found_tags.add(tag)
        i = end_index + 1

    missing_tags = requested_tags - found_tags
    if missing_tags:
        missing = ", ".join(sorted(missing_tags))
        raise ValueError(
            f"{source_hint}: instruction marker tag(s) not found: {missing}"
        )

    return "".join(output), warnings


def apply_instruction_templates(text: str, policy: dict, source_hint: str) -> str:
    templates = policy.get("templates")
    if not isinstance(templates, list) or not templates:
        raise ValueError(f"{source_hint}: template action requires templates")
    result = text
    for index, template in enumerate(templates, start=1):
        if not isinstance(template, str):
            raise ValueError(f"{source_hint}: template {index} must be a string")
        matches = list(PLACEHOLDER_RE.finditer(template))
        if len(matches) != 1:
            raise ValueError(
                f"{source_hint}: template {index} must contain exactly one "
                "placeholder"
            )
        placeholder = matches[0]
        prefix = template[:placeholder.start()]
        suffix = template[placeholder.end():]
        pattern = (
            r"(?m)^(?P<indent>[ \t]*)"
            + re.escape(prefix)
            + r"[^ \t/\n]+"
            + re.escape(suffix)
            + r"[ \t]*$"
        )
        replacement = rf"\g<indent>{template}"
        result, count = re.subn(pattern, replacement, result)
        if count != 1:
            raise ValueError(
                f"{source_hint}: instruction template {index} matched {count} "
                "line(s); expected 1"
            )
    return result


def compute_starter_text(
    finished_file: Path,
    policy: dict,
) -> tuple[str, list[str]]:
    raw = finished_file.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    mode = policy.get("mode")
    source_hint = str(finished_file.relative_to(REPO_ROOT))
    if mode == "error":
        raise ValueError(f"{source_hint}: {policy.get('message', 'ambiguous action')}")
    if mode == "copy":
        return text, []
    if mode == "empty":
        return "", []
    if mode == "strip-markers":
        if finished_file.suffix.lower() not in MARKER_FILE_SUFFIXES:
            raise ValueError(
                f"{source_hint}: strip-markers is not supported for "
                f"'{finished_file.suffix}' files"
            )
        tags = policy.get("tags")
        if not isinstance(tags, list) or not all(
            isinstance(tag, str) for tag in tags
        ):
            raise ValueError(
                f"{source_hint}: strip-markers action requires string tags"
            )
        return normalize_marker_blocks(text, source_hint, set(tags))
    if mode == "template":
        return apply_instruction_templates(text, policy, source_hint), []
    raise ValueError(f"{source_hint}: unsupported policy mode {mode!r}")


def sync_file(
    finished_file: Path,
    starter_file: Path,
    policy: dict,
    apply: bool,
    show_diff: bool,
) -> tuple[str, list[str]]:
    new_text, warnings = compute_starter_text(finished_file, policy)

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


def sync_exercise(
    exercise: dict,
    instruction_policies: dict[str, dict],
    apply: bool,
    show_diff: bool,
    target_rel: Optional[Path] = None,
) -> list[str]:
    reports: list[str] = []
    starter_dir = exercise.get("starter_dir")
    if not starter_dir:
        return reports

    finished_python = REPO_ROOT / exercise["finished_dir"] / "python"
    starter_python = REPO_ROOT / starter_dir / "python"

    if not finished_python.is_dir():
        reports.append(f"  skip: {finished_python.relative_to(REPO_ROOT)} does not exist")
        return reports

    if target_rel is not None:
        target_file = finished_python / target_rel
        if not target_file.is_file():
            reports.append(
                f"  error: {target_file.relative_to(REPO_ROOT)} does not exist"
            )
            return reports
        finished_files = [target_file]
    else:
        finished_files = list(iter_source_files(finished_python))

    finished_rel_set: set[Path] = set()

    for finished_file in finished_files:
        rel = finished_file.relative_to(finished_python)
        finished_rel_set.add(rel)
        starter_file = starter_python / rel
        rel_starter = starter_file.relative_to(REPO_ROOT)
        policy = instruction_policies.get(rel.as_posix(), {"mode": "copy"})
        try:
            status, warnings = sync_file(
                finished_file,
                starter_file,
                policy,
                apply,
                show_diff,
            )
        except (re.error, ValueError) as error:
            reports.append(f"  {rel_starter}: error: {error}")
            continue
        reports.append(f"  {rel_starter}: {status}")
        for warning in warnings:
            reports.append(f"    warning: {warning}")

    if target_rel is None and starter_python.is_dir():
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
    parser.add_argument(
        "--file",
        metavar="STARTER_FILE",
        help=(
            "Limit processing to one repository-relative starter file "
            "(e.g. 'starter/aks/configure-aks/python/k8s/deployment.yaml')."
        ),
    )
    args = parser.parse_args()

    selectors = [bool(args.only), bool(args.topic), bool(args.file)]
    if sum(selectors) > 1:
        print(
            "Error: --only, --topic, and --file are mutually exclusive.",
            file=sys.stderr,
        )
        return 1

    exercises = load_inventory()
    target_rel: Optional[Path] = None
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
    elif args.file:
        requested = Path(args.file)
        if requested.is_absolute() or ".." in requested.parts:
            print(
                "Error: --file must be a repository-relative starter path.",
                file=sys.stderr,
            )
            return 1
        matches = []
        for exercise in exercises:
            starter_dir = exercise.get("starter_dir")
            if not starter_dir:
                continue
            starter_python = Path(starter_dir) / "python"
            try:
                rel = requested.relative_to(starter_python)
            except ValueError:
                continue
            matches.append((exercise, rel))
        if len(matches) != 1:
            print(
                f"Error: '{args.file}' does not map to exactly one starter exercise.",
                file=sys.stderr,
            )
            return 1
        exercise, target_rel = matches[0]
        exercises = [exercise]

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
        "errors": 0,
    }

    for exercise in exercises:
        if not exercise.get("starter_dir"):
            continue
        print(f"{exercise['id']}:")
        instructions_path = REPO_ROOT / exercise["instructions_file"]
        finished_root = REPO_ROOT / exercise["finished_dir"] / "python"
        if not instructions_path.is_file():
            print(
                f"  error: registered instructions file "
                f"{instructions_path.relative_to(REPO_ROOT)} does not exist"
            )
            counters["errors"] += 1
            continue
        exercise_policies = analyze_instructions(instructions_path, finished_root)
        reports = sync_exercise(
            exercise,
            exercise_policies,
            args.apply,
            args.diff,
            target_rel,
        )
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
            elif ": error:" in line or line.lstrip().startswith("error:"):
                counters["errors"] += 1
            elif "warning:" in line:
                counters["warnings"] += 1

    print()
    print("Summary:")
    print(f"  Files to update/updated: {counters['updated']}")
    print(f"  Files unchanged:         {counters['unchanged']}")
    print(f"  Files to create/created: {counters['created']}")
    print(f"  Files skipped:           {counters['skipped']}")
    print(f"  Extra files in starter:  {counters['extra']}")
    print(f"  Errors:                  {counters['errors']}")
    print(f"  Warnings:                {counters['warnings']}")
    if not args.apply:
        print()
        print("Dry-run only. Re-run with --apply to write changes.")
    return 1 if counters["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
