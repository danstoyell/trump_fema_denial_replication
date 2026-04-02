"""
Trump Combined (1st + 2nd Term) FEMA Denial Rates by State Classification
=========================================================================
Bar chart showing denial rates for Democratic vs Republican states across
three classification methods:
  1. Election result  — state classified by 2024 Trump vote share (>50% = R)
  2. Governor only    — classified by governor's party at time of request
  3. Trifecta         — governor + both senators must all match (default)

Both Trump terms (Jan 20 2017 – Jan 20 2021 and Jan 20 2025 – present)
are combined into a single bucket.

Output: trump_combined_denial_rates.png
"""

import sys
import argparse
sys.path.insert(0, ".")

from replicate_fema_analysis import (
    fetch_all_pages,
    fetch_declarations_page,
    fetch_denials_page,
    fetch_all_fema_web,
    get_state_alignment,
    _parse_dt,
    STATE_PARTY_DATA,
)
from collections import defaultdict

OUTPUT_PATH = "trump_combined_denial_rates.png"

# Trump term boundaries
TRUMP1_START = "2017-01-20"
TRUMP1_END   = "2021-01-20"
TRUMP2_START = "2025-01-20"
TRUMP2_END   = "2029-01-20"

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


def in_trump_terms(date_str):
    """Return True if date falls within either Trump term."""
    if not date_str or not isinstance(date_str, str) or len(date_str) < 10:
        return False
    d = date_str[:10]
    return (TRUMP1_START <= d < TRUMP1_END) or (TRUMP2_START <= d < TRUMP2_END)


def election_alignment(state):
    """Classify state as D/R/Mixed based on 2024 Trump vote share (>50% = R)."""
    pct = TRUMP_2024.get(state)
    if pct is None:
        return None  # territory / unknown
    return "R" if pct > 50 else "D"


def fetch_data(fema_web=False):
    if fema_web:
        print("Fetching DR approvals from FemaWeb endpoint...")
        approved = fetch_all_fema_web(include_emergency=False)
        print(f"  {len(approved)} rows")
    else:
        print("Fetching DR approvals...")
        approved = fetch_all_pages(
            lambda skip: fetch_declarations_page(skip, declaration_type="DR"),
            "DisasterDeclarationsSummaries",
        )
        print(f"  {len(approved)} rows")

    print("Fetching denials...")
    denied = fetch_all_pages(fetch_denials_page, "DeclarationDenials")
    print(f"  {len(denied)} rows")
    return approved, denied


def compute_counts(approved_records, denied_records):
    """
    For each of the three classification methods, compute approved/denied
    counts for D and R states across both Trump terms combined.

    Returns dict: method -> alignment -> {"approved": n, "denied": n}
    """
    METHODS = ("election", "governor", "trifecta")

    counts = {m: defaultdict(lambda: {"approved": 0, "denied": 0}) for m in METHODS}

    # Deduplicate approvals by (disasterNumber, state)
    seen = set()
    approvals = []
    for rec in approved_records:
        key = (rec["disasterNumber"], rec["state"])
        if key not in seen:
            seen.add(key)
            approvals.append(rec)

    for rec in approvals:
        date = rec.get("declarationDate", "")
        if not in_trump_terms(date):
            continue
        state = rec["state"]
        for method in METHODS:
            if method == "election":
                alignment = election_alignment(state)
            elif method == "governor":
                alignment = get_state_alignment(state, date, governor_only=True)
            else:
                alignment = get_state_alignment(state, date)
            if alignment in ("D", "R"):
                counts[method][alignment]["approved"] += 1

    # Denials: Turndown + Major Disaster only
    denied_filtered = [
        r for r in denied_records
        if r.get("currentRequestStatus") == "Turndown"
        and r.get("declarationRequestType") == "Major Disaster"
    ]

    # Deduplicate by declarationRequestNumber
    seen_denied = set()
    deduped = []
    for rec in denied_filtered:
        key = rec.get("declarationRequestNumber")
        if key not in seen_denied:
            seen_denied.add(key)
            deduped.append(rec)

    for rec in deduped:
        date = rec.get("requestStatusDate") or rec.get("declarationRequestDate", "")
        if not in_trump_terms(date):
            continue
        state = rec.get("stateAbbreviation", "").strip()
        for method in METHODS:
            if method == "election":
                alignment = election_alignment(state)
            elif method == "governor":
                alignment = get_state_alignment(state, date, governor_only=True)
            else:
                alignment = get_state_alignment(state, date)
            if alignment in ("D", "R"):
                counts[method][alignment]["denied"] += 1

    return counts


def plot(counts, fema_web=False):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        import numpy as np
    except ImportError:
        print("matplotlib not installed: pip install matplotlib")
        return

    DEM_COLOR = "#2166c0"
    REP_COLOR = "#d6312b"

    METHODS = [
        ("election",  "Election\nResult"),
        ("governor",  "Governor\nOnly"),
        ("trifecta",  "Trifecta\n(All 3)"),
    ]

    bar_w = 0.3
    xs = np.arange(len(METHODS))

    fig, ax = plt.subplots(figsize=(9, 6))
    fig.patch.set_facecolor("white")

    for i, (method, label) in enumerate(METHODS):
        for j, (alignment, color) in enumerate([("D", DEM_COLOR), ("R", REP_COLOR)]):
            c = counts[method][alignment]
            total = c["approved"] + c["denied"]
            if total == 0:
                continue
            rate = c["denied"] / total * 100
            offset = -bar_w / 2 - 0.02 if alignment == "D" else bar_w / 2 + 0.02
            x = xs[i] + offset
            ax.bar(x, rate, bar_w, color=color, zorder=3)
            # Rate above bar
            ax.text(x, rate + 1.2, f"{rate:.1f}%",
                    ha="center", va="bottom", fontsize=10, fontweight="bold",
                    color=color)
            # n= inside bar
            ax.text(x, 2, f"n={total}\n({c['approved']}✓ {c['denied']}✗)",
                    ha="center", va="bottom", fontsize=7, color="white",
                    fontweight="bold", zorder=4)

    ax.set_xticks(xs)
    ax.set_xticklabels([label for _, label in METHODS], fontsize=12)
    ax.set_xlim(-0.6, xs[-1] + 0.6)
    ax.set_ylim(0, 100)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v)}%"))
    ax.tick_params(length=0)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#eeeeee", linewidth=0.7)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color("#bbbbbb")

    dem_patch = mpatches.Patch(color=DEM_COLOR, label="Democratic states")
    rep_patch = mpatches.Patch(color=REP_COLOR, label="Republican states")
    ax.legend(handles=[dem_patch, rep_patch], loc="upper right",
              fontsize=9, framealpha=0.9)

    approvals_src = ("v1/FemaWebDisasterDeclarations" if fema_web
                     else "v2/DisasterDeclarationsSummaries")

    fig.text(
        0.5, 0.97,
        "Trump FEMA Denial Rates by State Classification (Both Terms Combined)",
        fontsize=13, fontweight="bold", ha="center", va="top", color="#111111",
    )
    fig.text(
        0.5, 0.90,
        f"DR declarations only · Natural disasters only · Jan 2017–Jan 2021 and Jan 2025–present · {approvals_src}",
        fontsize=8.5, ha="center", va="top", color="#555555",
    )
    fig.text(
        0.02, 0.01,
        "Election result: state classified R if Trump 2024 vote share >50%, else D.\n"
        "Governor: classified by governor's party at time of request. "
        "Trifecta: governor + both senators must all match.\n"
        "Source: Independent replication using FEMA Disaster Declarations Summaries and "
        "Declaration Denials APIs. Inspired by POLITICO/E&E News reporting (Thomas Frank).",
        fontsize=7.5, va="bottom", ha="left", color="#888888", linespacing=1.5,
    )

    plt.subplots_adjust(left=0.1, right=0.95, top=0.87, bottom=0.18)
    plt.savefig(OUTPUT_PATH, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"Chart saved to {OUTPUT_PATH}")
    plt.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Trump combined (1st + 2nd term) FEMA denial rates by state classification."
    )
    parser.add_argument(
        "--fema-web",
        action="store_true",
        help="Use v1/FemaWebDisasterDeclarations (disaster-level) instead of "
             "v2/DisasterDeclarationsSummaries (county-level) for approvals.",
    )
    args = parser.parse_args()

    approved, denied = fetch_data(fema_web=args.fema_web)
    counts = compute_counts(approved, denied)

    print("\nResults (denial rate):")
    for method, label in [("election", "Election"), ("governor", "Governor"), ("trifecta", "Trifecta")]:
        for alignment in ["D", "R"]:
            c = counts[method][alignment]
            total = c["approved"] + c["denied"]
            if total == 0:
                print(f"  {label:10} {'Dem' if alignment=='D' else 'Rep'}: no data")
            else:
                rate = c["denied"] / total * 100
                print(f"  {label:10} {'Dem' if alignment=='D' else 'Rep'}: {rate:.1f}% denial "
                      f"(n={total}, {c['approved']} approved, {c['denied']} denied)")

    plot(counts, fema_web=args.fema_web)
