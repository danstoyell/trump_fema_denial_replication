"""
Significance tests for the Trump 2nd term partisan gap
======================================================
For every flag combination of replicate_fema_analysis.py (approvals endpoint x
incident types x declaration types x classification = 24), tests whether
Democratic-aligned states' Trump 2nd term denial rate differs from Republican-
aligned states':
  - Exact binomial: Dem denials vs. a null rate equal to the Rep denial rate
    (treats the Rep rate as known, so it overstates significance).
  - Fisher's exact test on the 2x2 Dem/Rep x approved/denied table
    (accounts for uncertainty on both sides; the better headline number).

Also tests the state-level correlation between Trump 2nd term approval rate and
2024 Trump vote share (the trump2_scatter.py chart) for each scope: Pearson
(what the chart's trend line uses), Spearman, and a request-weighted slope.

Output: significance_results.md
Requires scipy and numpy.
"""

import sys
import io
import argparse
import contextlib
import itertools
from datetime import date
sys.path.insert(0, ".")

import numpy as np
from scipy import stats

import replicate_fema_analysis as rfa
from trump2_scatter import TRUMP_2024, compute_state_rates

OUTPUT_PATH = "significance_results.md"

CLASSIFICATIONS = [("trifecta", {}), ("gov-only", {"governor_only": True}),
                   ("2/3", {"two_thirds": True})]


def fetch_data():
    """Fetch every approvals variant and the denials once."""
    print("Fetching v2 DR approvals...")
    v2_dr = rfa.fetch_all_pages(
        lambda skip: rfa.fetch_declarations_page(skip, declaration_type="DR"),
        "DisasterDeclarationsSummaries")
    print("Fetching v2 EM approvals...")
    v2_em = rfa.fetch_all_pages(
        lambda skip: rfa.fetch_declarations_page(skip, declaration_type="EM"),
        "DisasterDeclarationsSummaries")
    print("Fetching FemaWeb approvals...")
    web_all = rfa.fetch_all_fema_web(include_emergency=True)
    web_dr = [r for r in web_all if r["declarationType"] == "DR"]
    print("Fetching denials...")
    denied = rfa.fetch_all_pages(rfa.fetch_denials_page, "DeclarationDenials")
    approvals = {
        (False, False): v2_dr, (False, True): v2_dr + v2_em,
        (True, False): web_dr, (True, True): web_all,
    }
    return approvals, denied


def natural_only(approved, denied):
    """Same incident-type exclusions analyze() applies without --all-types."""
    exclude_app = {"Biological", "Terrorist", "Chemical", "Other", "Toxic Substances"}
    exclude_den = {"Other", "Human Cause", "Toxic Substances"}
    return ([r for r in approved if r.get("incidentType") not in exclude_app],
            [r for r in denied if r.get("requestedIncidentTypes") not in exclude_den])


def gap_tests(approvals, denied):
    rows = []
    for fema_web, all_types, (cls, kw), emerg in itertools.product(
            [False, True], [False, True], CLASSIFICATIONS, [False, True]):
        with contextlib.redirect_stdout(io.StringIO()):
            counts = rfa.analyze(approvals[(fema_web, emerg)], denied,
                                 all_types=all_types, include_emergency=emerg, **kw)
        d, r = counts["Trump 2"]["D"], counts["Trump 2"]["R"]
        n_d, n_r = d["approved"] + d["denied"], r["approved"] + r["denied"]
        binom = stats.binomtest(d["denied"], n_d, r["denied"] / n_r).pvalue
        odds, fisher = stats.fisher_exact([[d["denied"], d["approved"]],
                                           [r["denied"], r["approved"]]])
        rows.append({
            "api": "V1" if fema_web else "v2",
            "incidents": "all" if all_types else "natural",
            "decl": "DR+EM" if emerg else "DR",
            "cls": cls,
            "d": (d["approved"], n_d), "r": (r["approved"], n_r),
            "binom": binom, "fisher": fisher, "odds": odds,
        })
    return rows


def scatter_tests(approvals, denied):
    rows = []
    for fema_web, all_types, emerg in itertools.product(
            [False, True], [False, True], [False, True]):
        a, d = approvals[(fema_web, emerg)], denied
        if not all_types:
            a, d = natural_only(a, d)
        state_counts = compute_state_rates(a, d, include_emergency=emerg)
        xs, ys, ns = [], [], []
        for state, pct in sorted(TRUMP_2024.items()):
            c = state_counts.get(state, {"approved": 0, "denied": 0})
            n = c["approved"] + c["denied"]
            if n:
                xs.append(pct); ys.append(c["approved"] / n * 100); ns.append(n)
        x, y, w = np.array(xs), np.array(ys), np.array(ns, dtype=float)
        pearson = stats.linregress(x, y)
        spearman = stats.spearmanr(x, y)
        # Weighted least squares with weights = requests per state
        A = np.vstack([np.ones_like(x), x]).T
        AtW = A.T * w
        beta = np.linalg.solve(AtW @ A, AtW @ y)
        dof = len(x) - 2
        s2 = (w * (y - A @ beta) ** 2).sum() / dof
        se = np.sqrt(s2 * np.linalg.inv(AtW @ A)[1, 1])
        wls_p = 2 * stats.t.sf(abs(beta[1] / se), dof)
        rows.append({
            "api": "V1" if fema_web else "v2",
            "incidents": "all" if all_types else "natural",
            "decl": "DR+EM" if emerg else "DR",
            "states": len(x), "r": pearson.rvalue, "p": pearson.pvalue,
            "slope": pearson.slope, "rho": spearman.statistic,
            "rho_p": spearman.pvalue, "wslope": beta[1], "wls_p": wls_p,
        })
    return rows


def pct(pair):
    a, n = pair
    return f"{a}/{n} ({a / n * 100:.1f}%)"


def write_markdown(gaps, scatter):
    lines = [
        "# Significance Tests — Trump 2nd Term Partisan Gap",
        "",
        f"Generated by `significance_tests.py` on {date.today().isoformat()} from live "
        "OpenFEMA data. Tribal requests are attributed to their state, as in the charts.",
        "",
        "## Dem vs. Rep approval (24 flag combinations)",
        "",
        "Sorted from weakest (highest Fisher p) to strongest. Binomial: Dem denials "
        "vs. a null rate equal to the Rep denial rate (treats the Rep rate as known, "
        "so it overstates significance). Fisher: exact test on the 2x2 table "
        "(two-sided) — the better headline number.",
        "",
        "| API | Incidents | Declarations | Classification | Dem approved | Rep approved | Gap (pts) | Binomial p | Fisher p | Odds ratio |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for g in sorted(gaps, key=lambda g: -g["fisher"]):
        gap = g["r"][0] / g["r"][1] * 100 - g["d"][0] / g["d"][1] * 100
        lines.append(
            f"| {g['api']} | {g['incidents']} | {g['decl']} | {g['cls']} "
            f"| {pct(g['d'])} | {pct(g['r'])} | {gap:.1f} "
            f"| {g['binom']:.2e} | {g['fisher']:.2e} | {g['odds']:.2f} |")
    worst = max(gaps, key=lambda g: g["fisher"])
    lines += [
        "",
        f"Highest Fisher p across all 24: **{worst['fisher']:.3g}** "
        f"({worst['cls']}, {worst['incidents']} incidents, {worst['decl']}). "
        f"Highest binomial p: **{max(g['binom'] for g in gaps):.3g}**.",
        "",
        "## State approval rate vs. 2024 Trump vote share",
        "",
        "One point per state with at least one Trump 2nd term decision, as in "
        "`trump2_scatter.py`. State classification does not enter these tests.",
        "",
        "| API | Incidents | Declarations | States | Pearson r | Pearson p | Slope (pts/pt) | Spearman ρ | Spearman p | Request-weighted slope | Weighted p |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in sorted(scatter, key=lambda s: -s["p"]):
        lines.append(
            f"| {s['api']} | {s['incidents']} | {s['decl']} | {s['states']} "
            f"| {s['r']:.3f} | {s['p']:.2e} | {s['slope']:.2f} "
            f"| {s['rho']:.3f} | {s['rho_p']:.2e} | {s['wslope']:.2f} | {s['wls_p']:.2e} |")
    lines += [
        "",
        "## Caveats",
        "",
        "- Requests are not independent: one storm can generate several requests, "
        "states request repeatedly, and decisions are issued in batches. All tests "
        "here overstate precision somewhat.",
        "- The 24 combinations are highly correlated views of the same data; the "
        "table reports raw p-values without multiple-comparison correction.",
        "- Pearson weights every state equally, including states with a single "
        "request (0% or 100% approval); the Spearman and request-weighted columns "
        "check robustness to that.",
        "",
    ]
    with open(OUTPUT_PATH, "w") as f:
        f.write("\n".join(lines))
    print(f"Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Binomial / Fisher / correlation tests for the Trump 2nd term "
                    "partisan gap across all flag combinations."
    )
    parser.parse_args()

    approvals, denied = fetch_data()
    gaps = gap_tests(approvals, denied)
    scatter = scatter_tests(approvals, denied)

    worst = max(gaps, key=lambda g: g["fisher"])
    print(f"\nHighest Fisher p: {worst['fisher']:.3g} "
          f"({worst['api']} {worst['incidents']} {worst['decl']} {worst['cls']})")
    print(f"Highest binomial p: {max(g['binom'] for g in gaps):.3g}")
    print(f"Highest scatter Pearson p: {max(s['p'] for s in scatter):.3g}")
    write_markdown(gaps, scatter)
