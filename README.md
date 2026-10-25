# FEMA Disaster Declaration Approval Rates by President & State Party

Independent replication of the POLITICO/E&E News analysis (Thomas Frank) showing presidential approval rates for FEMA disaster requests from Democratic-led vs Republican-led states.

---

## Scripts

| Script | Description |
|---|---|
| `replicate_fema_analysis.py` | Main analysis — fetches all FEMA data, computes approval rates by president and state party, outputs a line chart |
| `export_trump2_records.py` | Exports all Trump 2nd term approved/denied records as a human-readable Markdown file |
| `export_csv.py` | Row-level CSV of every approved/denied record with all classification columns (`fema_all_records.csv`) |
| `biden_vs_trump2_chart.py` | Bar chart comparing Biden vs Trump 2nd term denial rates by state party (two-thirds rule) |
| `trump_combined_denial_chart.py` | Trump 1+2 combined denial rates under three classification methods (election / governor / trifecta) |
| `trump2_sensitivity_chart.py` | Grouped bar chart showing Trump 2nd term denial rates across all 12 methodology combinations |
| `trump2_scatter.py` | Scatterplot of state-level FEMA approval rate vs 2024 Trump vote share (`--include-emergency` adds EM on both sides) |
| `request_behavior_analysis.py` | 4-panel chart testing whether the partisan gap reflects request behavior (volume, scope, incident mix) or decisionmaker behavior |

All scripts support `--fema-web` (see below). Run any script with `--help` for full flag documentation.

### Pending-as-denial augmentation

`replicate_fema_analysis.py` and `request_behavior_analysis.py` both accept `--include-pending <CSV>` (with optional `--pending-threshold-days N`, default 30). OpenFEMA only publishes requests after they're decided, so requests stuck in "Pending" status are invisible to the canonical pipeline. Pass a Disaster Tracker spreadsheet and any pending request older than the threshold is counted as a de-facto denial in the most recent president's column; the line chart marks the resulting drop with a hollow ghost marker. Pending rows whose state already has an OpenFEMA decision on a request dated within 3 days are skipped, so a stale tracker can't double-count.

The tracker is the Revolving Door Project's [Trump disaster aid map](https://therevolvingdoorproject.org/?p=159357); its data is a public [Google Sheet](https://docs.google.com/spreadsheets/d/1VEeTSh1xHNB3EolYEcVECFtUURB3QBSzceUfVXnjJOI/edit?usp=sharing). Refresh the committed copy with:

```
curl -L "https://docs.google.com/spreadsheets/d/1VEeTSh1xHNB3EolYEcVECFtUURB3QBSzceUfVXnjJOI/export?format=csv" -o "Disaster Tracker - Interactive Map - Sheet1.csv"
```

The committed copy is the Oct 23, 2026 snapshot. Both the old ("Waiting Period", "N days and counting") and current ("Waiting Period (Days)") column formats are accepted.

---

## Methodology

### Data Sources

| Dataset | Default Endpoint | Alternative (`--fema-web`) |
|---|---|---|
| Approved declarations | `fema.gov/api/open/v2/DisasterDeclarationsSummaries` (~46,700 DR + ~21,700 EM rows, one per county) | `fema.gov/api/open/v1/FemaWebDisasterDeclarations` (~5,290 rows, one per disaster) |
| Denied requests | `fema.gov/api/open/v1/DeclarationDenials` (~1,306 rows) | same |

Row counts as of Oct 25, 2026. After deduplication the two approval endpoints give identical results in every flag combination.

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

A state's alignment is determined at the time of the decision (the same date used for presidential assignment) using a hardcoded `STATE_PARTY_DATA` dictionary covering all 50 states for every year from 1981 through 2026 (~2,300 state-year entries). Sources: National Governors Association historical records and senate.gov membership data. Entries for 2009–2026 were re-verified against officeholder records in Oct 2026; earlier years have not been fully audited.

Tribal requests are attributed to the state they fall in (both approvals and denials), even though tribes request declarations directly rather than through the governor.

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
| Territories & unclassified (AS, DC, FM, GU, MH, MP, PR, PW, VI) | ~203 | No governor/senator classification exists |
| Mixed-alignment states | ~1,794 | Split partisan control; excluded by methodology |
| Out-of-range dates | ~1,396 | Pre-Reagan records; the databases extend back to 1953 |

Counts are for `--fema-web --all-types --include-emergency` with trifecta classification, Oct 25, 2026.

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

## Key Findings (Trump 2nd Term, as of Oct 25, 2026)

| Configuration | Dem approved | Rep approved | Gap |
|---|---|---|---|
| Default (trifecta, DR only, natural disasters) | 17 / 37 (45.9%) | 56 / 66 (84.8%) | 38.9 pts |
| `--fema-web --all-types --include-emergency` (trifecta) | 25 / 49 (51.0%) | 70 / 85 (82.4%) | 31.4 pts |
| …plus `--include-pending` (Oct 23 tracker) | 25 / 49 (51.0%) | 70 / 86 (81.4%) | 30.4 pts |

The partisan gap appears in **all 24 flag combinations**: Republican states' approval rate exceeds Democratic states' by 18.6–38.9 percentage points. It is narrowest under governor-only classification and widest under trifecta with major disasters only. Under Biden the same 24 combinations show gaps between −5.1 and +0.4 points, with Democratic states usually slightly ahead.

Republican states' Trump 2nd-term approval rate (81–85%) is close to their Biden-era rate (~84%), so the gap comes from the drop in Democratic states' approval rate rather than unusually favorable treatment of Republican states.

Not yet in OpenFEMA as of Oct 25, 2026: the tracker lists Republican-trifecta rejections for Nebraska (Aug 3, 2026) and Idaho (Sep 1, 2026), both under appeal.

---

*Source: Independent replication using FEMA public APIs. Inspired by POLITICO/E&E News reporting (Thomas Frank). State party data sourced from National Governors Association historical records and senate.gov membership.*
