# sync-starter-deploy

Sync `starter/**/python/azdeploy.py` from `finished/**/python/azdeploy.py` for every exercise, byte-for-byte, below the DON'T-CHANGE divider.

## The one rule that matters

**Only the region below this divider is ever synced. Everything above it in the starter file is preserved verbatim, always.**

```
# =============================================================================
# DON'T CHANGE ANYTHING BELOW THIS LINE.
# =============================================================================
```

Reasoning:

- **Above the divider is student territory.** The header block holds student-editable defaults (`rg`, `location`, and any per-exercise variables promoted into the header). Starter and finished frequently and legitimately differ up there.
- **Below the divider is machine territory.** Helpers, menu logic, `az` invocations, error handling. Starter and finished must stay identical below the divider or the exercise experience diverges.

If either the finished or starter file lacks the divider, the file is skipped with a warning. The sync will never write a file where the divider is missing or ambiguous.

Corollary rules:

- **Finished is the source of truth.** This skill never writes to anything under `finished/`.
- **Never sync above the divider.** Not even as a "helpful" backport. If the header block needs to change, do that by hand or with a dedicated one-shot; this skill is not the tool.
- **Only `azdeploy.py`.** No `.sh` or `.ps1`; those scripts no longer ship.

## When to use this skill

- A deploy script was updated in `finished/` and the matching starter needs to catch up.
- You fixed a bug, added a menu option, or refactored a helper in one or more finished deploy scripts and want to propagate the change.
- Before shipping a milestone, to confirm every starter is byte-identical to finished below the divider.

## When NOT to use this skill

- Authoring a brand-new `azdeploy.py` from scratch — use the [azdeploy-scripts skill](/home/jeffko/lab-git/mslearn-azure-ai/.github/skills/azdeploy-scripts/SKILL.md) for that.
- Any change that should originate in the starter. The direction is always `finished -> starter`.
- Changing anything in the header block (see the callout above).

## How to run

Always launch from the repo root. Dry-run first, always.

### Update everything

```
python .github/skills/sync-starter-deploy/sync.py
```

### Update every exercise under one topic

Topic slugs match the top-level folder under `finished/` (e.g., `postgresql`, `aks`, `azure-container-apps`, `amr`, `app-sec-config`, `container-hosting`, `cosmosdb`, `instrument-observe`, `integrate-services`). Full list lives in [topic-map.json](/home/jeffko/lab-git/mslearn-azure-ai/.github/skills/exercise-inventory/topic-map.json).

```
python .github/skills/sync-starter-deploy/sync.py --topic postgresql
```

### Update one exercise

Exercise ids are `<topic>/<exercise>`. See the [exercise-inventory skill](/home/jeffko/lab-git/mslearn-azure-ai/.github/skills/exercise-inventory/SKILL.md) for the full list.

```
python .github/skills/sync-starter-deploy/sync.py --only postgresql/build-agent
```

`--only` and `--topic` are mutually exclusive.

### Preview exactly what would change

```
python .github/skills/sync-starter-deploy/sync.py --topic postgresql --diff
```

Prints a unified diff for every file that would change. Works with or without `--apply`.

### Actually write changes

Add `--apply` to any of the above. Without it, the script is dry-run only and reports `would update`, `would create`, or `unchanged`.

```
python .github/skills/sync-starter-deploy/sync.py --topic postgresql --apply
```

## Exact behavior per file

For each exercise the [exercise-inventory skill](/home/jeffko/lab-git/mslearn-azure-ai/.github/skills/exercise-inventory/SKILL.md) reports:

| finished `azdeploy.py` | starter `azdeploy.py` | Action |
|---|---|---|
| exists, has divider | exists, has divider, body already matches | `unchanged` |
| exists, has divider | exists, has divider, body differs | Replace starter body below divider with finished body below divider. Header preserved. |
| exists, has divider | missing | Copy the entire finished file to starter (this is the only case the header is copied — nothing to preserve). |
| exists, no divider | any | `skip: divider missing in finished` (fix the finished file first) |
| exists, has divider | exists, no divider | `skip: divider missing in starter` (fix by deleting the starter file so the next run recreates it, or add the divider by hand) |
| missing | exists | `skip: finished file missing` (deleting starter files is out of scope for this skill) |
| missing | missing | Nothing reported. |

Exercises where [topic-map.json](/home/jeffko/lab-git/mslearn-azure-ai/.github/skills/exercise-inventory/topic-map.json) sets `starter_slug: null` (e.g., `integrate-services/azure-functions`) are silently skipped.

## Recommended workflow

1. Make your edits in `finished/` using the [azdeploy-scripts skill](/home/jeffko/lab-git/mslearn-azure-ai/.github/skills/azdeploy-scripts/SKILL.md) conventions.
2. Dry-run this skill against the smallest scope you can:
   ```
   python .github/skills/sync-starter-deploy/sync.py --only <topic>/<exercise> --diff
   ```
3. Confirm the diff shows only what you meant to change and only below the divider.
4. Apply:
   ```
   python .github/skills/sync-starter-deploy/sync.py --only <topic>/<exercise> --apply
   ```
5. Widen scope as needed (`--topic <topic>`, then no scope) once you're confident.

## Files in this skill

- [SKILL.md](SKILL.md) — this file.
- [sync.py](sync.py) — the sync driver. Loads the exercise inventory from the [exercise-inventory skill](/home/jeffko/lab-git/mslearn-azure-ai/.github/skills/exercise-inventory/SKILL.md) so it never guesses paths.
