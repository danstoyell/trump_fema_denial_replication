# FEMA Disaster Declaration Approval Rates by President & State Party

Independent replication of the POLITICO/E&E News analysis (Thomas Frank) showing presidential approval rates for FEMA disaster requests from Democratic-led vs Republican-led states.

---

## Scripts

| Script | Description |
|---|---|
| `replicate_fema_analysis.py` | Main analysis — fetches all FEMA data, computes approval rates by president and state party, outputs a line chart |
| `export_trump2_records.py` | Exports all Trump 2nd term approved/denied records as a human-readable Markdown file |
| `biden_vs_trump2_chart.py` | Bar chart comparing Biden vs Trump 2nd term denial rates by state party |
| `trump2_sensitivity_chart.py` | Grouped bar chart showing Trump 2nd term denial rates across all 12 methodology combinations |
| `trump2_scatter.py` | Scatterplot of state-level FEMA approval rate vs 2024 Trump vote share |

All scripts support `--fema-web` (see below). Run any script with `--help` for full flag documentation.

---

## Methodology

### Data Sources

| Dataset | Default Endpoint | Alternative (`--fema-web`) |
|---|---|---|
| Approved declarations | `fema.gov/api/open/v2/DisasterDeclarationsSummaries` (~46,220 rows, one per county) | `fema.gov/api/open/v1/FemaWebDisasterDeclarations` (~5,168 rows, one per disaster) |
| Denied requests | `fema.gov/api/open/v1/DeclarationDenials` (~1,288 rows) | same |

Both approval endpoints are paginated at 1,000 records per request and fetched exhaustively.

### Declaration Types

Two types of presidential declarations exist under the Stafford Act:

- **Major Disaster (DR):** The primary tool for large-scale natural disasters. Unlocks the full suite of FEMA programs (IA, PA, HM).
- **Emergency (EM):** A narrower, faster mechanism for imminent or smaller-scale events. More limited in scope and funding.

By default the analysis uses **DR only** on both sides (approvals and denials) for an apples-to-apples comparison. Use `--include-emergency` to expand to DR+EM on both sides.

### Incident Type Filtering

By default, non-natural incident types are excluded. Because the two APIs use different terminology, separate exclusion lists are applied:

**Approvals** — excluded `incidentType` values: `Biological`, `Terrorist`, `Chemical`, `Other`, `Toxic Substances`

**Denials** — excluded `requestedIncidentTypes` values: `Human Cause`, `Other`, `Toxic Substances`

(`"Terrorist"` in the approvals API = `"Human Cause"` in the denials API; `"Chemical"` = `"Toxic Substances"`.)

Use `--all-types` to remove this filter symmetrically from both sides.

### Deduplication

- **Default approvals endpoint (v2):** One row per county per disaster. Deduplicated by `(disasterNumber, state)` so each state-level disaster counts once.
- **FemaWeb endpoint (v1):** Already one row per disaster. No deduplication needed.
- **Denials:** Only `currentRequestStatus = "Turndown"` records are counted. Exact duplicates by `declarationRequestNumber` are collapsed.

### Date Used for Presidential Assignment

- **Approvals:** `declarationDate` — the date the president signed the declaration.
- **Denials:** `requestStatusDate` — the date the denial decision was issued (not when the governor submitted the request). Falls back to `declarationRequestDate` if missing.

This ensures both sides are assigned to the president who made the decision, not the one who received the request.

### State Party Classification

A state's alignment is determined at the time of the request using a hardcoded `STATE_PARTY_DATA` dictionary covering all 50 states for every year from 1981 through 2026 (~2,300 state-year entries). Sources: National Governors Association historical records and senate.gov membership data.

Three classification modes are available:

| Mode | Rule |
|---|---|
| **Trifecta** (default) | Governor + both senators must all belong to the same party |
| `--two-thirds` | At least 2 of the 3 offices must belong to the same party |
| `--governor-only` | Classified by the governor's party alone; senators ignored |

States that don't meet the threshold for D or R are classified as **Mixed** and excluded from the D/R comparison. Independents cannot form a D or R alignment under any mode.

### Presidential Term Boundaries

Records are assigned to a presidential term by declaration/decision date:

| President | Start | End |
|---|---|---|
| Reagan | Jan 20, 1981 | Jan 20, 1989 |
| H.W. Bush | Jan 20, 1989 | Jan 20, 1993 |
| Clinton | Jan 20, 1993 | Jan 20, 2001 |
| G.W. Bush | Jan 20, 2001 | Jan 20, 2009 |
| Obama | Jan 20, 2009 | Jan 20, 2017 |
| Trump (1st) | Jan 20, 2017 | Jan 20, 2021 |
| Biden | Jan 20, 2021 | Jan 20, 2025 |
| Trump (2nd) | Jan 20, 2025 | Jan 20, 2029 |

### Excluded Records

| Category | Count | Notes |
|---|---|---|
| Territories & unclassified (AS, DC, GU, PR, VI, etc.) | ~138 | No governor/senator classification exists |
| Mixed-alignment states | ~1,482 | Split partisan control; excluded by methodology |
| Out-of-range dates | ~1,267 | Mostly pre-Reagan denial records; the denial database extends to 1953 |

### Approval Rate Formula

```
approval rate = approved / (approved + denied)
```

---

## Flags

### Declaration scope

| Flag | Approvals fetched | Denials counted |
|---|---|---|
| *(default)* | DR only | DR Turndowns only |
| `--include-emergency` | DR + EM | DR + EM Turndowns |

### Approvals data source

| Flag | Source | Granularity |
|---|---|---|
| *(default)* | `v2/DisasterDeclarationsSummaries` | One row per county (deduplicated) |
| `--fema-web` | `v1/FemaWebDisasterDeclarations` | One row per disaster (no dedup needed) |

The FemaWeb endpoint uses full type strings (`"Major Disaster"`, `"Emergency"`) which are automatically normalized to the short codes (`"DR"`, `"EM"`) used internally.

### Incident types

| Flag | Effect |
|---|---|
| *(default)* | Natural disasters only — non-natural types excluded symmetrically |
| `--all-types` | All incident types included on both sides |

### State classification

| Flag | Rule |
|---|---|
| *(default)* | Trifecta — governor + both senators must all match |
| `--governor-only` | Governor's party only |
| `--two-thirds` | 2 of 3 offices must match |

All flags can be freely combined. Output filenames are suffixed to reflect the active flags (e.g. `fema_approval_rates_fema_web_two_thirds.png`).

---

## Key Findings (Trump 2nd Term, as of March 2025)

Using the default methodology (trifecta, DR only, natural disasters):

| Alignment | Approved | Denied | Approval Rate |
|---|---|---|---|
| Democratic trifecta | 4 | 9 | ~31% |
| Republican trifecta | 27 | 9 | ~75% |

The partisan gap is **robust across all 12 methodology combinations** tested in the sensitivity analysis — Democratic state denial rates are 20–54 percentage points higher than Republican states regardless of how states are classified or which declaration types are included.

Under Biden, denial rates were statistically identical between Dem and Rep states (~16% each). The gap under Trump's 2nd term is driven almost entirely by the Democratic state denial rate tripling, not by Republican states receiving unusually favorable treatment relative to historical norms.

---

*Source: Independent replication using FEMA public APIs. Inspired by POLITICO/E&E News reporting (Thomas Frank). State party data sourced from National Governors Association historical records and senate.gov membership.*
