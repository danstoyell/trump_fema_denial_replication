"""
Request Behavior Analysis — Is It the Requests or the Decisionmaker?
=====================================================================
Investigates whether the partisan gap in FEMA denial rates under Trump's 2nd
term reflects changes in DECISION-MAKING or changes in REQUEST BEHAVIOR from
Democratic vs Republican states.

Key question: Did Democratic governors start submitting more requests, bigger
requests, or requests for different disaster types under Trump 2? Or did
requests stay constant while denial rates changed?

Requests are binned by declarationRequestDate (when the governor submitted),
not decision date — this isolates governor behavior from federal decisions.

Metrics:
  1. Requests per year (annualized) by party and term
  2. Denial rate by party and term
  3. Average programs requested per request (scope proxy — dollar amounts
     are not available from OpenFEMA APIs)
  4. Incident type mix of requests by party and term

Default methodology: trifecta classification, FemaWeb v1, DR+EM, all types.

Output: request_analysis.png

Flags:
  --fema-web           Use v1/FemaWebDisasterDeclarations (default: on)
  --governor-only      Classify by governor party alone
  --two-thirds         Classify as D/R if 2 of 3 offices match
  --major-only         DR only (default: DR+EM)
  --natural-only       Exclude non-natural incident types
"""

import sys
import argparse
import csv
import re
from collections import defaultdict
from datetime import date

sys.path.insert(0, ".")
from replicate_fema_analysis import (
    fetch_all_pages,
    fetch_declarations_page,
    fetch_denials_page,
    fetch_all_fema_web,
    get_state_alignment,
    get_president,
)

OUTPUT_PATH = "request_analysis.png"

PRESIDENTS = [
    ("Obama",    "2009-01-20", "2017-01-20"),
    ("Trump",    "2017-01-20", "2021-01-20"),
    ("Biden",    "2021-01-20", "2025-01-20"),
    ("Trump 2",  "2025-01-20", "2029-01-20"),
]
# Actual elapsed years for annualization (Trump 2 capped at today)
TODAY = date.today().isoformat()

def term_years(name):
    for n, start, end in PRESIDENTS:
        if n == name:
            effective_end = min(end, TODAY)
            d1 = date.fromisoformat(start)
            d2 = date.fromisoformat(effective_end)
            return max((d2 - d1).days / 365.25, 0.01)
    return 4.0

EXCLUDE_APPROVAL_TYPES = {"Biological", "Terrorist", "Chemical", "Other", "Toxic Substances"}
EXCLUDE_DENIAL_TYPES   = {"Other", "Human Cause", "Toxic Substances"}

INCIDENT_GROUPS = {
    "Flood/Storm":   {"Flood", "Severe Storm", "Coastal Storm", "Winter Storm",
                      "Tropical Storm", "Hurricane", "Typhoon", "Tornado",
                      "Straight-Line Winds", "Tropical Depression"},
    "Fire":          {"Fire"},
    "Other Natural": {"Earthquake", "Tsunami", "Drought", "Freezing",
                      "Snowstorm", "Landslide", "Mud/Landslide",
                      "Dam/Levee Break", "Fishing Losses"},
    "Non-natural":   {"Biological", "Terrorist", "Chemical", "Human Cause",
                      "Toxic Substances", "Other"},
}

def incident_group(itype):
    for group, types in INCIDENT_GROUPS.items():
        if itype in types:
            return group
    return "Other Natural"


# ── Fetch ──────────────────────────────────────────────────────────────────

def fetch_data(fema_web=True, major_only=False):
    if fema_web:
        print("Fetching approvals (FemaWeb v1)...")
        approved = fetch_all_fema_web(include_emergency=not major_only)
    else:
        types = ["DR"] if major_only else ["DR", "EM"]
        approved = []
        for t in types:
            print(f"Fetching {t} approvals (v2)...")
            recs = fetch_all_pages(
                lambda skip, t=t: fetch_declarations_page(skip, declaration_type=t),
                "DisasterDeclarationsSummaries",
            )
            approved.extend(recs)

    print("Fetching denials...")
    denied = fetch_all_pages(fetch_denials_page, "DeclarationDenials")
    print(f"  {len(denied)} rows")
    return approved, denied


def _safe_year(date_str):
    """Sanity-check year; canonical analyze() falls back on bogus years like '0999-'."""
    if not date_str or not isinstance(date_str, str) or len(date_str) < 4:
        return None
    try:
        return int(date_str[:4])
    except ValueError:
        return None


def president_for(date_str):
    """Wrap canonical get_president() with bogus-year guard."""
    yr = _safe_year(date_str)
    if yr is None or yr < 1900:
        return None
    return get_president(date_str)


# ── Pending-requests-as-denials augmentation ──────────────────────────────

_STATE_NAME_TO_ABBR = {
    "Alabama":"AL","Alaska":"AK","Arizona":"AZ","Arkansas":"AR","California":"CA",
    "Colorado":"CO","Connecticut":"CT","Delaware":"DE","Florida":"FL","Georgia":"GA",
    "Hawaii":"HI","Idaho":"ID","Illinois":"IL","Indiana":"IN","Iowa":"IA",
    "Kansas":"KS","Kentucky":"KY","Louisiana":"LA","Maine":"ME","Maryland":"MD",
    "Massachusetts":"MA","Michigan":"MI","Minnesota":"MN","Mississippi":"MS","Missouri":"MO",
    "Montana":"MT","Nebraska":"NE","Nevada":"NV","New Hampshire":"NH","New Jersey":"NJ",
    "New Mexico":"NM","New York":"NY","North Carolina":"NC","North Dakota":"ND","Ohio":"OH",
    "Oklahoma":"OK","Oregon":"OR","Pennsylvania":"PA","Rhode Island":"RI","South Carolina":"SC",
    "South Dakota":"SD","Tennessee":"TN","Texas":"TX","Utah":"UT","Vermont":"VT",
    "Virginia":"VA","Washington":"WA","West Virginia":"WV","Wisconsin":"WI","Wyoming":"WY",
}

def load_pending_as_denials(csv_path, threshold_days=30,
                             governor_only=False, two_thirds=False):
    """
    Read a third-party Disaster Tracker CSV (manually compiled list of pending
    Major Disaster requests) and return a list of synthetic denial buckets:
        [(president, alignment, state_abbr, submission_iso), ...]
    Pending tribal requests are skipped — they have no state-party alignment.
    Pending requests for which alignment is None/Mixed are skipped from the
    D/R buckets but reported in the console output.
    """
    rows = []
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r.get("Major Disaster Declaration Decision") != "Pending":
                continue
            m = re.match(r"(\d+)", r.get("Waiting Period", ""))
            if not m or int(m.group(1)) <= threshold_days:
                continue
            name = r.get("State/Tribe", "").strip()
            abbr = _STATE_NAME_TO_ABBR.get(name)
            req_raw = r.get("Major Disaster Declaration Request", "").strip()
            if not req_raw:
                continue
            mo, da, yr = req_raw.split("/")
            req_iso = f"{yr}-{int(mo):02d}-{int(da):02d}"
            rows.append({
                "name": name, "abbr": abbr, "req_iso": req_iso,
                "days": int(m.group(1)),
            })

    buckets = []
    skipped_tribal, skipped_mixed = [], []
    for row in rows:
        if row["abbr"] is None:
            skipped_tribal.append(row)
            continue
        pres = president_for(row["req_iso"])
        align = get_state_alignment(row["abbr"], row["req_iso"],
                                    governor_only=governor_only,
                                    two_thirds=two_thirds)
        if not pres or align not in ("D", "R"):
            skipped_mixed.append({**row, "align": align})
            continue
        buckets.append((pres, align, row["abbr"], row["req_iso"], row["days"]))

    return buckets, skipped_tribal, skipped_mixed


# ── Compute stats ──────────────────────────────────────────────────────────

def compute_denial_stats(approved, denied, governor_only=False, two_thirds=False,
                         major_only=False, natural_only=False):
    """
    Compute approval/denial counts keyed by president-at-DECISION date.
    Used only for Panel 2 — isolates who was making the decision, not who
    submitted the request. Approvals use declarationDate; denials use
    requestStatusDate (FEMA's final decision date).
    Returns dict: {(president, alignment): {"approved": n, "denied": n}}
    """
    seen = set()
    approvals = []
    for rec in approved:
        key = (rec.get("disasterNumber"), rec.get("state", "").strip())
        if key not in seen:
            seen.add(key)
            approvals.append(rec)

    denied_filtered = [r for r in denied if r.get("currentRequestStatus") == "Turndown"]
    if major_only:
        denied_filtered = [r for r in denied_filtered
                           if r.get("declarationRequestType") == "Major Disaster"]

    seen_d = set()
    deduped_denials = []
    for r in denied_filtered:
        k = r.get("declarationRequestNumber")
        if k not in seen_d:
            seen_d.add(k)
            deduped_denials.append(r)

    dstats = defaultdict(lambda: {"approved": 0, "denied": 0})

    for rec in approvals:
        decision_date = rec.get("declarationDate", "")
        state = rec.get("state", "").strip()
        itype = rec.get("incidentType", "")
        if natural_only and itype in EXCLUDE_APPROVAL_TYPES:
            continue
        pres = president_for(decision_date)
        alignment = get_state_alignment(state, decision_date,
                                        governor_only=governor_only,
                                        two_thirds=two_thirds)
        if not pres or alignment not in ("D", "R"):
            continue
        dstats[(pres, alignment)]["approved"] += 1

    for rec in deduped_denials:
        decision_date = rec.get("requestStatusDate") or rec.get("declarationRequestDate", "")
        state = rec.get("stateAbbreviation", "").strip()
        itype = rec.get("requestedIncidentTypes", "")
        if natural_only and itype in EXCLUDE_DENIAL_TYPES:
            continue
        pres = president_for(decision_date)
        alignment = get_state_alignment(state, decision_date,
                                        governor_only=governor_only,
                                        two_thirds=two_thirds)
        if not pres or alignment not in ("D", "R"):
            continue
        dstats[(pres, alignment)]["denied"] += 1

    return dict(dstats)


def compute_stats(approved, denied, governor_only=False, two_thirds=False,
                  major_only=False, natural_only=False):
    """
    Returns dict keyed by (president, alignment) with:
      requests: total requests (approved + denied)
      approved: count approved
      denied: count denied
      programs_total: sum of programs requested across all requests
      incident_types: Counter of incident group labels
    """
    from collections import Counter

    # Deduplicate approvals by (disasterNumber, state) — v2 is county-level
    seen = set()
    approvals = []
    for rec in approved:
        key = (rec.get("disasterNumber"), rec.get("state", "").strip())
        if key not in seen:
            seen.add(key)
            approvals.append(rec)

    # Filter denials: Turndown + matching declaration type
    denied_filtered = [r for r in denied
                       if r.get("currentRequestStatus") == "Turndown"]
    if major_only:
        denied_filtered = [r for r in denied_filtered
                           if r.get("declarationRequestType") == "Major Disaster"]
    # else include both Major Disaster and Emergency

    # Dedup denials
    seen_d = set()
    deduped_denials = []
    for r in denied_filtered:
        k = r.get("declarationRequestNumber")
        if k not in seen_d:
            seen_d.add(k)
            deduped_denials.append(r)

    stats = defaultdict(lambda: {
        "requests": 0,
        "approved": 0,
        "denied": 0,
        "programs_total": 0,
        "incident_types": Counter(),
    })

    # IA + PA + HM only. IH (Individuals & Households) overlaps with IA in FEMA's
    # data model and would double-count; excluded for both sides for symmetry.
    def programs_count_approval(rec):
        return sum([
            bool(rec.get("iaProgramDeclared")),
            bool(rec.get("paProgramDeclared")),
            bool(rec.get("hmProgramDeclared")),
        ])

    def programs_count_denial(rec):
        return sum([
            bool(rec.get("iaProgramRequested")),
            bool(rec.get("paProgramRequested")),
            bool(rec.get("hmProgramRequested")),
        ])

    for rec in approvals:
        req_date = (rec.get("declarationRequestDate") or rec.get("declarationDate", ""))
        state    = rec.get("state", "").strip()
        itype    = rec.get("incidentType", "")

        if natural_only and itype in EXCLUDE_APPROVAL_TYPES:
            continue

        pres      = president_for(req_date)
        alignment = get_state_alignment(state, req_date,
                                        governor_only=governor_only,
                                        two_thirds=two_thirds)
        if not pres or alignment not in ("D", "R"):
            continue

        key = (pres, alignment)
        stats[key]["requests"]        += 1
        stats[key]["approved"]        += 1
        stats[key]["programs_total"]  += programs_count_approval(rec)
        stats[key]["incident_types"][incident_group(itype)] += 1

    for rec in deduped_denials:
        req_date = (rec.get("declarationRequestDate") or "")
        state    = rec.get("stateAbbreviation", "").strip()
        itype    = rec.get("requestedIncidentTypes", "")

        if natural_only and itype in EXCLUDE_DENIAL_TYPES:
            continue

        pres      = president_for(req_date)
        alignment = get_state_alignment(state, req_date,
                                        governor_only=governor_only,
                                        two_thirds=two_thirds)
        if not pres or alignment not in ("D", "R"):
            continue

        key = (pres, alignment)
        stats[key]["requests"]       += 1
        stats[key]["denied"]         += 1
        stats[key]["programs_total"] += programs_count_denial(rec)
        stats[key]["incident_types"][incident_group(itype)] += 1

    return dict(stats)


# ── Plot ───────────────────────────────────────────────────────────────────

def plot(stats, denial_stats, fema_web=True, governor_only=False, two_thirds=False,
         major_only=False, natural_only=False,
         pending_note=None, output_path=None):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("matplotlib required: pip install matplotlib")
        return

    TERMS   = ["Obama", "Trump", "Biden", "Trump 2"]
    DEM_CLR = "#2166c0"
    REP_CLR = "#d6312b"
    GROUPS  = ["Flood/Storm", "Fire", "Other Natural", "Non-natural"]
    GROUP_COLORS = ["#4393c3", "#d73027", "#91cf60", "#999999"]

    bar_w = 0.32
    xs    = np.arange(len(TERMS))

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.patch.set_facecolor("white")

    def safe(key, field):
        return stats.get(key, {}).get(field, 0)

    # ── Panel 1: Requests per year (annualized) ────────────────────────────
    ax = axes[0, 0]
    for j, (party, color) in enumerate([("D", DEM_CLR), ("R", REP_CLR)]):
        ys = []
        ns = []
        for term in TERMS:
            n = safe((term, party), "requests")
            yrs = term_years(term)
            ys.append(n / yrs)
            ns.append(n)
        bars = ax.bar(xs + (j - 0.5) * (bar_w + 0.02), ys, bar_w, color=color,
                      zorder=3, label="Dem states" if party == "D" else "Rep states")
        for i, (bar, n) in enumerate(zip(bars, ns)):
            if n > 0:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + 0.3,
                        f"n={n}", ha="center", va="bottom", fontsize=7, color=color)
    ax.set_xticks(xs)
    ax.set_xticklabels(TERMS, fontsize=10)
    ax.set_ylabel("Requests per year (annualized)", fontsize=9)
    ax.set_title("Request Frequency\nDid governors submit more or fewer requests per year?",
                 fontsize=11, fontweight="bold")
    ax.legend(fontsize=8)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#eeeeee", linewidth=0.7)
    for sp in ("top","right","left"):
        ax.spines[sp].set_visible(False)

    # ── Panel 2: Denial rate (by president-at-DECISION date) ──────────────
    ax = axes[0, 1]
    for j, (party, color) in enumerate([("D", DEM_CLR), ("R", REP_CLR)]):
        ys = []
        for term in TERMS:
            d = denial_stats.get((term, party), {})
            app = d.get("approved", 0)
            den = d.get("denied", 0)
            total = app + den
            ys.append(den / total * 100 if total else 0)
        ax.bar(xs + (j - 0.5) * (bar_w + 0.02), ys, bar_w, color=color, zorder=3)
        for i, (x_pos, y) in enumerate(zip(xs + (j - 0.5) * (bar_w + 0.02), ys)):
            if y > 0:
                ax.text(x_pos, y + 0.5, f"{y:.1f}%",
                        ha="center", va="bottom", fontsize=7, color=color)
    ax.set_xticks(xs)
    ax.set_xticklabels(TERMS, fontsize=10)
    ax.set_ylabel("Denial rate (%)", fontsize=9)
    ax.set_title("Denial Rate\n(by president who signed the decision)",
                 fontsize=11, fontweight="bold")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v)}%"))
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#eeeeee", linewidth=0.7)
    for sp in ("top","right","left"):
        ax.spines[sp].set_visible(False)

    # ── Panel 3: Avg programs requested per request ────────────────────────
    ax = axes[1, 0]
    for j, (party, color) in enumerate([("D", DEM_CLR), ("R", REP_CLR)]):
        ys = []
        for term in TERMS:
            req  = safe((term, party), "requests")
            prog = safe((term, party), "programs_total")
            ys.append(prog / req if req else 0)
        bars = ax.bar(xs + (j - 0.5) * (bar_w + 0.02), ys, bar_w, color=color, zorder=3)
        for bar, y in zip(bars, ys):
            if y > 0:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + 0.01,
                        f"{y:.2f}", ha="center", va="bottom", fontsize=7, color=color)
    ax.set_xticks(xs)
    ax.set_xticklabels(TERMS, fontsize=10)
    ax.set_ylabel("Avg programs per request (IA+PA+HM)", fontsize=9)
    ax.set_title("Request Scope\nDid governors ask for more assistance types per request?",
                 fontsize=11, fontweight="bold")
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#eeeeee", linewidth=0.7)
    for sp in ("top","right","left"):
        ax.spines[sp].set_visible(False)

    # ── Panel 4: Incident type mix (Biden vs Trump 2, D vs R) ─────────────
    ax = axes[1, 1]
    combos   = [("Biden","D"), ("Biden","R"), ("Trump 2","D"), ("Trump 2","R")]
    combo_xs = np.arange(len(combos))
    combo_labels = ["Biden\nDem", "Biden\nRep", "Trump 2\nDem", "Trump 2\nRep"]
    bottoms = np.zeros(len(combos))
    for grp, gcolor in zip(GROUPS, GROUP_COLORS):
        heights = []
        for (term, party) in combos:
            req   = safe((term, party), "requests")
            count = stats.get((term, party), {}).get("incident_types", {}).get(grp, 0)
            heights.append(count / req * 100 if req else 0)
        ax.bar(combo_xs, heights, bottom=bottoms, color=gcolor, zorder=3,
               label=grp, width=0.55)
        for i, (h, b) in enumerate(zip(heights, bottoms)):
            if h > 5:
                ax.text(combo_xs[i], b + h / 2, f"{h:.0f}%",
                        ha="center", va="center", fontsize=7, color="white",
                        fontweight="bold")
        bottoms += np.array(heights)
    ax.set_xticks(combo_xs)
    ax.set_xticklabels(combo_labels, fontsize=10)
    ax.set_ylabel("Share of requests (%)", fontsize=9)
    ax.set_title("Incident Type Mix of Requests\n(Biden vs Trump 2)",
                 fontsize=11, fontweight="bold")
    ax.set_ylim(0, 110)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v)}%"))
    ax.legend(fontsize=8, loc="upper center",
              bbox_to_anchor=(0.5, -0.12), ncol=4, framealpha=0.9)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#eeeeee", linewidth=0.7)
    for sp in ("top","right","left"):
        ax.spines[sp].set_visible(False)

    # ── Titles and labels ──────────────────────────────────────────────────
    class_label = ("Governor only" if governor_only
                   else "Two-thirds" if two_thirds
                   else "Trifecta")
    scope_label = "DR only" if major_only else "DR+EM"
    type_label  = "Natural disasters only" if natural_only else "All incident types"
    src_label   = ("v1/FemaWebDisasterDeclarations" if fema_web
                   else "v2/DisasterDeclarationsSummaries")

    fig.suptitle(
        "Is It the Requests or the Decisionmaker?",
        fontsize=13, fontweight="bold", y=1.02,
    )
    fig.text(
        0.5, 0.995,
        f"FEMA Request Behavior by State Party Alignment, Obama–Trump 2",
        fontsize=9, color="#555555", ha="center", va="top",
    )
    fig.text(
        0.5, 0.972,
        f"Classification: {class_label} · {scope_label} · {type_label} · "
        f"Requests binned by submission date · {src_label}",
        fontsize=8.5, color="#555555", ha="center", va="top",
    )
    fig.text(
        0.02, 0.01,
        "Request volume annualized by actual elapsed days in each term. "
        "Scope proxy: count of IA/PA/HM program flags per request (dollar amounts not in OpenFEMA).\n"
        "Trump 2 denial counts reflect final-appeal decision dates published by OpenFEMA; pending appeals "
        "will appear later and may raise these numbers further.\n"
        "Source: Independent replication using FEMA APIs. Inspired by POLITICO/E&E News reporting (Thomas Frank).",
        fontsize=7.5, va="bottom", ha="left", color="#888888", linespacing=1.5,
    )

    if pending_note:
        axes[0, 1].text(
            0.5, -0.18, pending_note,
            transform=axes[0, 1].transAxes,
            fontsize=8.5, ha="center", va="top",
            color="#a02020", fontweight="bold", wrap=True,
        )

    out_path = output_path or OUTPUT_PATH
    plt.tight_layout(rect=[0, 0.05, 1, 1.0])
    plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"Chart saved to {out_path}")
    plt.close()


# ── Main ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Analyze whether partisan FEMA gaps reflect request behavior "
                    "or decision-making changes."
    )
    parser.add_argument("--fema-web", action="store_true", default=True,
                        help="Use v1/FemaWebDisasterDeclarations (default: on)")
    parser.add_argument("--no-fema-web", dest="fema_web", action="store_false",
                        help="Use v2/DisasterDeclarationsSummaries instead")
    parser.add_argument("--governor-only", action="store_true",
                        help="Classify states by governor party alone")
    parser.add_argument("--two-thirds", action="store_true",
                        help="Classify as D/R if 2 of 3 offices match")
    parser.add_argument("--major-only", action="store_true",
                        help="DR only (default: DR+EM)")
    parser.add_argument("--natural-only", action="store_true",
                        help="Exclude non-natural incident types")
    parser.add_argument("--include-pending",
                        metavar="CSV",
                        help="Path to Disaster Tracker CSV; pending requests >N days "
                             "are treated as denials in the Trump 2 column. "
                             "Writes to request_analysis_with_pending.png.")
    parser.add_argument("--pending-threshold-days", type=int, default=30,
                        help="Days a request can be pending before being counted "
                             "as a denial under --include-pending. Default 30.")
    args = parser.parse_args()

    approved, denied = fetch_data(fema_web=args.fema_web, major_only=args.major_only)

    stats = compute_stats(
        approved, denied,
        governor_only=args.governor_only,
        two_thirds=args.two_thirds,
        major_only=args.major_only,
        natural_only=args.natural_only,
    )

    denial_stats = compute_denial_stats(
        approved, denied,
        governor_only=args.governor_only,
        two_thirds=args.two_thirds,
        major_only=args.major_only,
        natural_only=args.natural_only,
    )

    print("\nRequest stats by president and party (submission date):")
    for term in ["Obama", "Trump", "Biden", "Trump 2"]:
        yrs = term_years(term)
        for party in ["D", "R"]:
            s = stats.get((term, party), {})
            req = s.get("requests", 0)
            den = s.get("denied", 0)
            prog = s.get("programs_total", 0)
            if req == 0:
                continue
            label = "Dem" if party == "D" else "Rep"
            print(f"  {term:8} {label}: {req:4} requests ({req/yrs:.1f}/yr)  "
                  f"denial={den/req*100:.1f}%  "
                  f"avg_programs={prog/req:.2f}")

    print("\nDenial rates by president and party (decision date):")
    for term in ["Obama", "Trump", "Biden", "Trump 2"]:
        for party in ["D", "R"]:
            d = denial_stats.get((term, party), {})
            app = d.get("approved", 0)
            den = d.get("denied", 0)
            total = app + den
            if total == 0:
                continue
            label = "Dem" if party == "D" else "Rep"
            print(f"  {term:8} {label}: {den/total*100:.1f}% denied (n={total})")

    pending_note = None
    out_path = OUTPUT_PATH
    if args.include_pending:
        thresh = args.pending_threshold_days
        buckets, tribal, mixed = load_pending_as_denials(
            args.include_pending, threshold_days=thresh,
            governor_only=args.governor_only, two_thirds=args.two_thirds,
        )
        added = defaultdict(int)
        for pres, align, abbr, req_iso, days in buckets:
            denial_stats.setdefault((pres, align), {"approved": 0, "denied": 0})
            denial_stats[(pres, align)]["denied"] += 1
            added[(pres, align)] += 1

        print(f"\n── Augmenting with pending >{thresh}d as denials ────────────────")
        print(f"  Source: {args.include_pending}")
        print(f"  Added to denial buckets: {dict(added)}")
        print(f"  Skipped (tribal, no state alignment): {len(tribal)}")
        print(f"  Skipped (mixed / no alignment): {len(mixed)}")
        if mixed:
            for m in mixed:
                print(f"    {m['name']} ({m['abbr']}) — alignment={m['align']}")

        print("\nDenial rates after augmentation (decision date):")
        for term in ["Trump 2"]:
            for party in ["D", "R"]:
                d = denial_stats.get((term, party), {})
                tot = d["approved"] + d["denied"]
                if tot == 0:
                    continue
                lbl = "Dem" if party == "D" else "Rep"
                print(f"  {term:8} {lbl}: {d['denied']/tot*100:.1f}% denied "
                      f"(n={tot}, +{added.get((term,party),0)} pending)")

        n_added = sum(added.values())
        n_tribal = len(tribal)
        n_mixed  = len(mixed)
        pending_note = (
            f"Trump 2 column augmented: +{n_added} pending >{thresh}-day requests counted as denials "
            f"(+{n_tribal} tribal and +{n_mixed} mixed-gov requests excluded)"
        )
        out_path = "request_analysis_with_pending.png"

    plot(stats, denial_stats,
         fema_web=args.fema_web,
         governor_only=args.governor_only,
         two_thirds=args.two_thirds,
         major_only=args.major_only,
         natural_only=args.natural_only,
         pending_note=pending_note,
         output_path=out_path)
