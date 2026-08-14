# sync-instruction-code

Sync copy/paste code blocks in one instruction markdown file to match the code in the finished tree. For each numbered step that tells the student to paste, replace the block content with the version from `finished/`. Fenced markers and their indentation are preserved so markdown syntax remains valid.

## The rule that matters

**Finished is the source of truth.** This skill only rewrites blocks inside `instructions/`. It never touches `finished/` or `starter/`. If a block in the instructions doesn't match the finished file, the block gets replaced with what's in the finished file — not the other way around.

## When to use this skill

- You updated a function body in `finished/` and want the instructions to show the new version.
- You spotted a wording drift between the code the student pastes and the code in `finished/` (missing comment, docstring typo, tweaked variable name, etc.).
- Before shipping a milestone, to confirm every "paste this" block in an exercise matches the reference implementation.

## When NOT to use this skill

- You want to change what the student pastes but not touch `finished/`. The direction is always `finished -> instructions`, so change `finished/` first.
- You want to rewrite prose, headings, or explanatory text. This skill only touches the content between `` ``` `` fences.
- You want to fix `starter/` — use the [sync-starter-code skill](/home/jeffko/lab-git/mslearn-azure-ai/.github/skills/sync-starter-code/SKILL.md).
- You want to fix `azdeploy.py` in `starter/` — use the [sync-starter-deploy skill](/home/jeffko/lab-git/mslearn-azure-ai/.github/skills/sync-starter-deploy/SKILL.md).

## What counts as a "paste block"

A fenced code block is checked only when both of these are true:

1. **The enclosing step's prose contains a paste cue.** Any of:
   - `add the following` (covers `add the following code`, `add the following JSON`, etc.)
   - `should look similar` / `should look like`
   - `replace ... with the following`
   - a bold BEGIN reference like `**BEGIN <TAG>**`, `**# BEGIN <TAG>**`, or `**# BEGIN: <TAG>**`
2. **A target file is in scope.** The most recent `Open the *X* file` line (in a numbered step or heading) sets the target, resolved relative to `finished/<topic>/<exercise>/python/`. If the direct path doesn't exist, a single-match basename search across the finished python tree is attempted.

The block's language tag also gates the check:

- Language ∈ `bash`, `sh`, `shell`, `console`, `powershell`, `pwsh`, `azurecli`, `cmd`, `batch`, `plaintext`, `text` → always skipped (shell commands, not paste code).
- Language ∈ `python`, `py`, `yaml`, `yml`, `json`, `html`, `dockerfile`, `sql`, and similar → checked.

Target basenames `azdeploy.py`, `.env`, and `.env.ps1` are always skipped (deployment artifacts, not student paste targets).

## How matching works

- Both the instruction block and the finished region are left-aligned with `textwrap.dedent` before comparison. The student is responsible for pasting with the correct indent, so instruction blocks are always shown flush-left. Relative indentation inside the block is still checked exactly.
- If the step references a BEGIN tag, the block content must appear inside the `# BEGIN <TAG>` / `# END <TAG>` region of the target file. Marker syntax handled: `#` (Python/YAML), `//` (JavaScript/TypeScript), `--` (SQL); with or without a trailing colon; and mixed-case tags with letters, digits, spaces, `_`, `-`, `/`, and `.`.
- Otherwise the block content must appear as a substring of the target file.

## Rewrite behavior

For each mismatched block the skill computes a replacement:

- If a BEGIN tag was referenced, the replacement is the finished region between `# BEGIN <TAG>` and `# END <TAG>`, left-aligned, then re-indented to match the fence's original leading whitespace.
- Otherwise (no BEGIN tag, block was a substring of the target), the block is left alone. Substring-only matches are considered ambiguous and reported as `SKIP: no matching substring in <file>. Ambiguous; review manually.` so you can review and fix by hand.

The fence lines (opening `` ``` ``lang and closing `` ``` ``) are never modified.

## How to run

Always launch from the repo root. Dry-run first, always.

### Preview one instruction file

```
python .github/skills/sync-instruction-code/sync.py instructions/azure-managed-redis/01-amr-data-operations.md
```

You'll see, for every stale block, a unified diff showing what would change plus a summary of how many blocks match, rewrite, or skip.

### Apply the rewrites

```
python .github/skills/sync-instruction-code/sync.py instructions/azure-managed-redis/01-amr-data-operations.md --apply
```

The instruction file is rewritten in place. Only paste blocks are touched; prose, headings, and shell command blocks are left alone.

### Sweep every instruction file quickly

The skill only accepts one file at a time on purpose. To find which files have stale blocks without opening each one, a shell loop calling the skill in dry-run mode works well:

```bash
for f in $(python3 .github/skills/exercise-inventory/inventory.py \
        | python3 -c "import json,sys; d=json.load(sys.stdin); [print(e['instructions_file']) for e in d['exercises']]"); do
    python3 .github/skills/sync-instruction-code/sync.py "$f" \
        | awk -v f="$f" '/Blocks to rewrite from finished:/ {if ($NF+0 > 0) print f, "->", $0}'
done
```

Then run the skill with `--apply` on each file that reports rewrites.

## Reading the output

The skill emits one section per fenced block that isn't a plain match, plus a summary.

- `REWRITE:` — a mismatched block that will be replaced with the finished version. A unified diff follows.
- `SKIP: target file '...' not found under finished/. Left alone.` — the `Open the *X* file` target could not be resolved. Common causes: the file is generated at runtime (e.g. `app-config.yaml`), or the exercise has no finished tree at all (e.g. any exercise where [topic-map.json](/home/jeffko/lab-git/mslearn-azure-ai/.github/skills/exercise-inventory/topic-map.json) sets `starter_slug: null`).
- `SKIP: '# BEGIN <TAG>' not found in <file>. Left alone; fix the finished file or the BEGIN tag in prose.` — the prose referenced a BEGIN tag but the finished file doesn't have that marker. This is a bug in one of the two — either the tag was renamed and the instructions still use the old name, or the finished code lost the markers.
- `SKIP: no matching substring in <file>. Ambiguous; review manually.` — no BEGIN tag was referenced and the block doesn't appear anywhere in the target file. The rewrite is ambiguous; edit by hand.

The summary counts:

- `Blocks already matching finished` — nothing to do.
- `Blocks to rewrite from finished` — number of `REWRITE:` entries above.
- `Blocks skipped (target missing)` / `(BEGIN missing)` / `(not in file)` — the three skip flavors above.

## Recommended workflow

1. Make the change in `finished/` first (or discover a drift you want to fix).
2. Dry-run this skill on the affected instruction file:
   ```
   python .github/skills/sync-instruction-code/sync.py <path-to-instruction-file>
   ```
3. Read every diff carefully. `REWRITE` is destructive — the block is fully replaced with the finished version. If the finished region contains code the instructions don't want to show (a whole function wrapper when the instructions only want the body), fix the BEGIN markers in `finished/` first so the region contains exactly what students should paste.
4. Apply once you're happy with the diffs:
   ```
   python .github/skills/sync-instruction-code/sync.py <path-to-instruction-file> --apply
   ```
5. Re-run the dry-run to confirm no rewrites remain.

## Files in this skill

- [SKILL.md](SKILL.md) — this file.
- [sync.py](sync.py) — the sync driver. Loads the exercise inventory from the [exercise-inventory skill](/home/jeffko/lab-git/mslearn-azure-ai/.github/skills/exercise-inventory/SKILL.md) so it never guesses paths.
