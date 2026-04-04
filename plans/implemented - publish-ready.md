# Make Repository Publish-Ready

## Context

The repo is functional but has several issues that need addressing before making it public on GitHub:

1. **Tracked `__pycache__` files** — 14 `.pyc` files are committed to git (`scripts/__pycache__/`), visible in `git ls-files --cached 'scripts/__pycache__/'`.
2. **No `.env.example`** — Users must read README to know which env vars are needed. The actual `.env` was never committed (good), but there's no template.
3. **Inline PEP 723 deps only** — Each script has `# /// script` metadata but there's no `pyproject.toml` for the project as a whole, making it harder for users to see all dependencies at a glance or use standard tooling.
4. **Hardcoded Anthem/Cook County specifics** — `check_anthem_network.py` has a 70-entry `COOK_COUNTY_CITIES` set (lines 37-70) used in `main()` standalone mode. The Anthem API endpoints themselves are properly env-var-driven (lines 30-33), but the module name and all print statements say "Anthem" throughout.
5. **Hardcoded article/author counts in README** — README line 28 says "702 articles", "2,800 authors", "1,904 records, 306 with relevant specialties"; ROADMAP.md has similar frozen counts (lines 6, 9, 24, 27). These will be wrong for any other condition.
6. **Stale data in ROADMAP.md** — "In Progress" item about ESI PPO plan (line 38-39) is user-specific. Open Problem 7 references "heir" (typo for "their").
7. **`fore_name` workaround** in `main.py` lines 117-122 is flagged as temporary debt.
8. **No license file.**

## Goals

- Remove all tracked files that shouldn't be in a public repo (`.pyc` files)
- Add `.env.example` so new users know exactly what credentials they need
- Add a `pyproject.toml` with consolidated dependency info
- Make the README and ROADMAP generic enough that someone searching for a different condition can understand how to adapt the tool
- Improve `.gitignore` for standard Python patterns
- Document clearly how to substitute a different insurance provider API
- Add a LICENSE file
- Clean up minor code debt (the `fore_name` workaround)

## Plan

### 1. Remove tracked `__pycache__` and fix `.gitignore`

**File: `.gitignore`** — Add standard Python ignores:
```
__pycache__/
*.pyc
*.pyo
```

Then remove the cached files from git tracking:
```bash
git rm -r --cached scripts/__pycache__/
```

### 2. Create `.env.example`

**New file: `.env.example`** — Template with all four required variables and comments explaining where to get credentials:
```
# Anthem/Elevance Health FHIR Provider Directory credentials
# Register at the Anthem developer portal to obtain these.
# See README.md for details.
ANTHEM_CLIENT_ID=
ANTHEM_CLIENT_SECRET=
ANTHEM_ACCESS_TOKEN_URL=https://totalview.healthos.elevancehealth.com/client.oauth2/unregistered/api/v1/token
ANTHEM_PROVIDER_DIRECTORY_URL=https://totalview.healthos.elevancehealth.com/resources/unregistered/api/v1/fhir/cms_mandate/mcd
```

Include the default URLs since those are public API endpoints (documented in Anthem's developer portal), not secrets.

### 3. Add `pyproject.toml`

**New file: `pyproject.toml`** — Minimal project metadata with consolidated dependencies. Keep the inline PEP 723 metadata in each script (it's what `uv run` uses), but add a `pyproject.toml` so the project has a standard entry point:

```toml
[project]
name = "physician-search"
version = "0.1.0"
description = "Find in-network physicians with demonstrated expertise in specific medical conditions"
requires-python = ">=3.11"
dependencies = [
    "httpx",
    "lxml",
    "python-dotenv",
    "duckdb",
]

[project.scripts]
physician-search = "main:main"
```

Do NOT remove the inline `# /// script` blocks from individual scripts — they're needed for standalone `uv run scripts/foo.py` usage. The `pyproject.toml` is supplementary, giving users a single place to see all deps.

### 4. Add LICENSE

**New file: `LICENSE`** — Use the GNU GPL v3 license. Use the current year (2026) and "Aryeh Jacobsohn" as author (from git config). Copy the standard GPL-3.0 text and add the copyright header.

### 5. Clean up README for public audience

**File: `README.md`**

Changes:
- Lines 25-32: Remove specific record counts ("702 articles", "2,800 authors", etc.) — these are run-specific output. Replace with generic descriptions like "full article metadata", "deduplicated author list", etc.
- Lines 77-88: Expand the Anthem credentials section. Add a subsection explaining that this currently supports Anthem/Elevance Health's FHIR Provider Directory, and document what someone would need to change to support a different insurer (see step 7).
- Add a brief "Adapting for a different insurer" section pointing to `check_anthem_network.py` and the `.env` variables.
- Add a "Adapting for a different condition" section explaining which constants to change (`TARGET_HCPCS` and `RELEVANT_TAXONOMIES`/`RELEVANT_CMS_SPECIALTIES` in `cms_db.py`, and the PubMed search terms in `fetch_authors.py`).

### 6. Clean up ROADMAP.md

**File: `plans/ROADMAP.md`**

- Remove frozen record counts from the "Completed" sections (lines 6, 9, 24, 27) — these are stale the moment someone runs it for a different condition.
- Line 38-39: Rewrite the "In Progress" ESI PPO item to be generic: "Identify the specific network/plan within the insurer's directory that matches the user's plan."
- Line 49: Fix "heir" → "their".

### 7. Document insurer substitution in check_anthem_network.py

**File: `scripts/check_anthem_network.py`**

Add a docstring section at the top of the module (after the existing docstring, around line 14) explaining what another user would need to change to adapt for a different FHIR-based provider directory:

```
Adapting for a different insurer:
- Set the four env vars in .env to point to your insurer's FHIR endpoint
- The OAuth2 flow (client credentials grant) is standard; if your insurer
  uses a different auth method, modify get_access_token()
- The FHIR Practitioner/PractitionerRole queries follow the DaVinci Plan-Net IG;
  any insurer implementing this IG should work with minimal changes
- The COOK_COUNTY_CITIES filter (used only in standalone mode) should be
  replaced with your geographic area of interest
```

Also move the `COOK_COUNTY_CITIES` set into a clearly labeled section with a comment like `# CUSTOMIZE: Replace with municipalities in your geographic area of interest`.

### 8. Fix the `fore_name` workaround

**File: `main.py` lines 117-122** and **File: `scripts/check_anthem_network.py` line 174, 178, 287**

The workaround exists because `merge_and_rank` outputs `first_name` but `check_anthem_network` expects `fore_name` (PubMed's field name). The fix:
- In `check_anthem_network.py`, change `run()` to accept either field: on lines 174 and 178, use `phys.get('fore_name') or phys.get('first_name', '')` instead of `phys['fore_name']`.
- Remove the workaround block in `main.py` lines 117-122.
- Also update line 287 which already does the fallback pattern — keep that as-is since it's in the print section which handles both cases.

### 9. Add a "Customization" section to README

**File: `README.md`** — Add a section after "Usage" that explains the three things someone needs to customize:

1. **Medical condition**: Which PubMed search terms (`fetch_authors.py` `SEARCH_TERMS`), which procedure codes and weights (`cms_db.py` `TARGET_HCPCS`), and which provider specialties (`cms_db.py` `RELEVANT_CMS_SPECIALTIES`, `RELEVANT_TAXONOMIES`).
2. **Insurance provider**: The four `.env` variables, and potentially the FHIR parsing logic if the insurer's directory doesn't follow DaVinci Plan-Net IG.
3. **Geographic area**: The `COOK_COUNTY_CITIES` set for standalone mode, and the `--state`/`--city` CLI flags.

Reference the specific files and constant names so someone can find them immediately.

## Files to modify

- `.gitignore` — add `__pycache__/`, `*.pyc`, `*.pyo`
- `.env.example` — **new file**, credential template
- `pyproject.toml` — **new file**, project metadata and consolidated deps
- `LICENSE` — **new file**
- `README.md` — remove frozen counts, add customization guide
- `plans/ROADMAP.md` — remove frozen counts, fix typo, genericize ESI PPO item
- `scripts/check_anthem_network.py` — add adaptation docs, label COOK_COUNTY_CITIES as customizable, fix `fore_name` fallback in `run()`
- `main.py` — remove `fore_name` workaround (lines 117-122)

## Testing

1. `git status` should show no `__pycache__` files tracked after step 1
2. `uv run main.py --help` still works (verify pyproject.toml doesn't break anything)
3. `uv run scripts/check_anthem_network.py --help` or a quick `--probe` still works after docstring changes
4. Grep the entire repo for any remaining secrets or personal data: `grep -ri "client_id\|client_secret\|password\|token=" --include="*.py" --include="*.md"` — should find only env var references, not actual values
5. Verify `.env` is not tracked: `git ls-files .env` should return empty
6. Read through README.md end-to-end as a new user — does the customization path make sense?

## Notes

- The `.env` file was **never committed** to git history (confirmed: `git log --all --diff-filter=A --name-only -- .env` returns nothing). No need for `git filter-branch` or BFG. The credentials are safe.
- The inline PEP 723 `# /// script` blocks should be kept alongside the new `pyproject.toml`. They serve different purposes: `pyproject.toml` is for project-level metadata/discoverability, while inline blocks let `uv run scripts/foo.py` work without installing the project.
- The `fore_name` fix (step 8) is low-risk — the field name mismatch is documented in ADR-002 line 48 and flagged as Phase 3 debt. The fix is a two-line change.
- `plans/` directory stays public per user preference.
- CLAUDE.md and ADR.md are developer-facing and fine to keep public. They don't contain secrets.
