# FEMA DISASTER DECLARATION APPROVAL RATES BY PRESIDENT & STATE PARTY

## Methodology

This is an independent replication of the POLITICO/E&E News analysis published by Thomas Frank. The script fetches live data directly from FEMA's public APIs and applies the same core methodology described in the original reporting.

### Data Sources

| Dataset | API Endpoint | Records Fetched |
|---|---|---|
| Approved declarations | `fema.gov/api/open/v2/DisasterDeclarationsSummaries` | ~46,220 |
| Denied requests | `fema.gov/api/open/v1/DeclarationDenials` | ~1,288 |

Both endpoints are paginated at 1,000 records per request; the script pages through all results exhaustively.

### Filtering to Natural Disasters Only

Only Major Disaster Declarations (`declarationType = 'DR'`) are included from the approvals API. Both datasets are then filtered to exclude non-natural incident types. Because the two APIs use different terminology for the same concepts, separate exclusion lists are applied:

**Approvals** — excluded `incidentType` values: `Biological`, `Terrorist`, `Chemical`, `Other`, `Toxic Substances`

**Denials** — excluded `requestedIncidentTypes` values: `Human Cause`, `Other`, `Toxic Substances`

(`"Terrorist"` in the approvals API = `"Human Cause"` in the denials API; `"Chemical"` = `"Toxic Substances"`.)

### Deduplication

- **Approvals:** The raw approvals dataset has one row per county, not per disaster. Records are deduplicated by `(disasterNumber, state)` so each state-level disaster declaration counts once.
- **Denials:** Only records with `currentRequestStatus = "Turndown"` are counted (excluding withdrawn, pending, or other statuses). Exact duplicates by `declarationRequestNumber` are collapsed to one record.

### State Party Classification

A state is classified as **Democratic-led** or **Republican-led** only when the governor and *both* U.S. senators all belong to the same party at the time of the request. Any state where the three offices are split across parties is classified as **Mixed** and excluded from the D/R comparison entirely.

Classifications are encoded in a hardcoded `STATE_PARTY_DATA` dictionary covering all 50 states for every year from 1981 through 2026 (~2,300 state-year entries). Sources: National Governors Association historical records and senate.gov membership data. The year used for classification is derived from the declaration date (approvals) or request date (denials).

Independents are treated as non-partisan: a state with an Independent governor or senator cannot form a D or R trifecta and is classified as Mixed.

### Presidential Term Boundaries

Records are assigned to a presidential term based on the declaration/request date using the following inauguration-day boundaries:

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

Three categories of records are tracked but excluded from the approval rate calculations:

1. **Territories and unclassified jurisdictions** (AS, DC, FM, GU, MH, MP, PR, PW, VI) — no governor/senator trifecta classification exists for these.
2. **Mixed-alignment states** — intentionally excluded per the methodology; these states had split partisan control at the time of the request.
3. **Out-of-range dates** — 1,267 records (618 approved, 649 denied) whose dates fall outside the Reagan–Trump 2 window. The denial database extends back to 1953, predating FEMA's creation in 1979 (records originated with predecessor agencies). These are pre-Reagan-era records and do not affect any presidential term's counts.

### Approval Rate Formula

For each combination of presidential term and state alignment:

```
approval rate = approved / (approved + denied)
```

---


# Output
```
Attempting to fetch denied declarations from FEMA API...
  Fetched 1000 records so far...
Fetched 1288 denial records

======================================================================
FEMA DISASTER DECLARATION APPROVAL RATES BY PRESIDENT & STATE PARTY
======================================================================

President     Party  Approved   Denied   Total     Rate
-------------------------------------------------------
Reagan          Dem        26       16      42    61.9%
Reagan          Rep        17        8      25    68.0%
H.W. Bush       Dem        28        5      33    84.8%
H.W. Bush       Rep        13        7      20    65.0%
Clinton         Dem        41       11      52    78.8%
Clinton         Rep        63       30      93    67.7%
Bush            Dem        54       17      71    76.1%
Bush            Rep        70       24      94    74.5%
Obama           Dem       108       19     127    85.0%
Obama           Rep       114       20     134    85.1%
Trump           Dem        49        4      53    92.5%
Trump           Rep       106       16     122    86.9%
Biden           Dem        74       18      92    80.4%
Biden           Rep       118       23     141    83.7%
Trump           Dem         4        8      12    33.3%
Trump           Rep        27        8      35    77.1%

======================================================================
EXCLUDED RECORDS
======================================================================

Territories / states not in alignment data  [122 approved, 16 denied, 138 total, 88.4% approval rate]
  State     Approved   Denied   Total     Rate
  --------------------------------------------
  AS              11        1      12    91.7%
  DC              14        1      15    93.3%
  FM              15        3      18    83.3%
  GU              14        2      16    87.5%
  MH               7        3      10    70.0%
  MP              15        5      20    75.0%
  PR              29        1      30    96.7%
  PW               1        0       1   100.0%
  VI              16        0      16   100.0%

Mixed-alignment states (split gov/senate — excluded by methodology)  [1167 approved, 315 denied, 1482 total, 78.7% approval rate]
  (top states by volume)
  State     Approved   Denied   Total     Rate
  --------------------------------------------
  FL              54       24      78    69.2%
  KY              51       13      64    79.7%
  MO              44       14      58    75.9%
  NC              44       12      56    78.6%
  CA              41       14      55    74.5%
  VT              49        3      52    94.2%
  LA              37       15      52    71.2%
  ME              44        5      49    89.8%
  TX              32       16      48    66.7%
  NY              33       14      47    70.2%

Out-of-range dates (pre-reagan): 1267 records (618 approved, 649 denied)
Chart saved to: fema_approval_rates.png


PARTY ALIGNMENT DATA COVERAGE:
----------------------------------------
States with alignment data: 50
Year range: 1981-2026
Total state-year entries: 2300


KEY STATE ALIGNMENTS (2025 - Trump 2nd term):
--------------------------------------------------
  Washington      (WA): D
  Illinois        (IL): D
  Colorado        (CO): D
  Maryland        (MD): D
  California      (CA): D
  Michigan        (MI): D
  Oklahoma        (OK): R
  Tennessee       (TN): R
  Alaska          (AK): R
  Nebraska        (NE): R
  Arkansas        (AR): R
  Kentucky        (KY): Mixed
  ```