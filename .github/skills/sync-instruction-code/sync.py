"""Sync copy/paste code blocks in a single instruction file from the finished tree.

Walk one instruction markdown file, and for every fenced code block that a
numbered step tells the student to paste, verify that the block content
matches the corresponding file under ``finished/<topic>/<exercise>/python/``.
If a block is out of sync, replace the block content with the version from
the finished file. The fenced markers and their indentation are preserved so
markdown syntax remains valid.

Finished is the source of truth. Neither this script nor its output ever
writes to files under ``finished/`` or ``starter/``.

A block is a paste candidate when its enclosing numbered step's prose
contains one of:

- ``add the following`` (covers ``add the following code``, ``add the
  following JSON``, and so on)
- ``should look similar`` / ``should look like``
- ``replace ... with the following``
- a bold BEGIN reference like ``**BEGIN <TAG>**``, ``**# BEGIN <TAG>**``,
  or ``**# BEGIN: <TAG>**``

Blocks whose language is shell / CLI (``bash``, ``powershell``,
``azurecli``, ``sh``, ``cmd``, ``console``, ``text``) are always skipped.

Matching rules:

- The block content and the finished region are both left-aligned with
  ``textwrap.dedent`` before comparison. The student is responsible for
  adding leading indent when they paste, so the shown code is always flush
  left.
- If the enclosing step references a BEGIN tag, the block content must
  appear inside the ``# BEGIN <TAG>`` / ``# END <TAG>`` region in the
  target file (Python and YAML markers both supported, with or without
  colons).
- Otherwise, the block content must appear as a substring of the target
  file.
- When rewriting, the block is replaced with the finished BEGIN region (if
  a tag was specified) or with the exact matching substring located in the
  target file. Fence indentation is preserved.

Runs on one instruction file per invocation. Dry-run by default; pass
``--apply`` to write changes back to the instruction file.
"""
import argparse
import difflib
import json
import re
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
INVENTORY_SCRIPT = REPO_ROOT / ".github/skills/exercise-inventory/inventory.py"

OPEN_FILE_RE = re.compile(r"Open (?:the )?\*(?P<target>[^*]+?\.[A-Za-z0-9]+)\*")
BEGIN_PROSE_RE = re.compile(
    r"\*\*(?:#\s*)?BEGIN:?\s+(?P<tag>[A-Za-z][A-Za-z0-9 _\-/.]+?)\*\*"
)
FENCE_OPEN_RE = re.compile(r"^(?P<indent>[ \t]*)```(?P<lang>[A-Za-z0-9_-]*)\s*$")
FENCE_CLOSE_RE = re.compile(r"^(?P<indent>[ \t]*)```\s*$")
STEP_START_RE = re.compile(r"^\s*\d+\.\s")
HEADING_RE = re.compile(r"^#{1,6}\s")

SHELL_LANGS = frozenset({
    "bash", "sh", "shell", "console", "powershell", "pwsh",
    "azurecli", "azurecli-interactive", "cmd", "batch", "plaintext", "text",
})

SKIP_TARGET_BASENAMES = frozenset({"azdeploy.py", ".env", ".env.ps1"})

PASTE_CUE_PATTERNS = (
    re.compile(r"add the following", re.IGNORECASE),
    re.compile(r"should look similar", re.IGNORECASE),
    re.compile(r"should look like", re.IGNORECASE),
    re.compile(r"replace .*with the following", re.IGNORECASE),
)


@dataclass
class BlockFinding:
    fence_open_index: int
    fence_close_index: int
    fence_indent: str
    language: str
    tag: Optional[str]
    target_rel: str
    original_block: str
    replacement_block: Optional[str]
    status: str  # "match" | "rewrite" | "no-target" | "no-begin-region" | "no-substring"


def load_inventory() -> list[dict]:
    result = subprocess.run(
        [sys.executable, str(INVENTORY_SCRIPT)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)["exercises"]


def exercise_for_instructions(instructions_rel: str, exercises: list[dict]) -> Optional[dict]:
    for exercise in exercises:
        if exercise["instructions_file"] == instructions_rel:
            return exercise
    return None


def strip_base_indent(content_lines: list[str], indent_len: int) -> str:
    out: list[str] = []
    for line in content_lines:
        if not line.strip():
            out.append("")
            continue
        prefix = line[:indent_len]
        if prefix.strip() == "":
            out.append(line[indent_len:])
        else:
            out.append(line)
    return "\n".join(out)


def left_align(text: str) -> str:
    trimmed = "\n".join(line.rstrip() for line in text.splitlines())
    return textwrap.dedent(trimmed).strip("\n")


def find_begin_region(source: str, tag: str) -> Optional[str]:
    lines = source.splitlines(keepends=True)
    begin_re = re.compile(rf"^\s*(?:#|//|--)\s*BEGIN:?\s+{re.escape(tag)}\s*$")
    end_re = re.compile(rf"^\s*(?:#|//|--)\s*END:?\s+{re.escape(tag)}\s*$")
    start = None
    for index, line in enumerate(lines):
        if begin_re.match(line.rstrip("\n")):
            start = index
            break
    if start is None:
        return None
    for index in range(start + 1, len(lines)):
        if end_re.match(lines[index].rstrip("\n")):
            return "".join(lines[start + 1:index])
    return None


def resolve_target(finished_root: Path, target_rel: str) -> Optional[Path]:
    direct = finished_root / target_rel
    if direct.is_file():
        return direct
    basename = Path(target_rel).name
    matches = [
        p for p in finished_root.rglob(basename)
        if p.is_file() and not any(
            part in {"__pycache__", ".venv"}
            for part in p.relative_to(finished_root).parts
        )
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def has_paste_cue(prose: str) -> bool:
    if BEGIN_PROSE_RE.search(prose):
        return True
    return any(p.search(prose) for p in PASTE_CUE_PATTERNS)


def collect_block(
    lines: list[str], fence_line_index: int, indent_len: int
) -> tuple[list[str], int]:
    content: list[str] = []
    for j in range(fence_line_index + 1, len(lines)):
        close = FENCE_CLOSE_RE.match(lines[j])
        if close and len(close.group("indent")) == indent_len:
            return content, j
        content.append(lines[j])
    return content, len(lines) - 1


def choose_replacement(
    target_text: str, tag: Optional[str], block_left_aligned: str
) -> Optional[str]:
    if tag:
        region = find_begin_region(target_text, tag)
        if region is None:
            return None
        return left_align(region)

    target_left = left_align(target_text)
    if block_left_aligned in target_left:
        return block_left_aligned
    return None


def region_matches(
    target_text: str, tag: Optional[str], block_left_aligned: str
) -> bool:
    if tag:
        region = find_begin_region(target_text, tag)
        if region is None:
            return False
        return block_left_aligned in left_align(region)
    target_left = left_align(target_text)
    return block_left_aligned in target_left


def indent_block(block_left_aligned: str, indent: str) -> str:
    lines = block_left_aligned.split("\n")
    out = []
    for line in lines:
        if line == "":
            out.append("")
        else:
            out.append(indent + line)
    return "\n".join(out)


def analyze_file(
    instructions_path: Path, finished_root: Path
) -> tuple[list[BlockFinding], list[str]]:
    text = instructions_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    findings: list[BlockFinding] = []

    current_target_rel: Optional[str] = None
    step_start = 0

    i = 0
    while i < len(lines):
        line = lines[i]

        if STEP_START_RE.match(line) or HEADING_RE.match(line):
            step_start = i
            open_match = OPEN_FILE_RE.search(line)
            if open_match:
                current_target_rel = open_match.group("target").strip()

        fence = FENCE_OPEN_RE.match(line)
        if not fence:
            i += 1
            continue

        indent = fence.group("indent")
        indent_len = len(indent)
        language = (fence.group("lang") or "").lower()
        fence_open_index = i
        content_lines, close_index = collect_block(lines, i, indent_len)
        i = close_index + 1

        step_prose = "\n".join(lines[step_start:fence_open_index])

        if language in SHELL_LANGS:
            continue
        if not has_paste_cue(step_prose):
            continue
        if current_target_rel is None:
            continue

        target_basename = Path(current_target_rel).name
        if target_basename in SKIP_TARGET_BASENAMES:
            continue

        target_path = resolve_target(finished_root, current_target_rel)
        if target_path is None:
            findings.append(BlockFinding(
                fence_open_index=fence_open_index,
                fence_close_index=close_index,
                fence_indent=indent,
                language=language,
                tag=None,
                target_rel=current_target_rel,
                original_block="\n".join(content_lines),
                replacement_block=None,
                status="no-target",
            ))
            continue

        original_block = "\n".join(content_lines)
        block_content = strip_base_indent(content_lines, indent_len)
        block_left = left_align(block_content)
        if not block_left.strip():
            continue

        tag_match = BEGIN_PROSE_RE.search(step_prose)
        tag = None
        if tag_match:
            tag = re.sub(r"\s+", " ", tag_match.group("tag").strip())

        target_text = target_path.read_text(encoding="utf-8")
        target_rel = str(target_path.relative_to(REPO_ROOT))

        if region_matches(target_text, tag, block_left):
            findings.append(BlockFinding(
                fence_open_index=fence_open_index,
                fence_close_index=close_index,
                fence_indent=indent,
                language=language,
                tag=tag,
                target_rel=target_rel,
                original_block=original_block,
                replacement_block=None,
                status="match",
            ))
            continue

        replacement_left = choose_replacement(target_text, tag, block_left)
        if replacement_left is None:
            findings.append(BlockFinding(
                fence_open_index=fence_open_index,
                fence_close_index=close_index,
                fence_indent=indent,
                language=language,
                tag=tag,
                target_rel=target_rel,
                original_block=original_block,
                replacement_block=None,
                status="no-begin-region" if tag else "no-substring",
            ))
            continue

        replacement_indented = indent_block(replacement_left, indent)
        findings.append(BlockFinding(
            fence_open_index=fence_open_index,
            fence_close_index=close_index,
            fence_indent=indent,
            language=language,
            tag=tag,
            target_rel=target_rel,
            original_block=original_block,
            replacement_block=replacement_indented,
            status="rewrite",
        ))

    return findings, lines


def apply_findings(lines: list[str], findings: list[BlockFinding]) -> list[str]:
    result = list(lines)
    rewrites = [f for f in findings if f.status == "rewrite"]
    for finding in sorted(rewrites, key=lambda f: f.fence_open_index, reverse=True):
        new_content_lines = finding.replacement_block.split("\n")
        result[finding.fence_open_index + 1:finding.fence_close_index] = new_content_lines
    return result


def print_diff(original: str, updated: str, label: str) -> None:
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        updated.splitlines(keepends=True),
        fromfile=f"{label} (current)",
        tofile=f"{label} (finished)",
    )
    sys.stdout.write("".join(diff))
    if not original.endswith("\n"):
        sys.stdout.write("\n")


def print_summary(findings: list[BlockFinding]) -> None:
    counters = {"match": 0, "rewrite": 0, "no-target": 0,
                "no-begin-region": 0, "no-substring": 0}
    for f in findings:
        counters[f.status] += 1
    print()
    print("Summary:")
    print(f"  Blocks already matching finished: {counters['match']}")
    print(f"  Blocks to rewrite from finished:  {counters['rewrite']}")
    print(f"  Blocks skipped (target missing):  {counters['no-target']}")
    print(f"  Blocks skipped (BEGIN missing):   {counters['no-begin-region']}")
    print(f"  Blocks skipped (not in file):     {counters['no-substring']}")


def print_findings(findings: list[BlockFinding], instructions_rel: str) -> None:
    for f in findings:
        line_num = f.fence_open_index + 1
        label = f"{instructions_rel}:{line_num}"
        if f.status == "match":
            continue
        if f.status == "rewrite":
            print(f"\n--- REWRITE: {label} -> {f.target_rel}"
                  + (f" (# BEGIN {f.tag})" if f.tag else ""))
            print_diff(f.original_block + "\n", f.replacement_block + "\n", label)
            continue
        if f.status == "no-target":
            print(f"\n--- SKIP: {label} -> target file '{f.target_rel}' "
                  f"not found under finished/. Left alone.")
            continue
        if f.status == "no-begin-region":
            print(f"\n--- SKIP: {label} -> '# BEGIN {f.tag}' not found in "
                  f"{f.target_rel}. Left alone; fix the finished file or the "
                  f"BEGIN tag in prose.")
            continue
        if f.status == "no-substring":
            print(f"\n--- SKIP: {label} -> no matching substring in "
                  f"{f.target_rel}. Ambiguous; review manually.")
            print(f"    Block starts: {f.original_block.splitlines()[0][:80] if f.original_block else ''!r}")
            continue


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "instructions_file",
        help=(
            "Path (repo-relative or absolute) to a single instruction file "
            "under instructions/. Example: "
            "instructions/azure-database-postgresql/01-build-agent-tool-backend.md"
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the rewrites back to the instruction file. Default is dry-run.",
    )
    args = parser.parse_args()

    instructions_path = Path(args.instructions_file)
    if not instructions_path.is_absolute():
        instructions_path = REPO_ROOT / instructions_path
    instructions_path = instructions_path.resolve()

    try:
        instructions_rel = str(instructions_path.relative_to(REPO_ROOT))
    except ValueError:
        print(f"Error: {instructions_path} is outside the repo.", file=sys.stderr)
        return 1

    if not instructions_path.is_file():
        print(f"Error: {instructions_rel} does not exist.", file=sys.stderr)
        return 1

    exercises = load_inventory()
    exercise = exercise_for_instructions(instructions_rel, exercises)
    if exercise is None:
        print(
            f"Error: {instructions_rel} is not registered in "
            f".github/skills/exercise-inventory/topic-map.json.",
            file=sys.stderr,
        )
        return 1

    finished_root = REPO_ROOT / exercise["finished_dir"] / "python"
    if not finished_root.is_dir():
        print(
            f"Error: finished tree {finished_root.relative_to(REPO_ROOT)} "
            f"does not exist. Nothing to compare against.",
            file=sys.stderr,
        )
        return 1

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"Mode: {mode}")
    print(f"Instructions: {instructions_rel}")
    print(f"Finished tree: {finished_root.relative_to(REPO_ROOT)}")

    findings, lines = analyze_file(instructions_path, finished_root)
    print_findings(findings, instructions_rel)
    print_summary(findings)

    rewrites = [f for f in findings if f.status == "rewrite"]
    if not rewrites:
        return 0

    if not args.apply:
        print()
        print(f"Dry-run only. Re-run with --apply to write {len(rewrites)} rewrite(s).")
        return 0

    updated_lines = apply_findings(lines, findings)
    original_text = instructions_path.read_text(encoding="utf-8")
    trailing_newline = "\n" if original_text.endswith("\n") else ""
    instructions_path.write_text("\n".join(updated_lines) + trailing_newline, encoding="utf-8")
    print()
    print(f"Wrote {len(rewrites)} rewrite(s) to {instructions_rel}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
