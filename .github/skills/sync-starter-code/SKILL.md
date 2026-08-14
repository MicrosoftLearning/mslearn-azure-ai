# sync-starter-code

Sync application code files under `starter/**/python/` from the matching `finished/**/python/` tree for every exercise, keeping the two side by side. Python files with `# BEGIN <TAG>` / `# END <TAG>` markers get the code between the markers stripped so students have empty space to paste code from the instructions.

## The two rules that matter

1. **Finished is the source of truth.** Every non-deployment source file under `finished/<topic>/<exercise>/python/` is copied to the matching path under `starter/<starter_topic>/<starter_slug>/python/`. This skill never writes to `finished/`.
2. **`# BEGIN` / `# END` blocks are emptied in the starter.** For every matching pair of marker lines in a `.py` file, the content strictly between them is replaced with three blank lines. Marker lines themselves are preserved verbatim (including indentation).

Deployment scripts (`azdeploy.py`) and generated env files (`.env`, `.env.ps1`) are always excluded — those belong to the [sync-starter-deploy skill](/home/jeffko/lab-git/mslearn-azure-ai/.github/skills/sync-starter-deploy/SKILL.md) and the deployment script, respectively.

## Files that are synced

Every file under `finished/<topic>/<exercise>/python/` is a sync candidate. Common examples: `client/app.py`, `client/<topic>_functions.py`, `client/requirements.txt`, `client/templates/index.html`, `client/static/css/style.css`, `client/sample_*.json`, `api/main.py`, `api/Dockerfile`, `agent-backend/agent_tools.py`, `k8s/*.yaml`, and so on.

## Files that are excluded

Never copied, and never touched in the starter tree if they already exist there:

- **Deployment / generated env files:** `azdeploy.py`, `.env`, `.env.ps1`
- **Markdown docs:** any `*.md` or `*.markdown` file (readmes stay owned by the finished tree)
- **Build/venv detritus:** anything under `__pycache__/`, `.venv/`, `.git/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, and any `*.pyc`
- **OS junk:** `.DS_Store`, `Thumbs.db`

## `# BEGIN` / `# END` handling for Python files

Only `.py` files are transformed. In the finished tree, student code sits between marker lines like:

```
# BEGIN STORE DOCUMENT CHUNK FUNCTION
def store_document_chunk(...):
    ...
# END STORE DOCUMENT CHUNK FUNCTION
```

In the starter tree that becomes:

```
# BEGIN STORE DOCUMENT CHUNK FUNCTION



# END STORE DOCUMENT CHUNK FUNCTION
```

Rules:

- Marker lines are preserved verbatim, including any leading indentation.
- Tags must match exactly (e.g. `# BEGIN X` pairs with `# END X`). Whitespace on either side of the tag is ignored.
- Exactly three blank lines sit between the `# BEGIN` line and its `# END` line.
- If a `# BEGIN` has no matching `# END` (or another `# BEGIN` appears before the expected `# END`), the block is left untouched and a warning is emitted so you can fix the finished file.
- Content outside of `# BEGIN` / `# END` blocks (helpers, imports, blank-line separators, module docstrings) is copied verbatim from finished. Whatever spacing exists between blocks in finished is what ends up in starter.

Non-Python files are copied byte-for-byte from finished, no marker processing.

## Starter-only files

Files that exist in the starter tree but not in the finished tree are reported as `extra in starter (not in finished; left alone)`. This skill never deletes anything from the starter tree. If a stale starter file needs to go, remove it by hand.

## When to use this skill

- You updated the reference implementation of an exercise in `finished/` and want the starter code to catch up.
- You added a new file (template, JSON fixture, k8s manifest, etc.) to `finished/` and need it mirrored into `starter/`.
- You edited or added a `# BEGIN` / `# END` block in a finished Python file and want the starter to have a matching empty block.
- Before shipping a milestone, to confirm every starter file matches finished (with blocks emptied).

## When NOT to use this skill

- Anything under `finished/**/python/azdeploy.py` — use the [sync-starter-deploy skill](/home/jeffko/lab-git/mslearn-azure-ai/.github/skills/sync-starter-deploy/SKILL.md).
- Authoring a brand-new exercise from scratch. Build it in `finished/` first (with the [azdeploy-scripts](/home/jeffko/lab-git/mslearn-azure-ai/.github/skills/azdeploy-scripts/SKILL.md) conventions for the deploy script), add it to [topic-map.json](/home/jeffko/lab-git/mslearn-azure-ai/.github/skills/exercise-inventory/topic-map.json), then run this skill to seed the starter tree.
- Changes that should originate in the starter tree. The direction is always `finished -> starter`.

## How to run

Always launch from the repo root. Dry-run first, always.

### Update everything

```
python .github/skills/sync-starter-code/sync.py
```

### Update every exercise under one topic

Topic slugs match the top-level folder under `finished/`. Full list lives in [topic-map.json](/home/jeffko/lab-git/mslearn-azure-ai/.github/skills/exercise-inventory/topic-map.json).

```
python .github/skills/sync-starter-code/sync.py --topic cosmosdb
```

### Update one exercise

Exercise ids are `<topic>/<exercise>`. See the [exercise-inventory skill](/home/jeffko/lab-git/mslearn-azure-ai/.github/skills/exercise-inventory/SKILL.md) for the full list.

```
python .github/skills/sync-starter-code/sync.py --only cosmosdb/build-query
```

`--only` and `--topic` are mutually exclusive.

### Preview exactly what would change

```
python .github/skills/sync-starter-code/sync.py --topic cosmosdb --diff
```

Prints a unified diff for every file that would change. Works with or without `--apply`.

### Actually write changes

Add `--apply` to any of the above. Without it, the script is dry-run only and reports `would update`, `would create`, or `unchanged`.

```
python .github/skills/sync-starter-code/sync.py --topic cosmosdb --apply
```

## Exact behavior per file

For each file under a synced exercise:

| finished file | starter file | Action |
|---|---|---|
| present, no markers | matches expected content | `unchanged` |
| present, no markers | differs from expected | Replace starter file with finished contents. Result reported as `updated`. |
| present, no markers | missing | Copy finished file to starter. Result reported as `created`. |
| present, `.py` with matched `# BEGIN`/`# END` blocks | matches emptied version | `unchanged` |
| present, `.py` with matched `# BEGIN`/`# END` blocks | differs | Rewrite starter with finished contents, with each block's body replaced by three blank lines. |
| present, `.py` with an unmatched `# BEGIN` (no `# END`) | any | Warning printed; that block is left untouched. Other blocks in the file still get emptied. |
| excluded (`azdeploy.py`, `.env`, `.env.ps1`, `*.md`, `*.pyc`, anything under `__pycache__/` or `.venv/`) | any | Ignored. Never read, never written. |
| missing | present | Reported as `extra in starter (not in finished; left alone)`. Not deleted. |

Exercises where [topic-map.json](/home/jeffko/lab-git/mslearn-azure-ai/.github/skills/exercise-inventory/topic-map.json) sets `starter_slug: null` (e.g. `integrate-services/azure-functions`) are silently skipped.

## Recommended workflow

1. Make your edits in `finished/` and verify the reference implementation still runs.
2. Dry-run this skill against the smallest scope you can:
   ```
   python .github/skills/sync-starter-code/sync.py --only <topic>/<exercise> --diff
   ```
3. Confirm the diff only shows changes you meant, and that every `# BEGIN` / `# END` block in the diff is emptied out with three blank lines between the markers.
4. Apply:
   ```
   python .github/skills/sync-starter-code/sync.py --only <topic>/<exercise> --apply
   ```
5. If you also touched the deployment script, run the [sync-starter-deploy skill](/home/jeffko/lab-git/mslearn-azure-ai/.github/skills/sync-starter-deploy/SKILL.md) too.
6. Widen scope (`--topic <topic>`, then no scope) once you're confident.

## Files in this skill

- [SKILL.md](SKILL.md) — this file.
- [sync.py](sync.py) — the sync driver. Loads the exercise inventory from the [exercise-inventory skill](/home/jeffko/lab-git/mslearn-azure-ai/.github/skills/exercise-inventory/SKILL.md) so it never guesses paths.
