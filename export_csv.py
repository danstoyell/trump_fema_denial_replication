"""
FEMA Disaster Declarations — Full Row-Level CSV Export
=======================================================
Exports every approved and denied FEMA disaster declaration record with:
  - All relevant API fields from both endpoints
  - Presidential term assignment (by decision/declaration date)
  - State party coding under all three classification modes
  - Election-result classification (2024 Trump vote share > 50% → R)
  - Declaration type flags (is_major_disaster, is_emergency, is_natural)
  - Record status (approved / denied / denied-non-turndown)

Approvals are deduplicated by (disasterNumber, state) so each state-level
disaster counts once (eliminates the county-row duplication in v2 API).
Denials include all statuses (not just Turndown) so nothing is hidden;
filter on `current_request_status` in the CSV if you want only Turndowns.

Output: fema_all_records.csv

Usage:
  python3 export_csv.py
  python3 export_csv.py --fema-web
"""

import sys
import csv
import argparse
import json
import urllib.request
import urllib.parse
sys.path.insert(0, ".")

from replicate_fema_analysis import (
    fetch_all_pages,
    fetch_all_fema_web,
    get_state_alignment,
    get_president,
    _parse_dt,
    _FEMA_WEB_TYPE_MAP,
)

OUTPUT_PATH = "fema_all_records.csv"

# 2024 presidential election — Trump vote share by state (official results)
TRUMP_2024 = {
    "AL": 64.57, "AK": 54.54, "AZ": 52.22, "AR": 64.20, "CA": 38.33,
    "CO": 43.14, "CT": 41.89, "DE": 41.79, "FL": 56.09, "GA": 50.73,
    "HI": 37.48, "ID": 66.89, "IL": 43.47, "IN": 58.58, "IA": 55.73,
    "KS": 57.16, "KY": 64.47, "LA": 60.22, "ME": 45.50, "MD": 34.08,
    "MA": 36.02, "MI": 49.73, "MN": 46.68, "MS": 60.89, "MO": 58.49,
    "MT": 58.39, "NE": 59.33, "NV": 50.59, "NH": 47.87, "NJ": 46.07,
    "NM": 45.85, "NY": 43.31, "NC": 50.86, "ND": 66.95, "OH": 55.13,
    "OK": 66.16, "OR": 40.96, "PA": 50.20, "RI": 41.77, "SC": 58.23,
    "SD": 63.43, "TN": 64.19, "TX": 56.14, "UT": 59.37, "VT": 32.32,
    "VA": 46.06, "WA": 39.01, "WV": 69.96, "WI": 49.59, "WY": 71.60,
}

EXCLUDE_APPROVAL_TYPES = {"Biological", "Terrorist", "Chemical", "Other", "Toxic Substances"}
EXCLUDE_DENIAL_TYPES   = {"Other", "Human Cause", "Toxic Substances"}


# ── Fetch ──────────────────────────────────────────────────────────────────

def fetch_approvals_v2():
    """Fetch DR + EM approvals from v2/DisasterDeclarationsSummaries with expanded fields."""
    records = []
    for decl_type in ("DR", "EM"):
        print(f"Fetching {decl_type} approvals (v2)...")
        skip = 0
        filter_val = urllib.parse.quote(f"declarationType eq '{decl_type}'")
        while True:
            url = (
                f"https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries"
                f"?$top=1000&$skip={skip}"
                f"&$select=disasterNumber,state,declarationDate,declarationType,"
                f"declarationTitle,incidentType,incidentBeginDate,incidentEndDate,"
                f"paProgramDeclared,iaProgramDeclared,hmProgramDeclared,ihProgramDeclared,"
                f"region,tribalRequest,declarationRequestNumber"
                f"&$filter={filter_val}"
                f"&$orderby=declarationDate%20asc"
            )
            with urllib.request.urlopen(urllib.request.Request(url)) as r:
                recs = json.loads(r.read())["DisasterDeclarationsSummaries"]
            if not recs:
                break
            records.extend(recs)
            if len(recs) < 1000:
                break
            skip += 1000
            print(f"  {len(records)} records so far...")
        print(f"  Done: {sum(1 for r in records if r['declarationType'] == decl_type)} {decl_type} rows")
    return records


def fetch_approvals_fema_web():
    """Fetch DR + EM approvals from v1/FemaWebDisasterDeclarations."""
    print("Fetching approvals (FemaWeb, DR+EM)...")
    # fetch_all_fema_web with include_emergency=True returns DR+EM after normalization
    recs = fetch_all_fema_web(include_emergency=True)
    # Map disasterName → declarationTitle for consistency
    for rec in recs:
        rec.setdefault("declarationTitle", rec.get("disasterName", ""))
    print(f"  {len(recs)} rows")
    return recs


def fetch_denials_full():
    """Fetch all denials from v1/DeclarationDenials with expanded fields."""
    print("Fetching denials...")
    all_recs = []
    skip = 0
    while True:
        url = (
            f"https://www.fema.gov/api/open/v1/DeclarationDenials"
            f"?$top=1000&$skip={skip}"
            f"&$select=declarationRequestNumber,stateAbbreviation,incidentName,"
            f"declarationRequestDate,requestedIncidentTypes,declarationRequestType,"
            f"currentRequestStatus,requestStatusDate,"
            f"ihProgramRequested,iaProgramRequested,paProgramRequested,hmProgramRequested,"
            f"region,tribalRequest"
            f"&$orderby=declarationRequestDate%20asc"
        )
        with urllib.request.urlopen(urllib.request.Request(url)) as r:
            recs = json.loads(r.read())["DeclarationDenials"]
        if not recs:
            break
        all_recs.extend(recs)
        if len(recs) < 1000:
            break
        skip += 1000
        print(f"  {len(all_recs)} records so far...")
    print(f"  {len(all_recs)} total denial rows")
    return all_recs


# ── Classification helpers ─────────────────────────────────────────────────

def election_alignment(state):
    pct = TRUMP_2024.get(state)
    if pct is None:
        return ""
    return "R" if pct > 50 else "D"


def fmt(v):
    """Normalize None/missing to empty string."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "1" if v else "0"
    return str(v).strip()


# ── Build rows ─────────────────────────────────────────────────────────────

def build_approval_row(rec, fema_web):
    state = rec.get("state", "").strip()
    date  = rec.get("declarationDate", "")
    decl_type = rec.get("declarationType", "")

    president       = get_president(date) or ""
    align_trifecta  = get_state_alignment(state, date) or ""
    align_governor  = get_state_alignment(state, date, governor_only=True) or ""
    align_two_thirds= get_state_alignment(state, date, two_thirds=True) or ""
    align_election  = election_alignment(state)

    incident_type = rec.get("incidentType", "")
    is_natural = "1" if incident_type not in EXCLUDE_APPROVAL_TYPES else "0"

    return {
        "record_type":              "approved",
        "approvals_source":         "fema_web_v1" if fema_web else "declarations_v2",
        # identifiers
        "disaster_number":          fmt(rec.get("disasterNumber")),
        "declaration_request_number": fmt(rec.get("declarationRequestNumber")),
        "state":                    state,
        "region":                   fmt(rec.get("region")),
        "tribal_request":           fmt(rec.get("tribalRequest")),
        # dates
        "declaration_date":         fmt(date)[:10],
        "incident_begin_date":      fmt(rec.get("incidentBeginDate", ""))[:10],
        "incident_end_date":        fmt(rec.get("incidentEndDate", ""))[:10],
        "request_date":             "",   # not available on approvals side
        "decision_date":            fmt(date)[:10],
        # event details
        "title":                    fmt(rec.get("declarationTitle", rec.get("disasterName", ""))),
        "incident_type":            fmt(incident_type),
        "requested_incident_types": "",
        "declaration_type":         fmt(decl_type),
        "request_type":             "",
        "current_request_status":   "Approved",
        # programs (approved side)
        "ia_program":               fmt(rec.get("iaProgramDeclared")),
        "pa_program":               fmt(rec.get("paProgramDeclared")),
        "hm_program":               fmt(rec.get("hmProgramDeclared")),
        "ih_program":               fmt(rec.get("ihProgramDeclared")),
        # derived flags
        "is_major_disaster":        "1" if decl_type == "DR" else "0",
        "is_emergency":             "1" if decl_type == "EM" else "0",
        "is_natural":               is_natural,
        # presidential / party coding
        "president":                president,
        "state_trifecta":           align_trifecta,
        "state_governor_only":      align_governor,
        "state_two_thirds":         align_two_thirds,
        "state_election_2024":      align_election,
        "trump_2024_pct":           fmt(TRUMP_2024.get(state, "")),
    }


def build_denial_row(rec):
    state = rec.get("stateAbbreviation", "").strip()
    req_date    = rec.get("declarationRequestDate", "")
    status_date = rec.get("requestStatusDate", "")
    # Use decision date (requestStatusDate) for presidential assignment, same as analyze()
    decision_date = status_date or req_date

    # Guard bogus years
    if decision_date and isinstance(decision_date, str) and len(decision_date) >= 4:
        if int(decision_date[:4]) < 1900:
            decision_date = req_date

    president        = get_president(decision_date) or "" if decision_date else ""
    align_trifecta   = get_state_alignment(state, decision_date) or "" if decision_date else ""
    align_governor   = get_state_alignment(state, decision_date, governor_only=True) or "" if decision_date else ""
    align_two_thirds = get_state_alignment(state, decision_date, two_thirds=True) or "" if decision_date else ""
    align_election   = election_alignment(state)

    req_type = rec.get("declarationRequestType", "")
    incident_types = rec.get("requestedIncidentTypes", "")
    is_major   = "1" if req_type == "Major Disaster" else "0"
    is_em      = "1" if req_type == "Emergency" else "0"
    is_natural = "1" if incident_types not in EXCLUDE_DENIAL_TYPES else "0"

    return {
        "record_type":              "denied",
        "approvals_source":         "",
        # identifiers
        "disaster_number":          "",
        "declaration_request_number": fmt(rec.get("declarationRequestNumber")),
        "state":                    state,
        "region":                   fmt(rec.get("region")),
        "tribal_request":           fmt(rec.get("tribalRequest")),
        # dates
        "declaration_date":         "",
        "incident_begin_date":      "",
        "incident_end_date":        "",
        "request_date":             fmt(req_date)[:10],
        "decision_date":            fmt(decision_date)[:10] if decision_date else "",
        # event details
        "title":                    fmt(rec.get("incidentName", "")),
        "incident_type":            "",
        "requested_incident_types": fmt(incident_types),
        "declaration_type":         "",
        "request_type":             fmt(req_type),
        "current_request_status":   fmt(rec.get("currentRequestStatus")),
        # programs (denied side — "requested")
        "ia_program":               fmt(rec.get("iaProgramRequested")),
        "pa_program":               fmt(rec.get("paProgramRequested")),
        "hm_program":               fmt(rec.get("hmProgramRequested")),
        "ih_program":               fmt(rec.get("ihProgramRequested")),
        # derived flags
        "is_major_disaster":        is_major,
        "is_emergency":             is_em,
        "is_natural":               is_natural,
        # presidential / party coding
        "president":                president,
        "state_trifecta":           align_trifecta,
        "state_governor_only":      align_governor,
        "state_two_thirds":         align_two_thirds,
        "state_election_2024":      align_election,
        "trump_2024_pct":           fmt(TRUMP_2024.get(state, "")),
    }


# ── Main ───────────────────────────────────────────────────────────────────

COLUMNS = [
    "record_type", "approvals_source",
    "disaster_number", "declaration_request_number",
    "state", "region", "tribal_request",
    "declaration_date", "incident_begin_date", "incident_end_date",
    "request_date", "decision_date",
    "title", "incident_type", "requested_incident_types",
    "declaration_type", "request_type", "current_request_status",
    "ia_program", "pa_program", "hm_program", "ih_program",
    "is_major_disaster", "is_emergency", "is_natural",
    "president",
    "state_trifecta", "state_governor_only", "state_two_thirds", "state_election_2024",
    "trump_2024_pct",
]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Export all FEMA disaster declaration records to a flat CSV."
    )
    parser.add_argument(
        "--fema-web",
        action="store_true",
        help="Use v1/FemaWebDisasterDeclarations (disaster-level) instead of "
             "v2/DisasterDeclarationsSummaries (county-level) for approvals.",
    )
    args = parser.parse_args()

    # Fetch
    if args.fema_web:
        raw_approvals = fetch_approvals_fema_web()
    else:
        raw_approvals = fetch_approvals_v2()

    raw_denials = fetch_denials_full()

    # Deduplicate approvals by (disasterNumber, state) — v2 has one row per county
    seen = set()
    approvals = []
    for rec in raw_approvals:
        key = (rec.get("disasterNumber"), rec.get("state", "").strip())
        if key not in seen:
            seen.add(key)
            approvals.append(rec)
    print(f"\nApprovals: {len(raw_approvals)} raw → {len(approvals)} after dedup")

    # Deduplicate denials by declarationRequestNumber
    seen_d = set()
    denials = []
    for rec in raw_denials:
        key = rec.get("declarationRequestNumber")
        if key not in seen_d:
            seen_d.add(key)
            denials.append(rec)
    print(f"Denials: {len(raw_denials)} raw → {len(denials)} after dedup")

    # Build rows
    rows = []
    for rec in approvals:
        rows.append(build_approval_row(rec, fema_web=args.fema_web))
    for rec in denials:
        rows.append(build_denial_row(rec))

    # Sort by decision_date, then record_type
    rows.sort(key=lambda r: (r["decision_date"] or r["request_date"] or "", r["record_type"]))

    # Write CSV
    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} rows to {OUTPUT_PATH}")
    print(f"  {len(approvals)} approvals + {len(denials)} denials")
