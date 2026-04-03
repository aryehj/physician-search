# Plan 4: Open Payments (Sunshine Act)

## Goal

Find physicians who receive payments from pharmaceutical or device companies for products used in piriformis syndrome treatment. A doctor receiving consulting fees or speaker payments related to botulinum toxin (for piriformis injection) or nerve stimulation devices signals hands-on experience with these treatments.

## Data Source

**CMS Open Payments** — public API and bulk data at `openpaymentsdata.cms.gov`.

- API: SODA-compatible REST API (Socrata Open Data API)
- Endpoint: `https://openpaymentsdata.cms.gov/resource/<dataset-id>.json`
- Dataset: "General Payment Data" (most relevant — includes consulting, speaking, food/beverage, travel)
- No auth required for basic queries (API token optional for higher rate limits)
- Query params: SoQL (Socrata Query Language) — supports `$where`, `$select`, `$limit`, `$offset`

**IMPORTANT — Dataset ID discovery:** The Socrata dataset IDs change every year and are not predictable. The script MUST discover the correct dataset ID programmatically rather than hardcoding one. Approach:
1. Query the Open Payments catalog/metadata endpoint to list available datasets
2. Search for the most recent "General Payment" dataset
3. Extract the dataset ID (the alphanumeric slug in the URL)
4. If auto-discovery fails, accept a `--dataset-id` CLI arg as manual override and print instructions for finding the ID on the Open Payments website

## Relevant Products / Companies

### Drugs
| Product | Use in Piriformis | Manufacturer |
|---------|-------------------|-------------|
| Botox (onabotulinumtoxinA) | Piriformis muscle injection — chemical denervation | Allergan/AbbVie |
| Dysport (abobotulinumtoxinA) | Same use, alternative toxin | Ipsen |
| Marcaine/bupivacaine | Local anesthetic for piriformis injection | Various |
| Depo-Medrol (methylprednisolone) | Steroid injection into piriformis | Pfizer |

### Devices / Equipment
| Product | Use | Manufacturer |
|---------|-----|-------------|
| Ultrasound guidance equipment | Image-guided piriformis injection | Various |
| Radiofrequency ablation probes | Nerve ablation for chronic cases | Various (Stryker, Medtronic) |
| Peripheral nerve stimulators | Neuromodulation for sciatic pain | Nevro, Abbott, Medtronic |

## Noise Mitigation

Botox is used for many conditions beyond piriformis (migraine, cosmetic, spasticity, overactive bladder). The specialty filter is the primary noise reducer, but even within pain medicine, Botox payments may relate to headache treatment rather than piriformis. To manage this:

1. **Tight specialty filter** — only accept these Open Payments specialty strings:
   - "Allopathic & Osteopathic Physicians|Anesthesiology|Pain Medicine"
   - "Allopathic & Osteopathic Physicians|Physical Medicine & Rehabilitation"
   - "Allopathic & Osteopathic Physicians|Orthopaedic Surgery"
   - "Allopathic & Osteopathic Physicians|Orthopaedic Surgery|Sports Medicine"
   - "Allopathic & Osteopathic Physicians|Neurology"
   - Do NOT include general Anesthesiology (without Pain Medicine sub-specialty) or Neurology|Headache Medicine
2. **Cross-reference signal** — in output, flag physicians who also appear in Plan 1 (procedure volume) or Plan 2 (practice colleague) results. A physician with both Botox payments AND high 27096 procedure volume is a much stronger signal than payments alone.
3. **Payment type weighting** — consulting/speaking fees (signal: "this doctor is an expert the company wants to amplify") > research payments > food/beverage (signal: "a rep bought lunch")

## Approach

### Script: `find_by_payments.py`

**Step 0 — Discover dataset ID**

- Query the Open Payments data catalog to find the most recent "General Payment" dataset
- Try: `https://openpaymentsdata.cms.gov/api/1/metastore/schemas/dataset/items` or similar catalog endpoint
- Parse results for dataset with title matching "General Payment" and most recent year
- Extract the dataset ID
- Print and log the discovered ID and year
- If auto-discovery fails, require `--dataset-id` CLI arg

**Step 1 — Query for relevant payments**

Query the General Payment Data API for payments where product names match our targets:

```
GET /resource/{dataset_id}.json?
  $where=UPPER(name_of_drug_or_biological_or_device_or_medical_supply_1) LIKE '%BOTOX%'
    OR UPPER(name_of_drug_or_biological_or_device_or_medical_supply_1) LIKE '%DYSPORT%'
    OR UPPER(name_of_drug_or_biological_or_device_or_medical_supply_1) LIKE '%BOTULINUM%'
    ... (other products)
  &$select=covered_recipient_npi,
           covered_recipient_first_name,
           covered_recipient_last_name,
           covered_recipient_specialty_1,
           total_amount_of_payment_usdollars,
           nature_of_payment_or_transfer_of_value,
           name_of_drug_or_biological_or_device_or_medical_supply_1,
           recipient_city,
           recipient_state
  &$limit=50000
```

- Paginate with `$offset` if > 50000 results
- Check all product columns (`_1`, `_2`, `_3`, etc.) — some payments list multiple products
- SoQL has quirks with `UPPER()` and `LIKE` — test the exact syntax against the API before building the full query. If `UPPER()` isn't supported, use `upper()` (Socrata is case-sensitive about function names).

**Step 2 — Filter by specialty**

- Apply the tight specialty filter from the Noise Mitigation section above
- This dramatically reduces noise (filters out dermatologists, ophthalmologists, neurologists focused on headache, etc.)

**Step 3 — Aggregate by physician**

- Group by NPI
- Sum total payment amounts
- Collect: set of products, set of payment types (consulting, speaking, etc.), total amount
- Weight by payment type:
  - Consulting/speaking fees: weight 3
  - Research/education: weight 2
  - Food/beverage/travel: weight 1

**Step 4 — Cross-reference**

- Check which NPIs are already in our `physicians.json` (published authors)
- For new NPIs, query NPPES to get full practice address
- Filter to geographic area of interest
- If output files from Plan 1 or Plan 2 exist (`data/procedure_physicians.json`, `data/practice_colleagues.json`), flag overlapping NPIs in the output

**Step 5 — Output**

- Write `data/payment_physicians.json` — same base schema plus:
  - `payment_total`: float
  - `payment_weighted_score`: float (payment amount * payment type weight)
  - `payment_types`: list of nature-of-payment categories
  - `products`: list of drug/device names
  - `also_published`: bool
  - `also_in_procedure_data`: bool (if Plan 1 output exists)
  - `also_in_practice_colleagues`: bool (if Plan 2 output exists)
- Write `data/payment_physicians.csv`

### Key Implementation Details

- Use `httpx` for API queries. SODA API is rate-limited; respect `Retry-After` headers.
- Without an app token, limit is ~1000 req/hour. With token (free registration), 10K/hour. Start without token; add if needed.
- Product name matching must be case-insensitive and partial (LIKE, not exact match)
- The API returns strings for dollar amounts — convert to float for aggregation
- CLI args: `--state` filter, `--min-amount` (default $100, to exclude trivial food payments), `--year` (default: most recent), `--dataset-id` (manual override)

## Verification

1. Run `uv run find_by_payments.py --state IL`
2. Check output files for reasonable data
3. Verify a few NPIs: Google them, confirm they're pain medicine / PM&R doctors
4. Check that consulting/speaking payments are represented (if results are 100% food/beverage, the signal quality is low — consider raising `--min-amount`)
5. Cross-reference with our published author set — some overlap expected and validates the approach
6. Verify dataset ID discovery worked (check script output for the logged ID and year)

## Limitations

- Only captures Medicare-reported payments, not all industry relationships
- Botox is used for many conditions — specialty filtering helps but isn't perfect (mitigated by tight specialty list and cross-referencing with other plans)
- Small payments (meals) are noise; threshold helps but is arbitrary
- Not all piriformis-relevant treatments involve industry payments (e.g., dry needling, manual therapy)
- Data is ~1-2 years behind current date
