# exercise-inventory

Repo-wide map of every exercise across the `finished/`, `starter/`, and `instructions/` trees. Use this skill whenever you need to reason about "the same exercise" across all three trees — for parity audits, refactors that touch multiple trees, or renaming exercises.

**When to use this skill**

- Auditing whether `starter/` and `finished/` deployment scripts are still in sync for every exercise.
- Verifying that code blocks shown in an exercise's instruction Markdown match the `# BEGIN / # END` regions in the corresponding `finished/` source.
- Confirming that a `starter/` exercise still ships with the correct empty `# BEGIN / # END` block scaffolding.
- Bulk operations that iterate over exercises (e.g., "add a new note to every exercise's Troubleshooting section").
- Any question of the form "for exercise X, where are its three homes?"

**Files in this skill**

- [SKILL.md](SKILL.md) — this file.
- [topic-map.json](topic-map.json) — hand-maintained source of truth. Maps each exercise's slug to its finished/starter/instructions paths. Update it when adding, renaming, or removing an exercise (see below).
- [inventory.py](inventory.py) — reads `topic-map.json` and emits the current inventory as JSON (default) or Markdown (`--markdown`). Stdlib only, no dependencies.

## How to run

Always launch from the repo root:

```
python .github/skills/exercise-inventory/inventory.py
```

**Flags**

- (no flag) — Emit a JSON payload on stdout. Structure:
  ```json
  {
    "repo_root": "/abs/path/to/repo",
    "count": 22,
    "exercises": [
      {
        "id": "postgresql/build-agent",
        "topic": "postgresql",
        "exercise": "build-agent",
        "finished_dir": "finished/postgresql/build-agent",
        "starter_dir": "starter/postgresql/build-agent",
        "instructions_file": "instructions/azure-database-postgresql/01-build-agent-tool-backend.md"
      }
    ]
  }
  ```
- `--check` — Same JSON, plus `finished_exists`, `starter_exists`, `instructions_exists` booleans on every entry. Use this to find drift between what `topic-map.json` claims and what's actually on disk.
- `--markdown` — Printable table with a `missing` column showing any tree where the path doesn't exist on disk. Implies `--check`.

All paths in the output are repo-root-relative. Callers should prepend the repo root when they need absolute paths.

## Data model

`topic-map.json` groups exercises under topics. A topic entry looks like:

```json
"postgresql": {
  "instructions_dir": "azure-database-postgresql",
  "starter_topic": "postgresql",
  "exercises": {
    "build-agent": {
      "starter_slug": "build-agent",
      "instructions_file": "01-build-agent-tool-backend.md"
    }
  }
}
```

- `instructions_dir` — folder under `instructions/` that holds this topic's Markdown files. This handles the common case where the `finished/` and `starter/` topic slug differs from the `instructions/` slug (e.g., `finished/postgresql` vs `instructions/azure-database-postgresql`, `finished/amr` vs `instructions/azure-managed-redis`).
- `starter_topic` — folder under `starter/` that holds this topic's exercises. Handles the same asymmetry (e.g., `finished/azure-container-apps` vs `starter/aca`). If the starter tree uses the same slug as the finished tree, set this equal to the topic key.
- `exercises.<exercise-slug>` — the folder name under `finished/<topic>/`. The map assumes this is the canonical exercise slug.
- `exercises.<exercise-slug>.starter_slug` — the folder name under `starter/<starter_topic>/`. Handles per-exercise starter renames (e.g., `finished/azure-container-apps/deploy-container-aca` vs `starter/aca/aca-deploy`). Set to the exercise-slug when they match. Set to `null` when no starter exists for this exercise.
- `exercises.<exercise-slug>.instructions_file` — the Markdown filename under `instructions/<instructions_dir>/`.

## When to update `topic-map.json`

- **New exercise added.** Add an entry under the matching topic. If the topic itself is new, add a topic entry.
- **Exercise renamed.** Update the key under `exercises` (finished slug) plus any of `starter_slug` / `instructions_file` that changed.
- **Exercise deleted.** Remove the entry. If the whole topic is gone, remove the topic entry.
- **Folder slug conventions changed.** Update `instructions_dir` or `starter_topic` at the topic level.

After every change, run `python .github/skills/exercise-inventory/inventory.py --markdown` and confirm the `missing` column is `-` for every row. Any row with entries in `missing` means either the map is wrong or the tree is missing a folder — both are fixable but neither should be committed.

## How other skills should consume this

Downstream skills (e.g., a future "exercise-parity-audit" skill) should:

1. Invoke `inventory.py` with no flags, parse the JSON on stdout.
2. Iterate `exercises`. For each entry, compute the three absolute paths by joining `repo_root` with the relative paths.
3. Run their per-exercise checks.
4. Report findings keyed by `id` so users can quickly locate the offending exercise.

Prefer this over hand-scanning the three trees. Any hard-coded folder assumption in a downstream skill is a bug waiting to happen the next time a folder is renamed.
