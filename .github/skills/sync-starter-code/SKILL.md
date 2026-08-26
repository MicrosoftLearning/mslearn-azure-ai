# sync-starter-code

Build explicitly classified files under `starter/**/python/` from the matching `finished/**/python/` tree. The finished implementation supplies source content, while `policies.json` defines the state students should receive.

## The rules that matter

1. **Every writable starter file needs an explicit policy.** Unclassified files are reported and left untouched. There is no default copy behavior.
2. **Finished supplies implementation content; policy supplies student intent.** A policy can copy a completed file, create an empty file, empty marker blocks, create a placeholder-bearing template, or ignore the file.
3. **The process fails closed.** A malformed policy, a template replacement with an unexpected match count, or an invalid target produces an error and no write for that file.
4. **This skill never writes to `finished/`.**

Deployment scripts (`azdeploy.py`) and generated files (`.env`, `.env.ps1`, `sitecontainers-spec.json`) are always excluded — those belong to the [sync-starter-deploy skill](/home/jeffko/lab-git/mslearn-azure-ai/.github/skills/sync-starter-deploy/SKILL.md) and the deployment script, respectively. A source template such as `sitecontainers-spec.template.json` remains a normal sync candidate.

## File policies

Policies live in `policies.json`, keyed first by exercise id and then by the path relative to the exercise's `python/` folder.

- **`copy`** — copy the finished file verbatim.
- **`empty`** — create a zero-byte starter file because the student supplies the entire contents.
- **`strip-markers`** — copy finished and replace every matched `# BEGIN` / `# END` body with three blank lines.
- **`template`** — copy finished and apply explicitly configured regular-expression replacements. Every replacement declares its expected match count.
- **`ignore`** — report the file as ignored and never modify it.

Example:

```
{
  "exercises": {
    "aks/configure-aks": {
      "k8s/deployment.yaml": {
        "mode": "template",
        "replacements": [
          {
            "pattern": "...",
            "replacement": "...",
            "expected_matches": 1
          }
        ]
      }
    }
  }
}
```

## Files that are excluded

Never copied, and never touched in the starter tree if they already exist there:

- **Deployment / generated files:** `azdeploy.py`, `.env`, `.env.ps1`, `sitecontainers-spec.json`
- **Markdown docs:** any `*.md` or `*.markdown` file (readmes stay owned by the finished tree)
- **Build/venv detritus:** anything under `__pycache__/`, `.venv/`, `.git/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, and any `*.pyc`
- **OS junk:** `.DS_Store`, `Thumbs.db`

## `# BEGIN` / `# END` handling for `strip-markers` policies

The `strip-markers` policy supports `.py`, `.yaml`, and `.yml` files. Python marker lines use a space before the tag:

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

YAML marker lines can use the same form or a colon before the tag:

```
# BEGIN: Container specification
containers:
- name: api
  image: example.azurecr.io/aks-api:latest
# END: Container specification
```

The YAML block is emptied in the starter in the same way, with the marker lines and their indentation preserved.

Rules:

- Marker lines are preserved verbatim, including any leading indentation.
- Both `# BEGIN <TAG>` / `# END <TAG>` and `# BEGIN: <TAG>` / `# END: <TAG>` syntax are supported.
- Tags must match exactly (e.g. `# BEGIN X` pairs with `# END X`). Whitespace on either side of the tag is ignored.
- Exactly three blank lines sit between the `# BEGIN` line and its `# END` line.
- If a `# BEGIN` has no matching `# END` (or another `# BEGIN` appears before the expected `# END`), the block is left untouched and a warning is emitted so you can fix the finished file.
- Content outside of `# BEGIN` / `# END` blocks (helpers, imports, blank-line separators, module docstrings) is copied verbatim from finished. Whatever spacing exists between blocks in finished is what ends up in starter.

Other file types cannot use `strip-markers`; classify them with another policy.

## Starter-only files

Files that exist in the starter tree but not in the finished tree are reported as `extra in starter (not in finished; left alone)`. This skill never deletes anything from the starter tree. If a stale starter file needs to go, remove it by hand.

## When to use this skill

- You updated a reference implementation and want to regenerate a classified starter file.
- You need to enforce that a whole-file student exercise remains empty.
- You need to regenerate a starter template with instructional placeholders.
- You edited a `# BEGIN` / `# END` block in a classified Python or YAML file.
- Before shipping a milestone, to identify unclassified files without modifying them.

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

### Update one starter file

Use the repository-relative path under `starter/`:

```
python .github/skills/sync-starter-code/sync.py --file starter/aks/configure-aks/python/k8s/deployment.yaml
```

`--only`, `--topic`, and `--file` are mutually exclusive.

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
| present, classified, expected output matches | `unchanged` |
| present, classified, expected output differs | Rewrite according to policy. Result reported as `updated`. |
| present, classified, starter missing | Create according to policy. Result reported as `created`. |
| present, unclassified | Report `unclassified (left alone)`. Never write. |
| present, `ignore` policy | Report `ignored by policy`. Never write. |
| present, malformed or failed policy | Report an error. Never write that file and exit nonzero. |
| present, `strip-markers` policy with unmatched marker | Warning printed; affected region left untouched. Other matched blocks are emptied. |
| excluded (`azdeploy.py`, `.env`, `.env.ps1`, `sitecontainers-spec.json`, `*.md`, `*.pyc`, anything under `__pycache__/` or `.venv/`) | any | Ignored. Never read, never written. |
| missing | present | Reported as `extra in starter (not in finished; left alone)`. Not deleted. |

Exercises where [topic-map.json](/home/jeffko/lab-git/mslearn-azure-ai/.github/skills/exercise-inventory/topic-map.json) sets `starter_slug: null` (e.g. `integrate-services/azure-functions`) are silently skipped.

## Recommended workflow

1. Confirm the instructions' intended student action for the target file.
2. Add or review the explicit file policy in `policies.json`.
3. Make implementation edits in `finished/` and verify the reference implementation still runs.
4. Dry-run this skill against the smallest scope you can:
   ```
   python .github/skills/sync-starter-code/sync.py --file <starter-file> --diff
   ```
5. Confirm the diff exactly matches what the instructions expect the student to receive.
6. Apply:
   ```
   python .github/skills/sync-starter-code/sync.py --file <starter-file> --apply
   ```
7. Run the same command without `--apply` and confirm the file is unchanged.
8. If you also touched the deployment script, run the [sync-starter-deploy skill](/home/jeffko/lab-git/mslearn-azure-ai/.github/skills/sync-starter-deploy/SKILL.md) too.

## Files in this skill

- [SKILL.md](SKILL.md) — this file.
- [policies.json](policies.json) — explicit per-file starter-state policies.
- [sync.py](sync.py) — the policy-driven sync script.ver. Loads the exercise inventory from the [exercise-inventory skill](/home/jeffko/lab-git/mslearn-azure-ai/.github/skills/exercise-inventory/SKILL.md) so it never guesses paths.
