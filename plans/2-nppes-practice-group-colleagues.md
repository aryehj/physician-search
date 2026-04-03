# Plan 2: Same Practice Group via NPPES

## Goal

Find physicians who work at the same practice location as our known published experts. If Dr. A publishes on piriformis syndrome and Dr. B works in the same pain management office, Dr. B likely has relevant experience.

## Data Source

**NPPES API** — the same API already used in `lookup_npis.py`. No new data source needed.

Key insight: NPPES records include practice addresses. Two providers at the same address are colleagues. We can also search NPPES by organization name and location.

Additionally, NPPES has **Type 2 (Organization) NPIs** that represent practice groups. We currently filter to Type 1 (individual) only. Type 2 records can give us the organization name, which we can then use to find all individuals at that org.

## Approach

### Script: `find_practice_colleagues.py`

**Step 1 — Load known physicians**

- Read `data/physicians.json`
- Filter to `is_relevant_specialty: true` (our ~306 seed physicians)
- Extract unique practice addresses (normalize: uppercase, strip suite/unit numbers, trim whitespace)

**Step 2 — Group by practice address and count providers per address**

- Group seed physicians by normalized address
- This gives us practice locations known to have at least one piriformis expert
- **Hospital filter:** Count how many seed physicians share each normalized address. Separately, after querying NPPES in Step 3, count total providers returned per address. If an address yields > 20 providers across all specialties in a single zip code query, flag it as a probable hospital campus. For flagged addresses:
  - Still include results but tag them as `match_confidence: "low_hospital_campus"`
  - In the output, sort these below higher-confidence matches
  - This prevents large hospitals from dominating results while still surfacing them for manual review

**Step 3 — Search NPPES for colleagues at each address**

For each unique practice address (city + state + postal_code at minimum):

- Option A (preferred): Query NPPES API with `postal_code` + relevant taxonomy codes
  - API supports searching by `postal_code` and `taxonomy_description`
  - This finds all relevant-specialty providers near our experts
- Option B (fallback): Query by `organization_name` if we can extract it from the seed physician's NPPES record
  - Requires a second NPPES lookup of the seed physician to get their org name

For each approach, the NPPES API params are:
```
version=2.1
postal_code=XXXXX
taxonomy_description=Pain+Medicine  (or other relevant terms)
enumeration_type=NPI-1
limit=200
```

**Step 4 — Match addresses**

- For results from zip code search: compare normalized practice address against our seed addresses
- Accept as "same practice" if: same street address line 1 (after normalization) AND same city
- Accept as "same area" (weaker signal) if: same zip code + same relevant specialty
- **Billing address caveat:** NPPES "LOCATION" addresses are sometimes billing addresses for large groups rather than actual clinic sites. There is no reliable way to distinguish these programmatically. Accept this as a known limitation — the specialty filter and hospital-campus filter together keep noise manageable.

**Step 5 — Deduplicate and enrich**

- Remove NPIs already in our `physicians.json`
- For each new physician, record:
  - Which seed physician(s) they share an address with
  - Whether it's "same practice" (exact address match) or "same zip + specialty" (weaker)
  - Whether the address was flagged as a hospital campus
- Sort by signal strength: exact address matches (non-hospital) first, then hospital-campus matches, then same-zip matches

**Step 6 — Output**

- Write `data/practice_colleagues.json` — same base schema plus:
  - `colleague_of`: list of seed physician NPIs at same address
  - `match_type`: "same_address" | "same_address_hospital_campus" | "same_zip_specialty"
  - `match_confidence`: "high" | "low_hospital_campus" | "low_zip_only"
- Write `data/practice_colleagues.csv`

### Key Implementation Details

- Reuse address normalization logic: uppercase, strip "STE", "SUITE", "UNIT", "#" and trailing numbers, collapse whitespace
- NPPES API limit is 200 results per query and ~3 req/sec — same rate limiting as `lookup_npis.py`
- Some zip codes will have many providers; only keep those with relevant specialties
- Use the same `RELEVANT_TAXONOMIES` dict from `lookup_npis.py` — import or duplicate it
- CLI args: `--state` (default: all states in seed data), `--match-type` (address|zip|both, default both), `--hospital-threshold` (default 20, number of providers at an address before it's flagged as hospital campus)

### Address Normalization Function

```python
def normalize_address(addr_line: str) -> str:
    """Normalize address for comparison."""
    s = addr_line.upper().strip()
    # Remove suite/unit identifiers
    s = re.sub(r'\b(STE|SUITE|UNIT|APT|#)\s*\w*', '', s)
    # Collapse whitespace
    s = re.sub(r'\s+', ' ', s).strip()
    return s
```

## Verification

1. Run `uv run find_practice_colleagues.py`
2. Pick a seed physician, verify their practice address in `physicians.json`
3. Check that the output includes other providers at that same address
4. Google the address to confirm it's a real medical practice with multiple providers
5. Verify no seed physicians appear in the output (they should be excluded)
6. Check that hospital-campus addresses are properly flagged and sorted below direct matches

## Limitations

- NPPES addresses can be billing addresses, not actual practice locations (mitigated by noting this in `match_confidence`)
- Solo practitioners won't yield colleagues
- Large hospital addresses will yield many providers (mitigated by the hospital-campus threshold flag — default > 20 providers = flagged)
