---
name: azdeploy-scripts
description: Author, update, and port azdeploy deployment helper scripts (Bash, PowerShell, Python) for mslearn-azure-ai exercises. Covers the shared conventions all three flavors must follow, the Python port workflow (single stdlib script replacing sibling .sh and .ps1), the ASCII-only + cross-shell rules, and the dual .env / .env.ps1 file contract. Trigger phrases include "update azdeploy", "port azdeploy to Python", "convert deploy script to python", "python version of azdeploy", "azdeploy for X exercise", "azdeploy conventions", "add a menu option to azdeploy".
---

# azdeploy scripts (Bash, PowerShell, Python)

Every exercise folder ships an `azdeploy` helper that provisions the Azure resources the student needs. Historically that's a `.sh` and a `.ps1`; new exercises can additionally ship (or be replaced by) a single `azdeploy.py`. This skill covers all three flavors and the port workflow between them.

**Location convention:** `finished/<topic>/<exercise>/python/azdeploy.{sh,ps1,py}` (starter folder mirrors the same layout).

**When to use this skill**

- Creating a new exercise's `azdeploy.sh` / `azdeploy.ps1` by copying from a reference exercise.
- Adding a menu option, changing resource names, or adjusting env-file output on an existing script.
- Porting an exercise's `.sh` + `.ps1` to a single `azdeploy.py`.
- Auditing an existing script for parity or convention drift.

**Reference implementations (gold standard)**

- Bash + PowerShell: [finished/amr/pub-sub/python/azdeploy.sh](../../finished/amr/pub-sub/python/azdeploy.sh) and [.ps1](../../finished/amr/pub-sub/python/azdeploy.ps1) — best error handling, blocking create, retry-safe delete, warning suppression, Bash/PowerShell parity.
- Python port: [finished/aks/configure-aks/python/azdeploy.py](../../finished/aks/configure-aks/python/azdeploy.py) — canonical example of the stdlib-only, cross-shell, dual-env-file pattern.

---

## Part 1 — Shared conventions (all three flavors)

These rules apply to `.sh`, `.ps1`, and `.py` alike. When porting between them, preserve every user-visible message and every `az` argument unless a rule below says otherwise.

1. **Header lines are load-bearing.** The first 11 lines of `.sh` and `.ps1` (header comment block plus `rg`/`location` variables) are the only part students edit. Never rewrite them. Python ports mirror the same layout — same divider, same `# CHANGE THESE` intro, same commented example lines (`# rg = "<your-resource-group-name>"`, `# location = "<your-azure-region>"`), and **lowercase** `rg` and `location` module variables (not `RG`/`LOCATION`). Header parity across the three flavors matters more than PEP 8 constant casing, because the top of every script gets hand-edited before it's copied into the starter folder.
   - **Promote variables students commonly need to change** into the header block, above the "DON'T CHANGE" divider. Rule of thumb: if students hit subscription/region-specific failures because of that value, it belongs at the top.
   - **AKS scripts specifically:** `aks_vm_size` (Python: `AKS_VM_SIZE`) lives in the header, not below the divider, because Standard_D2s VM generations vary by subscription and region. Use the canonical-plus-fallback pattern:
     ```python
     # If the Standard_D2s_v7 SKU is not available in your region, try using Standard_D2s_v5, or Standard_D2s_v6 instead.
     # AKS_VM_SIZE = "Standard_D2s_v7" # Keeping for production
     AKS_VM_SIZE = "Standard_D2s_v6"
     ```
     Mirror the same shape in `.sh` and `.ps1` (lowercase `aks_vm_size`, same commented fallback line). Apply this to every AKS exercise (`aks/configure-aks`, `aks/deploy-aks`, `aks/troubleshoot-aks`) as they get ported.
2. **Preserve existing patterns.** When updating an existing script, only touch:
   - Resource names and derived variables below line 11.
   - Service-specific create/configure/status functions.
   - Menu items and descriptions.
   - Status-check logic for the new services.
3. **Established conventions (all flavors):**
   - Check if a resource exists (`provisioningState` probe) before creating it.
   - Prefix error messages with `Error: `.
   - Bash: use `local` for function-scoped variables. PowerShell: use `$script:` sparingly and prefer function-local variables. Python: pass state as function arguments.
   - Generate unique resource names using a SHA1 hash of the Azure user object id (first 8 hex chars).
   - Check `az` authentication at script startup; exit with `Please run: az login` if not authenticated.
   - **ASCII-only output.** No check marks (`✓`), warning signs (`⚠`), arrows, box-drawing, or emoji. They render inconsistently across PowerShell hosts and terminals. Use words: `Created`, `Not created`, `Ready`, `WARNING:`, `->`. This applies retroactively — Python ports must drop the check marks that `.sh` and `.ps1` currently contain.
   - Keep Bash and PowerShell messages identical so both scripts behave the same. When a Python port supersedes them, the Python messages match too.
4. **Suppress noise but surface real errors.**
   - `.sh` / `.ps1`: add `--only-show-errors` to `az` action commands (create/update/delete) to hide breaking-change and preview WARNINGs while still printing ERRORs on failure.
   - Redirect probe/query commands (`show`/`list` used for existence checks) with `2>/dev/null` (Bash), `2>$null` (PowerShell), or `capture_output=True` + discard stderr (Python) so a "not found" doesn't print a stack trace.
   - PowerShell wraps action commands in `Invoke-Quiet`; Bash uses `run_quiet`; Python uses `run_quiet(description, argv)` — all stay quiet on success and print the exit code plus captured output on failure.
   - **Python ports: set the CLI env var once, not the flag on every command.** Add this line right after the imports (before any subprocess call): `os.environ.setdefault("AZURE_CORE_ONLY_SHOW_ERRORS", "true")`. Azure CLI honors this env var globally, so every `az` invocation — including `az_query` probes — behaves as if `--only-show-errors` were passed. `subprocess.run` inherits the process env on every OS/shell (Linux, macOS, Windows PowerShell 5.1/7+, cmd, Git Bash). Do NOT pass `--only-show-errors` in argv lists; the env var replaces it.
5. **Handle create failures and retries robustly without changing the exercise flow.**
    - Prefer a blocking create so the script can detect and explain terminal failures inline. For a long-running deployment, structure the exercise so students leave the deployment terminal running and complete code or other work in VS Code while it provisions.
    - Read the exercise instructions before changing whether a create command blocks. Preserve `--no-wait` only when the exercise genuinely requires the deployment command to return control to the same terminal before provisioning finishes. If practical, reorder independent exercise work before removing or adding `--no-wait`.
   - Before creating, inspect the existing `provisioningState`: `Succeeded` → already exists, return; `Failed`/`Canceled` → delete the stale resource, poll until it is fully gone before recreating (a delete can report success before Azure finishes removing the resource, which otherwise causes a name conflict); empty/null → create; anything else → still provisioning, return.
    - On a blocking create failure, print clear, actionable guidance (capacity/region issues and how to change the region and retry). For a background create, provide that guidance when the later status or retry path observes a failed terminal state.
6. **When asked to update a copied script:**
   - First read the source script to understand existing patterns.
   - Only modify service-specific logic (create, configure, status-check functions).
   - Keep the menu loop, resource-group function, and env-file patterns intact.
   - Update variable names and menu text to match the new exercise.
   - Clear the screen (`clear` / `Clear-Host` / `clear_screen()`) after a valid menu selection so long-running output stays readable.

---

## Part 2 — Env file contract (`.env` + `.env.ps1`)

**When an exercise needs env vars, always emit BOTH files, never just one.** Students consume them with `source .env` (Bash/zsh/Git Bash) or `. .\.env.ps1` (PowerShell). The single-script Python port must produce both from the same run.

**When to emit env files:** if the exercise's client app reads any environment variable (endpoint, connection string, resource id, service name), the deploy script writes both files. If the exercise has no client-facing env vars (e.g. `aks/configure-aks`, which only sets up kubectl), the script writes neither.

**File formats**

`.env` (bash-source compatible):

```bash
export KEY="value"
```

`.env.ps1` (PowerShell dot-source compatible on PS 5.1 and 7+):

```powershell
$env:KEY = "value"
```

**Encoding and line endings**

- UTF-8 without BOM.
- LF line endings only (no CRLF). Bash and Git Bash choke on CRLF `.env` files; PowerShell reads either but LF stays consistent.
- ASCII-only content in values by default; UTF-8 preserved if a value legitimately needs it.

**Value escaping**

For `.env` (bash `source`), escape in this order: `\` → `\\`, `"` → `\"`, `$` → `\$`, backtick → `\`` (literal backslash-backtick).

For `.env.ps1`, use PowerShell's backtick escapes: backtick → double backtick, `"` → backtick-quote, `$` → backtick-dollar.

The Python helper below implements both.

---

## Part 3 — Python port workflow

Use this when the user asks to port an exercise's `azdeploy.sh` / `azdeploy.ps1` to a single `azdeploy.py`. Do not port more than one exercise per request unless explicitly asked.

**Design rules**

- **No shebang line.** Students always launch with `python azdeploy.py`, and shebangs are meaningless on Windows.
- **No module docstring or file-level header comment.** The file starts with the `Change the values of these variables as needed.` banner, matching the `.sh` / `.ps1` layout. Students don't need commentary describing what the script is.
- **Stdlib only.** No `azure-*` SDKs, no pip installs. Shell out to `az` and `kubectl` via `subprocess`.
- **Cross-platform targets:** Linux bash/zsh, macOS bash/zsh, Windows PowerShell 5.1 and 7+, Windows cmd, Git Bash on Windows. Every construct must work on all of them.
- **Executable resolution:** never rely on bare `["az", ...]`. Use `shutil.which("az")` (returns `az.cmd` on Windows) and pass the resolved path to `subprocess.run`. Cache resolved paths in a module-level dict.
- **`subprocess.run` calls:** always pass `check=False` explicitly and inspect `returncode` yourself.
- **ASCII-only output** (see Part 1). Verify with `grep -P '[^\x00-\x7F]' azdeploy.py` — must return zero matches before you're done.
- **Cross-shell screen clear:** `os.system("cls" if os.name == "nt" else "clear")`, and on nonzero return fall back to writing ANSI `"\x1b[2J\x1b[3J\x1b[H"` + flush. Git Bash on Windows needs this fallback.
- **Preflight `chdir`.** At startup, resolve `Path(__file__).parent`, verify the exercise-specific anchor file exists (typically `api/Dockerfile` or similar), and `os.chdir()` into the script folder. This makes cwd-relative `az` args (like `az acr build ... api/`) work regardless of where the student launches the script.
- **Ctrl+C:** wrap `main()` with `try/except KeyboardInterrupt` and `sys.exit(130)` for a clean abort.
- **Same interactive numbered menu as `.sh` / `.ps1`.** No argparse, no subcommands — students shouldn't have to learn a new UX.

**Reusable env-file writer**

Every port includes this helper, even when the current exercise doesn't call it. Copy verbatim from the reference implementation:

```python
def write_env_files(env_vars: dict[str, str], directory: str = ".") -> None:
    """Write .env (bash) and .env.ps1 (PowerShell) side by side.

    Writes UTF-8 without BOM and LF line endings so both bash `source` and
    PowerShell dot-source read them correctly on every supported shell.
    """
    target_dir = Path(directory)
    target_dir.mkdir(parents=True, exist_ok=True)

    def bash_escape(value: str) -> str:
        return (
            value.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("$", "\\$")
            .replace("`", "\\`")
        )

    def ps_escape(value: str) -> str:
        return (
            value.replace("`", "``")
            .replace('"', '`"')
            .replace("$", "`$")
        )

    bash_lines = [f'export {k}="{bash_escape(v)}"\n' for k, v in env_vars.items()]
    ps_lines = [f'$env:{k} = "{ps_escape(v)}"\n' for k, v in env_vars.items()]

    with open(target_dir / ".env", "w", encoding="utf-8", newline="\n") as f:
        f.writelines(bash_lines)
    with open(target_dir / ".env.ps1", "w", encoding="utf-8", newline="\n") as f:
        f.writelines(ps_lines)
```

**Decision guide — does this exercise need env files?**

1. Read the sibling `azdeploy.sh`. Grep for `cat > .env` / `export ` written to `.env` / any `.env` write.
2. If the `.sh` writes an env file → include the `write_env_files` helper above and call it at the same point in the flow with the same keys.
3. If the `.sh` writes no env file (e.g. AKS configure-aks) → **omit `write_env_files` from the script entirely.** No dead code. The reference implementation above stays in this skill for the next port that needs it.
4. If only one of `.sh` / `.ps1` writes env vars → treat that as a bug in the originals and emit both files anyway.

**Coexistence during testing**

Keep `azdeploy.sh` and `azdeploy.ps1` alongside the new `azdeploy.py` while the user tests the port. Only delete them once the user confirms the Python version is working end-to-end.

**Instruction markdown updates**

Exercise `.md` files still reference `.sh` / `.ps1` and use `source .env` (Bash) or `. .\.env.ps1` (PowerShell). Updating those instructions to reference `azdeploy.py` is a separate task — do not touch the markdown as part of a port unless the user explicitly asks.

---

## Part 4 — Verification checklist

Run these after any authoring or porting change. The Python port has extra steps beyond `.sh` / `.ps1`.

**All flavors**

- [ ] Script header (first 11 lines of `.sh` / `.ps1`, or the `RG`/`LOCATION` block of `.py`) is intact.
- [ ] Every `az` command matches its counterpart across flavors (same subcommand, same flags, same values).
- [ ] Menu text is identical across flavors.
- [ ] Error messages start with `Error: `.
- [ ] No unicode symbols anywhere.
- [ ] If the exercise uses env vars, both `.env` and `.env.ps1` are written in the same code path.

**Python port additionally**

- [ ] `python3 -m py_compile azdeploy.py` succeeds.
- [ ] `grep -P '[^\x00-\x7F]' azdeploy.py` returns zero matches (ASCII-only).
- [ ] `subprocess.run` calls pass `check=False` explicitly.
- [ ] Every executable goes through `shutil.which()`.
- [ ] Running from a wrong cwd still works (the preflight `chdir` handles it) OR emits the friendly "kept the exercise folder intact" error when the anchor file is missing next to the script.
- [ ] Running without `az login` prints "Error: Not authenticated with Azure. Please run: az login" and exits 1.
- [ ] Create commands preserve the blocking or background behavior described by the exercise instructions.
- [ ] If `write_env_files()` is called: run a temp-dir unit check (write a dict with values containing `"`, `\`, `$`, backtick) and confirm both files are UTF-8 no BOM, LF-only, and use the right escape rules.

**Agent must NOT**

- Run billable `az ... create` commands to verify. Live provisioning is user-owned.
- Delete `azdeploy.sh` / `azdeploy.ps1` as part of a port. That's a separate cleanup step after the user has tested.
- Edit exercise `.md` files during a port. Instructions are updated later.
