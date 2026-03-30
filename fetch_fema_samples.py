"""
fetch_fema_samples.py

Fetches 1000 rows from each FEMA API endpoint and writes:
  - fema_denials_raw.json        — raw denial records
  - fema_approvals_raw.json      — raw approval records (deduplicated to one per disaster/state)
  - fema_inspection_report.txt   — structured report for diagnosing denial deduplication

Run from any machine with access to fema.gov:
    python3 fetch_fema_samples.py
"""

import json
import urllib.request
import urllib.parse
import collections
import os

OUT_DIR = os.path.dirname(os.path.abspath(__file__))


# ── Fetch helpers ─────────────────────────────────────────────────────────────

def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "python-fema-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def fetch_n(base_url, entity_key, n=1000):
    """Page through the API until we have at least n records (or run out)."""
    records = []
    skip = 0
    page = 500  # FEMA caps at 1000; 500 is a safe page size
    while len(records) < n:
        want = min(page, n - len(records))
        sep = "&" if "?" in base_url else "?"
        url = f"{base_url}{sep}%24top={want}&%24skip={skip}"
        data = fetch_json(url)
        batch = data.get(entity_key, [])
        if not batch:
            break
        records.extend(batch)
        print(f"  fetched {len(records)} so far...")
        if len(batch) < want:
            break
        skip += want
    return records


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    lines = []  # report lines

    def log(s=""):
        print(s)
        lines.append(s)

    # ── 1. Denials ────────────────────────────────────────────────────────────
    print("Fetching denial records...")
    denials = fetch_n(
        "https://www.fema.gov/api/open/v1/DeclarationDenials"
        "?%24orderby=declarationRequestDate%20asc",
        "DeclarationDenials",
        n=1000,
    )
    with open(os.path.join(OUT_DIR, "fema_denials_raw.json"), "w") as f:
        json.dump(denials, f, indent=2)
    print(f"Saved {len(denials)} denial records.\n")

    # ── 2. Approvals ──────────────────────────────────────────────────────────
    print("Fetching approval records...")
    approvals_raw = fetch_n(
        "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries"
        "?%24filter=declarationType%20eq%20'DR'"
        "&%24orderby=declarationDate%20asc",
        "DisasterDeclarationsSummaries",
        n=1000,
    )
    with open(os.path.join(OUT_DIR, "fema_approvals_raw.json"), "w") as f:
        json.dump(approvals_raw, f, indent=2)
    print(f"Saved {len(approvals_raw)} raw approval records.\n")

    # Deduplicate approvals to one row per (disasterNumber, state)
    seen = set()
    approvals = []
    for r in approvals_raw:
        k = (r.get("disasterNumber"), r.get("state"))
        if k not in seen:
            seen.add(k)
            approvals.append(r)

    # ── 3. Report ─────────────────────────────────────────────────────────────
    log("=" * 70)
    log("FEMA API SAMPLE INSPECTION REPORT")
    log("=" * 70)

    # --- Denial fields --------------------------------------------------------
    log("\n── DENIAL RECORD FIELDS ──────────────────────────────────────────────")
    if denials:
        for k, v in denials[0].items():
            log(f"  {k:<40}  example: {json.dumps(v)[:60]}")

    # --- Approval fields (deduplicated) ---------------------------------------
    log("\n── APPROVAL RECORD FIELDS (post-dedup) ───────────────────────────────")
    if approvals:
        for k, v in approvals[0].items():
            log(f"  {k:<40}  example: {json.dumps(v)[:60]}")

    # --- Denial: key field population -----------------------------------------
    log("\n── DENIAL KEY FIELD POPULATION ───────────────────────────────────────")
    key_fields = [
        "declarationRequestNumber",
        "declarationRequestDate",
        "state",
        "incidentType",
        "fyDeclared",
        "ihDenied",
        "iaDenied",
        "paDenied",
        "hmDenied",
    ]
    n = len(denials)
    for field in key_fields:
        present  = sum(1 for r in denials if r.get(field) not in (None, "", "null"))
        log(f"  {field:<35}  present in {present:>4}/{n} rows  ({100*present/n:.0f}%)")

    # --- How many distinct (requestNumber, state) combos? ---------------------
    log("\n── DENIAL DEDUPLICATION ANALYSIS ─────────────────────────────────────")

    # Candidate key 1: declarationRequestNumber alone
    by_req_num = collections.Counter(
        r.get("declarationRequestNumber") for r in denials
    )
    dupes_req = {k: v for k, v in by_req_num.items() if v > 1 and k is not None}
    log(f"  Distinct declarationRequestNumbers : {len(by_req_num)}")
    log(f"  Numbers appearing >1 time          : {len(dupes_req)}")
    if dupes_req:
        # Show a sample duplicate group
        sample_num = next(iter(dupes_req))
        group = [r for r in denials if r.get("declarationRequestNumber") == sample_num]
        log(f"\n  Sample group for requestNumber={sample_num!r} ({len(group)} rows):")
        for r in group:
            row_fields = {k: r.get(k) for k in key_fields}
            log(f"    {json.dumps(row_fields)}")

    # Candidate key 2: (declarationRequestNumber, state)
    by_req_state = collections.Counter(
        (r.get("declarationRequestNumber"), r.get("state")) for r in denials
    )
    dupes_req_state = {k: v for k, v in by_req_state.items() if v > 1}
    log(f"\n  Distinct (requestNumber, state) pairs : {len(by_req_state)}")
    log(f"  Pairs appearing >1 time               : {len(dupes_req_state)}")
    if dupes_req_state:
        sample_key = next(iter(dupes_req_state))
        group = [r for r in denials
                 if (r.get("declarationRequestNumber"), r.get("state")) == sample_key]
        log(f"\n  Sample group for {sample_key} ({len(group)} rows):")
        for r in group:
            row_fields = {k: r.get(k) for k in key_fields}
            log(f"    {json.dumps(row_fields)}")

    # Candidate key 3: (requestNumber, state, incidentType)
    by_full = collections.Counter(
        (r.get("declarationRequestNumber"), r.get("state"), r.get("incidentType"))
        for r in denials
    )
    dupes_full = {k: v for k, v in by_full.items() if v > 1}
    log(f"\n  Distinct (requestNumber, state, incidentType) : {len(by_full)}")
    log(f"  Triples appearing >1 time                     : {len(dupes_full)}")

    # --- What differs between rows with the same request number? --------------
    log("\n── WHAT VARIES WITHIN A DENIAL GROUP? ────────────────────────────────")
    if dupes_req:
        sample_num = next(iter(dupes_req))
        group = [r for r in denials if r.get("declarationRequestNumber") == sample_num]
        all_keys = group[0].keys()
        varying = [k for k in all_keys if len({r.get(k) for r in group}) > 1]
        stable  = [k for k in all_keys if len({r.get(k) for r in group}) == 1]
        log(f"  Request {sample_num!r} — fields that VARY  : {varying}")
        log(f"  Request {sample_num!r} — fields that agree : {stable}")

    # --- Denial denial-flag combinations (ihDenied / iaDenied / paDenied / hmDenied) --
    log("\n── DENIAL FLAG COMBINATIONS ──────────────────────────────────────────")
    flag_fields = ["ihDenied", "iaDenied", "paDenied", "hmDenied"]
    combos = collections.Counter(
        tuple(r.get(f) for f in flag_fields) for r in denials
    )
    log(f"  {'ihDenied':<10} {'iaDenied':<10} {'paDenied':<10} {'hmDenied':<10}  count")
    log(f"  {'-'*55}")
    for combo, count in combos.most_common(20):
        log(f"  {str(combo[0]):<10} {str(combo[1]):<10} {str(combo[2]):<10} {str(combo[3]):<10}  {count}")

    # --- Rows per denial request (distribution) -------------------------------
    log("\n── ROWS-PER-REQUEST DISTRIBUTION (declarationRequestNumber) ──────────")
    freq = collections.Counter(by_req_num.values())
    for rows_per, num_requests in sorted(freq.items()):
        log(f"  {rows_per} row(s) per request : {num_requests:>5} requests")

    # --- Cross-check: does the same request appear in both approved & denied? --
    log("\n── REQUEST NUMBERS IN BOTH APPROVED AND DENIED? ──────────────────────")
    approved_req_nums = {r.get("declarationRequestNumber") for r in approvals
                         if r.get("declarationRequestNumber")}
    denied_req_nums   = {r.get("declarationRequestNumber") for r in denials
                         if r.get("declarationRequestNumber")}
    overlap = approved_req_nums & denied_req_nums
    log(f"  Approval request numbers in sample  : {len(approved_req_nums)}")
    log(f"  Denial  request numbers in sample   : {len(denied_req_nums)}")
    log(f"  Overlap (same number in both)       : {len(overlap)}")
    if overlap:
        log(f"  Sample overlap numbers: {list(overlap)[:5]}")

    # ── Write report ──────────────────────────────────────────────────────────
    report_path = os.path.join(OUT_DIR, "fema_inspection_report.txt")
    with open(report_path, "w") as f:
        f.write("\n".join(lines))
    print(f"\nReport written to: {report_path}")


if __name__ == "__main__":
    main()
