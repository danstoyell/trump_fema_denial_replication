"""
Export all Trump 2nd term FEMA disaster declaration requests — approved and denied —
classified by state party alignment, as a human-readable Markdown file.

Output: trump2_records.md
"""

import argparse
import json
import urllib.request
import urllib.parse
from collections import defaultdict
from replicate_fema_analysis import get_state_alignment, fetch_all_fema_web

CUTOFF = "2025-01-20"
OUTPUT_PATH = "trump2_records.md"


# ── Data fetching ──────────────────────────────────────────────────────────

def fetch_approvals():
    """
    Fetch DR declarations with declarationDate >= CUTOFF.
    API doesn't support date filtering, so we fetch newest-first and stop
    once we've passed the cutoff.
    """
    print("Fetching approved declarations (newest-first)...")
    raw = []
    skip = 0
    filter_val = urllib.parse.quote("declarationType eq 'DR'")
    while True:
        url = (
            f"https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries"
            f"?$top=1000&$skip={skip}"
            f"&$select=disasterNumber,state,declarationTitle,declarationDate,"
            f"incidentType,incidentBeginDate,incidentEndDate,"
            f"paProgramDeclared,iaProgramDeclared,hmProgramDeclared,ihProgramDeclared,"
            f"region,tribalRequest"
            f"&$filter={filter_val}"
            f"&$orderby=declarationDate%20desc"
        )
        with urllib.request.urlopen(url) as r:
            recs = json.loads(r.read())["DisasterDeclarationsSummaries"]
        if not recs:
            break
        in_range = [r for r in recs if r["declarationDate"][:10] >= CUTOFF]
        raw.extend(in_range)
        if any(r["declarationDate"][:10] < CUTOFF for r in recs):
            break
        skip += 1000
        print(f"  {len(raw)} records so far...")

    # Deduplicate by (disasterNumber, state) — raw data has one row per county
    seen = set()
    deduped = []
    for rec in raw:
        key = (rec["disasterNumber"], rec["state"])
        if key not in seen:
            seen.add(key)
            deduped.append(rec)

    print(f"Approvals: {len(raw)} rows → {len(deduped)} unique state-disasters")
    return deduped


def fetch_approvals_fema_web():
    """
    Fetch DR declarations from v1/FemaWebDisasterDeclarations, filter to
    Trump 2 term, and normalize into the same shape as fetch_approvals().
    Already one row per disaster — no deduplication needed.
    Field differences handled:
      - stateCode → state (done by fetch_all_fema_web via normalize_fema_web_record)
      - disasterName → declarationTitle (mapped here for the markdown renderer)
    """
    print("Fetching approved declarations from FemaWeb endpoint...")
    all_recs = fetch_all_fema_web(include_emergency=False)
    in_range = [r for r in all_recs if r.get("declarationDate", "")[:10] >= CUTOFF]
    # Map disasterName → declarationTitle so approval_table_rows() renders correctly
    for rec in in_range:
        rec.setdefault("declarationTitle", rec.get("disasterName", "—"))
    print(f"Approvals: {len(all_recs)} total → {len(in_range)} since {CUTOFF}")
    return in_range


def fetch_denials():
    """
    Fetch all DeclarationDenials and filter client-side for Trump 2 term.
    Full dataset is ~1,300 rows so a complete fetch is fast.
    """
    print("Fetching all denials...")
    all_recs = []
    skip = 0
    while True:
        url = (
            f"https://www.fema.gov/api/open/v1/DeclarationDenials"
            f"?$top=1000&$skip={skip}"
            f"&$select=stateAbbreviation,incidentName,declarationRequestDate,"
            f"requestedIncidentTypes,currentRequestStatus,requestStatusDate,"
            f"iaProgramRequested,paProgramRequested,hmProgramRequested,ihProgramRequested,"
            f"region,tribalRequest"
            f"&$orderby=declarationRequestDate%20asc"
        )
        with urllib.request.urlopen(url) as r:
            recs = json.loads(r.read())["DeclarationDenials"]
        if not recs:
            break
        all_recs.extend(recs)
        if len(recs) < 1000:
            break
        skip += 1000

    # Keep only confirmed turndowns in Trump 2 window
    filtered = [
        r for r in all_recs
        if r.get("currentRequestStatus") == "Turndown"
        and r.get("declarationRequestDate", "")[:10] >= CUTOFF
    ]
    print(f"Denials: {len(all_recs)} total → {len(filtered)} Turndowns since {CUTOFF}")
    return filtered


# ── Classification helpers ─────────────────────────────────────────────────

def classify(state, date):
    result = get_state_alignment(state, date)
    return result if result is not None else "Territory/Unknown"


def fmt_date(d):
    return d[:10] if d else "—"


def programs_approved(rec):
    parts = []
    if rec.get("ihProgramDeclared"): parts.append("IH")
    if rec.get("iaProgramDeclared"): parts.append("IA")
    if rec.get("paProgramDeclared"): parts.append("PA")
    if rec.get("hmProgramDeclared"): parts.append("HM")
    return ", ".join(parts) or "—"


def programs_denied(rec):
    parts = []
    if rec.get("ihProgramRequested"): parts.append("IH")
    if rec.get("iaProgramRequested"): parts.append("IA")
    if rec.get("paProgramRequested"): parts.append("PA")
    if rec.get("hmProgramRequested"): parts.append("HM")
    return ", ".join(parts) or "—"


# ── Markdown generation ────────────────────────────────────────────────────

PROGRAM_NOTE = (
    "**Programs:** IH = Individuals & Households, IA = Individual Assistance, "
    "PA = Public Assistance, HM = Hazard Mitigation"
)

def approval_table_rows(recs):
    recs_sorted = sorted(recs, key=lambda r: r["declarationDate"])
    lines = []
    lines.append("| Date | State | Title | Incident Type | Incident Begin | Programs |")
    lines.append("|---|---|---|---|---|---|")
    for r in recs_sorted:
        lines.append(
            f"| {fmt_date(r['declarationDate'])} "
            f"| {r['state']} "
            f"| {r.get('declarationTitle', '—')} "
            f"| {r.get('incidentType', '—')} "
            f"| {fmt_date(r.get('incidentBeginDate'))} "
            f"| {programs_approved(r)} |"
        )
    return "\n".join(lines)


def denial_table_rows(recs):
    recs_sorted = sorted(recs, key=lambda r: r["declarationRequestDate"])
    lines = []
    lines.append("| Request Date | State | Incident Name | Incident Type | Turndown Date | Programs Requested |")
    lines.append("|---|---|---|---|---|---|")
    for r in recs_sorted:
        lines.append(
            f"| {fmt_date(r['declarationRequestDate'])} "
            f"| {r.get('stateAbbreviation', '—').strip()} "
            f"| {r.get('incidentName', '—')} "
            f"| {r.get('requestedIncidentTypes', '—')} "
            f"| {fmt_date(r.get('requestStatusDate'))} "
            f"| {programs_denied(r)} |"
        )
    return "\n".join(lines)


def write_markdown(buckets, fema_web=False):
    lines = []
    lines.append("# FEMA Disaster Declarations — Trump 2nd Term (Jan 20, 2025–present)")
    lines.append("")
    lines.append(
        "Independent analysis of all approved and denied Major Disaster (DR) "
        "requests since January 20, 2025, classified by state party trifecta "
        "(governor + both U.S. senators from same party). Mixed and territory "
        "records are included at the bottom for completeness."
    )
    lines.append("")
    lines.append(PROGRAM_NOTE)
    lines.append("")

    # Summary table
    lines.append("## Summary")
    lines.append("")
    lines.append("| Alignment | Approved | Denied | Total | Approval Rate |")
    lines.append("|---|---|---|---|---|")
    for alignment in ["D", "R", "Mixed", "Territory/Unknown"]:
        a = len(buckets[alignment]["approved"])
        d = len(buckets[alignment]["denied"])
        t = a + d
        rate = f"{a/t*100:.1f}%" if t else "—"
        label = {"D": "Democratic trifecta", "R": "Republican trifecta",
                 "Mixed": "Mixed (excluded from main analysis)",
                 "Territory/Unknown": "Territory / Unknown"}[alignment]
        lines.append(f"| {label} | {a} | {d} | {t} | {rate} |")
    lines.append("")

    # Per-alignment sections
    for alignment, label, desc in [
        ("D",  "Democratic-Trifecta States",  "Governor + both senators are Democrats"),
        ("R",  "Republican-Trifecta States",  "Governor + both senators are Republicans"),
        ("Mixed", "Mixed-Alignment States", "Split partisan control — excluded from D/R comparison"),
        ("Territory/Unknown", "Territories & Unclassified", "DC, territories, tribal, or states outside alignment data"),
    ]:
        approved = buckets[alignment]["approved"]
        denied   = buckets[alignment]["denied"]
        total    = len(approved) + len(denied)
        rate     = f"{len(approved)/total*100:.1f}%" if total else "—"

        lines.append(f"---")
        lines.append("")
        lines.append(f"## {label}")
        lines.append(f"*{desc}*")
        lines.append("")
        lines.append(f"**{len(approved)} approved · {len(denied)} denied · {total} total · {rate} approval rate**")
        lines.append("")

        if approved:
            lines.append(f"### Approved ({len(approved)})")
            lines.append("")
            lines.append(approval_table_rows(approved))
            lines.append("")

        if denied:
            lines.append(f"### Denied ({len(denied)})")
            lines.append("")
            lines.append(denial_table_rows(denied))
            lines.append("")

    lines.append("---")
    lines.append("")
    approvals_api = ("v1/FemaWebDisasterDeclarations" if fema_web
                     else "v2/DisasterDeclarationsSummaries")
    lines.append(f"*Source: FEMA {approvals_api} (approvals) and v1/DeclarationDenials (denials). "
                 "State party classifications from independent research covering all 50 states, 1981–2026.*")

    with open(OUTPUT_PATH, "w") as f:
        f.write("\n".join(lines))
    print(f"\nSaved to {OUTPUT_PATH}")


# ── Main ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Export Trump 2nd term FEMA records to Markdown."
    )
    parser.add_argument(
        "--fema-web",
        action="store_true",
        help="Use v1/FemaWebDisasterDeclarations (disaster-level) instead of "
             "v2/DisasterDeclarationsSummaries (county-level) for approvals.",
    )
    args = parser.parse_args()

    approvals = fetch_approvals_fema_web() if args.fema_web else fetch_approvals()
    denials   = fetch_denials()

    buckets = defaultdict(lambda: {"approved": [], "denied": []})

    for rec in approvals:
        alignment = classify(rec["state"], rec["declarationDate"])
        buckets[alignment]["approved"].append(rec)

    for rec in denials:
        state     = rec.get("stateAbbreviation", "").strip()
        alignment = classify(state, rec["declarationRequestDate"])
        buckets[alignment]["denied"].append(rec)

    print("\nBucket summary:")
    for k, v in buckets.items():
        print(f"  {k}: {len(v['approved'])} approved, {len(v['denied'])} denied")

    write_markdown(buckets, fema_web=args.fema_web)
