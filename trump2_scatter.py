"""
Trump 2nd Term FEMA Approval Rate vs 2024 Trump Vote Share — Scatterplot
========================================================================
Each point is a state. X axis = Trump 2024 vote share. Y axis = FEMA approval
rate during Trump's 2nd term. All declaration types (DR+EM), all incident types.

Output: trump2_scatter.png
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
    get_state_alignment,
    _parse_dt,
    STATE_PARTY_DATA,
)

OUTPUT_PATH = "trump2_scatter.png"

# 2024 presidential election — Trump vote share by state
# Source: official state election results (corrected)
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

STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming",
}

TRUMP2_START = "2025-01-20"


def fetch_data(fema_web=False):
    if fema_web:
        print("Fetching DR+EM approvals from FemaWeb endpoint...")
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


def compute_state_rates(approved_records, denied_records):
    """
    Compute per-state approval rates for Trump 2nd term only.
    Returns dict: state -> {"approved": n, "denied": n}
    Uses same pipeline as analyze() but buckets by state instead of president.
    """
    from collections import defaultdict

    # Deduplicate approvals by (disasterNumber, state)
    seen = set()
    approvals = []
    for rec in approved_records:
        key = (rec["disasterNumber"], rec["state"])
        if key not in seen:
            seen.add(key)
            approvals.append(rec)

    state_counts = defaultdict(lambda: {"approved": 0, "denied": 0})

    for rec in approvals:
        date = rec.get("declarationDate", "")
        if date[:10] < TRUMP2_START:
            continue
        state = rec["state"]
        state_counts[state]["approved"] += 1

    # Denials: Turndown + Major Disaster only + Trump 2 window
    for rec in denied_records:
        if rec.get("currentRequestStatus") != "Turndown":
            continue
        if rec.get("declarationRequestType") != "Major Disaster":
            continue
        date = rec.get("requestStatusDate") or rec.get("declarationRequestDate", "")
        if not date or date[:10] < TRUMP2_START:
            continue
        state = rec.get("stateAbbreviation", "").strip()
        state_counts[state]["denied"] += 1

    return state_counts


def plot(state_counts, fema_web=False):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        import numpy as np
        from scipy import stats
    except ImportError:
        print("matplotlib/scipy not installed")
        return

    DEM_COLOR  = "#2166c0"
    REP_COLOR  = "#d6312b"
    MIX_COLOR  = "#888888"

    xs, ys, colors, labels, sizes = [], [], [], [], []

    for state, trump_pct in sorted(TRUMP_2024.items()):
        c = state_counts.get(state, {"approved": 0, "denied": 0})
        total = c["approved"] + c["denied"]
        if total == 0:
            continue

        approval_rate = c["approved"] / total * 100
        alignment = get_state_alignment(state, "2025-06-01T00:00:00.000Z")
        color = {"D": DEM_COLOR, "R": REP_COLOR}.get(alignment, MIX_COLOR)

        xs.append(trump_pct)
        ys.append(approval_rate)
        colors.append(color)
        labels.append(state)
        sizes.append(max(30, total ** 1.6 * 20))  # mild power scale — visible but not extreme

    xs = np.array(xs)
    ys = np.array(ys)

    fig, ax = plt.subplots(figsize=(11, 7))
    fig.patch.set_facecolor("white")

    ax.scatter(xs, ys, c=colors, s=sizes, alpha=0.82, zorder=3,
               linewidths=0.5, edgecolors="white")

    # OLS trend line across all states
    slope, intercept, r, p, _ = stats.linregress(xs, ys)
    x_line = np.linspace(xs.min() - 2, xs.max() + 2, 200)
    ax.plot(x_line, slope * x_line + intercept, color="#444444",
            linewidth=1.5, linestyle="--", zorder=2,
            label=f"Trend (r={r:.2f}, p={p:.3f})")

    # State labels — placed relative to the dot using offset_points so they
    # always stay anchored to the dot regardless of axis scaling, and never
    # clip outside the axes.
    # Per-state overrides (dx, dy in points) for crowded areas.
    LABEL_OFFSET_PTS = {
        # y=0% cluster (denied all): push below
        "AZ": (0, -10), "CA": (0, -10), "HI": (0, -10),
        "IL": (0, -10), "VT": (0, -10),
        # y=100% cluster (approved all): push above
        "AR": (0,  9), "GA": ( 14,  0), "IA": (  0,  9),
        "IN": (0,  9), "LA": ( 14,  0), "MI": (-14,  0),
        "MO": (0,  9), "MS": ( 14,  0), "MT": (-14,  0),
        "NC": (0,  9), "ND": ( 14,  0), "SC": (  0,  9),
        "TX": (0,  9), "WV": ( 14,  0),
        # y=50% cluster: alternate above/below
        "AK": ( 0,  9), "MD": (-14,  0), "MN": (-14,  0),
        "OR": ( 0, -10), "SD": ( 14,  0), "WA": ( 0,  9),
        "WI": ( 0, -10),
        # other
        "KS": ( 0,  9), "KY": ( 14,  0), "NE": ( 0, -10),
        "NM": (-14,  0), "OK": ( 0,  9), "TN": ( 0, -10),
        "VA": (-14,  0),
    }
    for x, y, lbl in zip(xs, ys, labels):
        dx, dy = LABEL_OFFSET_PTS.get(lbl, (9, 0))
        ha = "left" if dx >= 0 else "right"
        ax.annotate(
            lbl, xy=(x, y),
            xytext=(dx, dy), textcoords="offset points",
            fontsize=7, color="#333333", ha=ha, va="center",
            clip_on=True,
        )

    # Reference lines
    ax.axvline(50, color="#cccccc", linewidth=0.8, linestyle=":", zorder=1)
    ax.axhline(50, color="#cccccc", linewidth=0.8, linestyle=":", zorder=1)
    ax.text(50.3, 2, "50% Trump vote →", fontsize=7, color="#aaaaaa")
    ax.text(26, 50, "50% approval", fontsize=7, color="#aaaaaa",
            rotation=90, va="center", ha="right")

    ax.set_xlabel("Trump 2024 Vote Share (%)", fontsize=11)
    ax.set_ylabel("FEMA Approval Rate — Trump 2nd Term (%)", fontsize=11)
    ax.set_xlim(25, 75)
    ax.set_ylim(0, 105)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v)}%"))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v)}%"))
    ax.tick_params(length=0, labelsize=9)
    ax.set_axisbelow(True)
    ax.grid(color="#eeeeee", linewidth=0.7)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    dem_patch  = mpatches.Patch(color=DEM_COLOR, label="D trifecta")
    rep_patch  = mpatches.Patch(color=REP_COLOR, label="R trifecta")
    mix_patch  = mpatches.Patch(color=MIX_COLOR, label="Mixed")
    trend_line = plt.Line2D([0], [0], color="#444444", linewidth=1.5,
                            linestyle="--", label=f"Trend (r={r:.2f}, p={p:.3f})")
    ax.legend(handles=[dem_patch, rep_patch, mix_patch, trend_line],
              fontsize=8.5, loc="upper left", framealpha=0.9)

    # Bubble size legend
    for n, label in [(1, "n=1"), (5, "n=5"), (10, "n=10")]:
        ax.scatter([], [], s=max(40, n * 18), c="#aaaaaa", alpha=0.7,
                   label=label)
    ax.legend(handles=[dem_patch, rep_patch, mix_patch, trend_line] +
              [ax.scatter([], [], s=max(30, n ** 1.6 * 20), c="#aaaaaa",
                          alpha=0.7, label=f"n={n}")
               for n in [1, 5, 10]],
              fontsize=8, loc="upper left", framealpha=0.9,
              title="Bubble = total requests",
              labelspacing=1.4, handletextpad=1.2, borderpad=1.0)

    fig.text(
        0.5, 0.98,
        "Trump 2nd Term FEMA Approval Rate vs 2024 Trump Vote Share",
        fontsize=13, fontweight="bold", ha="center", va="top", color="#111111",
    )
    approvals_src = "FemaWeb v1" if fema_web else "DisasterDeclarationsSummaries v2"
    fig.text(
        0.5, 0.93,
        f"All declaration types (DR + EM) · All incident types · State trifecta classification · {approvals_src}",
        fontsize=8.5, ha="center", va="top", color="#555555",
    )
    fig.text(
        0.02, 0.01,
        "Note: Bubble size = total FEMA requests (approved + denied) for that state since Jan 20 2025. "
        "States with zero requests excluded.\n"
        "Sources: FEMA Disaster Declarations Summaries & Declaration Denials APIs; "
        "2024 election results via AP. Independent replication inspired by POLITICO/E&E News.",
        fontsize=7.5, va="bottom", ha="left", color="#888888", linespacing=1.5,
    )

    plt.subplots_adjust(left=0.08, right=0.97, top=0.90, bottom=0.12)
    plt.savefig(OUTPUT_PATH, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"Chart saved to {OUTPUT_PATH}")
    plt.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Trump 2nd term FEMA approval rate vs 2024 vote share scatterplot."
    )
    parser.add_argument(
        "--fema-web",
        action="store_true",
        help="Use v1/FemaWebDisasterDeclarations (disaster-level) instead of "
             "v2/DisasterDeclarationsSummaries (county-level) for approvals.",
    )
    args = parser.parse_args()

    approved, denied = fetch_data(fema_web=args.fema_web)
    state_counts = compute_state_rates(approved, denied)

    print("\nState-level Trump 2 results:")
    print(f"  {'State':<6} {'Trump%':>7} {'App':>5} {'Den':>5} {'Rate':>7}")
    print(f"  {'-'*35}")
    for state in sorted(TRUMP_2024):
        c = state_counts.get(state, {"approved": 0, "denied": 0})
        total = c["approved"] + c["denied"]
        if total == 0:
            continue
        rate = c["approved"] / total * 100
        print(f"  {state:<6} {TRUMP_2024[state]:>6.1f}% {c['approved']:>5} {c['denied']:>5} {rate:>6.1f}%")

    plot(state_counts, fema_web=args.fema_web)
