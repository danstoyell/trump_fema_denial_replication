"""
Biden vs Trump 2nd Term — FEMA Denial Rates by State Party
===========================================================
Methodology: two-thirds classification, DR+EM declarations, all incident types.

Output: biden_vs_trump2_denial_rates.png
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

OUTPUT_PATH = "biden_vs_trump2_denial_rates.png"


def fetch_data(fema_web=False):
    if fema_web:
        print("Fetching approvals from FemaWeb endpoint (DR+EM)...")
        approved = fetch_all_fema_web(include_emergency=True)
        print(f"  {len(approved)} rows")
    else:
        print("Fetching DR approvals...")
        dr = fetch_all_pages(
            lambda skip: fetch_declarations_page(skip, declaration_type="DR"),
            "DisasterDeclarationsSummaries",
        )
        print(f"  {len(dr)} rows")

        print("Fetching EM approvals...")
        em = fetch_all_pages(
            lambda skip: fetch_declarations_page(skip, declaration_type="EM"),
            "DisasterDeclarationsSummaries",
        )
        print(f"  {len(em)} rows")
        approved = dr + em

    print("Fetching denials...")
    denied = fetch_all_pages(fetch_denials_page, "DeclarationDenials")
    print(f"  {len(denied)} rows")

    return approved, denied


def denial_rate(counts, president, alignment):
    c = counts.get(president, {}).get(alignment, {"approved": 0, "denied": 0})
    total = c["approved"] + c["denied"]
    if total == 0:
        return None, 0, 0, 0
    rate = (1 - c["approved"] / total) * 100
    return rate, total, c["approved"], c["denied"]


def plot(counts, fema_web=False, include_emergency=True):
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

    presidents = ["Biden", "Trump 2"]
    display    = ["Biden", "Trump\n(2nd term)"]
    alignments = [("D", DEM_COLOR, "Dem states"), ("R", REP_COLOR, "Rep states")]

    bar_w = 0.3
    group_gap = 1.0
    xs = np.array([0, group_gap + bar_w * 2 + 0.2])

    fig, ax = plt.subplots(figsize=(8, 5.8))
    fig.patch.set_facecolor("white")

    offsets = [-bar_w / 2 - 0.02, bar_w / 2 + 0.02]

    for (alignment, color, _), offset in zip(alignments, offsets):
        for i, pres in enumerate(presidents):
            rate, total, approved, denied_n = denial_rate(counts, pres, alignment)
            if rate is None:
                continue
            x = xs[i] + offset
            ax.bar(x, rate, bar_w, color=color, zorder=3)
            # Rate label above bar
            ax.text(x, rate + 1.2, f"{rate:.1f}%",
                    ha="center", va="bottom", fontsize=10, fontweight="bold",
                    color=color)
            # Sample size inside bar near the bottom (avoids collision with x-tick labels)
            ax.text(x, 2, f"n={total}\n({approved}✓ {denied_n}✗)",
                    ha="center", va="bottom", fontsize=7, color="white",
                    fontweight="bold", zorder=4)

    # President labels as plain text below the axis, clear of bar annotations
    ax.set_xticks(xs)
    ax.set_xticklabels(display, fontsize=12)
    ax.set_xlim(-0.6, xs[-1] + 0.6)
    ax.set_ylim(0, 100)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v)}%"))
    ax.tick_params(length=0)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#eeeeee", linewidth=0.7)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color("#bbbbbb")

    dem_patch = mpatches.Patch(color=DEM_COLOR, label="Democratic-leaning states")
    rep_patch = mpatches.Patch(color=REP_COLOR, label="Republican-leaning states")
    ax.legend(handles=[dem_patch, rep_patch], loc="upper left",
              fontsize=9, framealpha=0.9)

    fig.text(
        0.5, 0.97,
        "FEMA Disaster Request Denial Rates: Biden vs Trump 2nd Term",
        fontsize=13, fontweight="bold", ha="center", va="top", color="#111111",
    )
    approvals_src = ("v1/FemaWebDisasterDeclarations" if fema_web
                     else "v2/DisasterDeclarationsSummaries")
    decl_scope = "DR + EM" if include_emergency else "DR only"
    fig.text(
        0.5, 0.90,
        f"By state party leaning (two-thirds rule) · {decl_scope} · All incident types · {approvals_src}",
        fontsize=8.5, ha="center", va="top", color="#555555",
    )
    fig.text(
        0.02, 0.01,
        "Note: States classified as D/R when 2 of 3 offices (governor + both senators) belong to same party.\n"
        "Source: Independent replication using FEMA Disaster Declarations Summaries and Declaration Denials APIs. "
        "Inspired by POLITICO/E&E News reporting (Thomas Frank).",
        fontsize=7.5, va="bottom", ha="left", color="#888888", linespacing=1.5,
    )

    plt.subplots_adjust(left=0.1, right=0.95, top=0.87, bottom=0.14)
    plt.savefig(OUTPUT_PATH, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"Chart saved to {OUTPUT_PATH}")
    plt.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Biden vs Trump 2nd term FEMA denial rate comparison."
    )
    parser.add_argument(
        "--fema-web",
        action="store_true",
        help="Use v1/FemaWebDisasterDeclarations (disaster-level) instead of "
             "v2/DisasterDeclarationsSummaries (county-level) for approvals.",
    )
    parser.add_argument(
        "--include-emergency",
        action="store_true",
        help="Include Emergency (EM) declarations in addition to Major Disasters (DR). "
             "Default: DR only.",
    )
    args = parser.parse_args()

    approved, denied = fetch_data(fema_web=args.fema_web)

    counts = analyze(
        approved,
        denied,
        all_types=True,
        two_thirds=True,
        include_emergency=args.include_emergency,
    )

    print("\nResults:")
    for pres in ["Biden", "Trump 2"]:
        for alignment in ["D", "R"]:
            rate, total, app, den = denial_rate(counts, pres, alignment)
            label = "Dem" if alignment == "D" else "Rep"
            print(f"  {pres:8} {label}: {rate:.1f}% denial (n={total}, {app} approved, {den} denied)")

    plot(counts, fema_web=args.fema_web, include_emergency=args.include_emergency)
