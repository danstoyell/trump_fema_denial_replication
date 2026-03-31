"""
Trump 2nd Term FEMA Denial Rate Sensitivity Analysis
=====================================================
Generates a grouped bar chart showing the Democratic and Republican denial rates
(1 - approval rate) for Trump's 2nd term under every combination of methodology
flags implemented in replicate_fema_analysis.py.

Axes of variation:
  Classification: trifecta (default) | governor-only | two-thirds
  Declaration scope: DR only (default) | DR + EM
  Incident types: natural disasters only (default) | all types

3 × 2 × 2 = 12 combinations, each shown as a Dem/Rep bar pair.

Output: trump2_sensitivity.png
"""

import sys
import argparse
sys.path.insert(0, ".")

from replicate_fema_analysis import (
    fetch_all_pages,
    fetch_declarations_page,
    fetch_denials_page,
    fetch_all_fema_web,
    analyze,
)

OUTPUT_PATH = "trump2_sensitivity.png"

# ── Fetch all data up front ────────────────────────────────────────────────

def fetch_data(fema_web=False):
    if fema_web:
        print("Fetching DR approvals from FemaWeb endpoint...")
        dr_approved = fetch_all_fema_web(include_emergency=False)
        print(f"  {len(dr_approved)} rows")
        print("Fetching EM approvals from FemaWeb endpoint...")
        em_approved = fetch_all_fema_web(include_emergency=True)
        # fetch_all_fema_web with include_emergency=True returns DR+EM;
        # subtract DR-only to get EM-only for the split used by run_combination
        dr_nums = {r["disasterNumber"] for r in dr_approved}
        em_approved = [r for r in em_approved if r["disasterNumber"] not in dr_nums]
        print(f"  {len(em_approved)} EM-only rows")
    else:
        print("Fetching DR approvals...")
        dr_approved = fetch_all_pages(
            lambda skip: fetch_declarations_page(skip, declaration_type="DR"),
            "DisasterDeclarationsSummaries",
        )
        print(f"  {len(dr_approved)} rows")

        print("Fetching EM approvals...")
        em_approved = fetch_all_pages(
            lambda skip: fetch_declarations_page(skip, declaration_type="EM"),
            "DisasterDeclarationsSummaries",
        )
        print(f"  {len(em_approved)} rows")

    print("Fetching all denials...")
    denied = fetch_all_pages(fetch_denials_page, "DeclarationDenials")
    print(f"  {len(denied)} rows")

    return dr_approved, em_approved, denied


# ── Extract Trump 2 denial rate for a given combination ───────────────────

def denial_rate(counts, alignment):
    c = counts.get("Trump 2", {}).get(alignment, {"approved": 0, "denied": 0})
    total = c["approved"] + c["denied"]
    if total == 0:
        return None, 0
    return (1 - c["approved"] / total) * 100, total


# ── Build all 12 combinations ─────────────────────────────────────────────

COMBINATIONS = [
    # (label_line1, label_line2, classification, include_emergency, all_types)
    ("Trifecta",    "DR · Natural",  "trifecta",    False, False),
    ("Trifecta",    "DR · All",      "trifecta",    False, True),
    ("Trifecta",    "DR+EM · Natural","trifecta",   True,  False),
    ("Trifecta",    "DR+EM · All",   "trifecta",    True,  True),
    ("Gov Only",    "DR · Natural",  "governor",    False, False),
    ("Gov Only",    "DR · All",      "governor",    False, True),
    ("Gov Only",    "DR+EM · Natural","governor",   True,  False),
    ("Gov Only",    "DR+EM · All",   "governor",    True,  True),
    ("Two-Thirds",  "DR · Natural",  "two_thirds",  False, False),
    ("Two-Thirds",  "DR · All",      "two_thirds",  False, True),
    ("Two-Thirds",  "DR+EM · Natural","two_thirds", True,  False),
    ("Two-Thirds",  "DR+EM · All",   "two_thirds",  True,  True),
]


def run_combination(dr_approved, em_approved, denied,
                    classification, include_emergency, all_types):
    approved = dr_approved + em_approved if include_emergency else dr_approved
    counts = analyze(
        approved,
        denied,
        all_types=all_types,
        governor_only=(classification == "governor"),
        two_thirds=(classification == "two_thirds"),
        include_emergency=include_emergency,
    )
    return counts


# ── Chart ─────────────────────────────────────────────────────────────────

def plot(results, fema_web=False):
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
    DEM_LIGHT = "#a8c4e8"
    REP_LIGHT = "#eda9a6"

    n = len(results)
    xs = np.arange(n)
    bar_w = 0.35

    fig, ax = plt.subplots(figsize=(16, 6.5))
    fig.patch.set_facecolor("white")

    dem_bars = []
    rep_bars = []
    x_labels = []

    for i, (label1, label2, classification, include_emergency, all_types,
             d_rate, d_total, r_rate, r_total) in enumerate(results):

        d_color = DEM_COLOR if d_rate is not None else DEM_LIGHT
        r_color = REP_COLOR if r_rate is not None else REP_LIGHT
        d_val = d_rate if d_rate is not None else 0
        r_val = r_rate if r_rate is not None else 0

        b_d = ax.bar(i - bar_w / 2, d_val, bar_w, color=d_color, zorder=3)
        b_r = ax.bar(i + bar_w / 2, r_val, bar_w, color=r_color, zorder=3)
        dem_bars.append(b_d)
        rep_bars.append(b_r)

        # Annotate with rate and sample size
        if d_rate is not None:
            ax.text(i - bar_w / 2, d_val + 1, f"{d_val:.0f}%\nn={d_total}",
                    ha="center", va="bottom", fontsize=6.5, color="#333333")
        if r_rate is not None:
            ax.text(i + bar_w / 2, r_val + 1, f"{r_val:.0f}%\nn={r_total}",
                    ha="center", va="bottom", fontsize=6.5, color="#333333")

        x_labels.append(f"{label1}\n{label2}")

    # Dividers between classification groups (every 4 bars)
    for div in [3.5, 7.5]:
        ax.axvline(div, color="#cccccc", linewidth=1, zorder=1)

    # Group labels above dividers
    for gx, glabel in [(1.5, "Trifecta"), (5.5, "Governor Only"), (9.5, "Two-Thirds")]:
        ax.text(gx, ax.get_ylim()[1] if ax.get_ylim()[1] > 0 else 100,
                glabel, ha="center", va="bottom", fontsize=9,
                fontweight="bold", color="#444444")

    ax.set_xticks(xs)
    ax.set_xticklabels(x_labels, fontsize=8)
    ax.set_ylim(0, 100)
    ax.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda v, _: f"{int(v)}%")
    )
    ax.tick_params(length=0)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#eeeeee", linewidth=0.7)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color("#bbbbbb")

    dem_patch = mpatches.Patch(color=DEM_COLOR, label="Democratic states")
    rep_patch = mpatches.Patch(color=REP_COLOR, label="Republican states")
    ax.legend(handles=[dem_patch, rep_patch], loc="upper right", fontsize=9,
              framealpha=0.9)

    fig.text(
        0.5, 0.98,
        "Trump 2nd Term FEMA Denial Rates — Sensitivity Across Methodologies",
        fontsize=13, fontweight="bold", ha="center", va="top", color="#111111",
    )
    approvals_src = "FemaWeb (v1)" if fema_web else "DisasterDeclarationsSummaries (v2)"
    fig.text(
        0.5, 0.92,
        f"Each bar pair shows the denial rate (1 − approval rate) for Dem- and Rep-led states "
        f"under a different combination of classification and scope flags · Approvals: {approvals_src}",
        fontsize=8.5, ha="center", va="top", color="#555555",
    )
    fig.text(
        0.02, 0.01,
        "Note: n = total requests (approved + denied) in that bucket. "
        "Source: Independent replication using FEMA APIs. "
        "Inspired by POLITICO/E&E News reporting (Thomas Frank).",
        fontsize=7.5, va="bottom", ha="left", color="#888888",
    )

    plt.subplots_adjust(left=0.05, right=0.98, top=0.88, bottom=0.18)
    plt.savefig(OUTPUT_PATH, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"Chart saved to {OUTPUT_PATH}")
    plt.close()


# ── Main ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Trump 2nd term FEMA denial rate sensitivity chart."
    )
    parser.add_argument(
        "--fema-web",
        action="store_true",
        help="Use v1/FemaWebDisasterDeclarations (disaster-level) instead of "
             "v2/DisasterDeclarationsSummaries (county-level) for approvals.",
    )
    args = parser.parse_args()

    dr_approved, em_approved, denied = fetch_data(fema_web=args.fema_web)

    results = []
    for label1, label2, classification, include_emergency, all_types in COMBINATIONS:
        print(f"Running: {label1} / {label2} ...", end=" ", flush=True)
        counts = run_combination(
            dr_approved, em_approved, denied,
            classification, include_emergency, all_types,
        )
        d_rate, d_total = denial_rate(counts, "D")
        r_rate, r_total = denial_rate(counts, "R")
        print(f"Dem {d_rate:.1f}% (n={d_total})  Rep {r_rate:.1f}% (n={r_total})"
              if d_rate is not None else "no data")
        results.append((label1, label2, classification, include_emergency, all_types,
                        d_rate, d_total, r_rate, r_total))

    plot(results, fema_web=args.fema_web)
