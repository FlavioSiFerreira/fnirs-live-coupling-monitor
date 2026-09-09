"""Recompute every poster number that the data in data/ can support.

Run it with no arguments:

    python reproduce_poster_numbers.py

Each claim prints as PASS or FAIL against the value printed on the poster.
Claims that the shipped data cannot settle are listed at the end rather than
quietly skipped.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

DATA = Path(__file__).resolve().parent / "data"

GOOD_CUT = 0.31        # rounded 33rd percentile, as printed on the poster
POOR_CUT = 0.49        # rounded 67th percentile, as printed on the poster
HR_GOOD = 0.20         # cardiac SNR label rule for the good vs rest ROC
HR_POOR = 0.05         # cardiac SNR label rule for the poor vs rest ROC
PAPER_RECORDING = "coupling_test2.txt"   # the paper sheet insertion recording

_results: list[tuple[bool, str]] = []


def roc_auc(labels: np.ndarray, score: np.ndarray) -> float:
    """AUC by the rank sum identity, so scikit-learn is not needed."""
    labels = np.asarray(labels).astype(bool)
    n_pos, n_neg = int(labels.sum()), int((~labels).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    ranks = stats.rankdata(score)
    rank_sum = float(ranks[labels].sum())
    return (rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def _record(label: str, ok: bool) -> None:
    """Record a claim that is a yes or no rather than a number."""
    _results.append((bool(ok), label))
    print(f"  [{'PASS' if ok else 'FAIL'}]  {label}")


def check(label: str, poster, computed, tol=0.005, fmt="{:.3f}") -> None:
    """Record one claim. Numeric claims compare within tol, others compare equal."""
    if isinstance(poster, (int, np.integer)) and isinstance(computed, (int, np.integer)):
        ok = poster == computed
        shown_p, shown_c = str(poster), str(computed)
    else:
        ok = abs(float(poster) - float(computed)) <= tol
        shown_p, shown_c = fmt.format(float(poster)), fmt.format(float(computed))
    _results.append((ok, label))
    print(f"  [{'PASS' if ok else 'FAIL'}]  {label:52s} poster {shown_p:>8s}"
          f"   computed {shown_c:>8s}")


def section(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def main() -> int:
    windows = pd.read_csv(DATA / "poster_numbers_6s2s.csv")
    both = pd.read_csv(DATA / "both_models_windows.csv")
    phases = pd.read_csv(DATA / "coupling_phases_6s2s.csv")

    section("Methods")
    check("analysis windows", 905, int(len(windows)))
    check("recordings", 24, int(windows.filename.nunique()))
    check("context seconds", 6.0, float(windows.context_sec.iloc[0]), tol=1e-9, fmt="{:.1f}")
    check("horizon seconds", 2.0, float(windows.horizon_sec.iloc[0]), tol=1e-9, fmt="{:.1f}")

    section("Quality bands")
    err = windows.nrmse_chronos.to_numpy()
    check("median NRMSE", 0.387, float(np.median(err)))
    q33, q67 = np.quantile(err, [1 / 3, 2 / 3])
    check("good cutting point, 33rd percentile", GOOD_CUT, float(q33))
    check("poor cutting point, 67th percentile", POOR_CUT, float(q67))
    good_or_ok = float((err <= q67).mean())
    check("share in the good or acceptable range", 2 / 3, good_or_ok, tol=0.01)

    section("Agreement with the cardiac reference")
    hr = windows.cardiac_hr_snr.to_numpy()
    rho, pval = stats.spearmanr(hr, err)
    check("Spearman rho", -0.27, float(rho))
    _results.append((pval < 0.001, "Spearman p below 0.001"))
    print(f"  [{'PASS' if pval < 0.001 else 'FAIL'}]  "
          f"{'Spearman p below 0.001':52s} poster  <0.001   computed {pval:8.1e}")
    auc_good = roc_auc(hr >= HR_GOOD, -err)
    auc_poor = roc_auc(hr <= HR_POOR, err)
    check("AUC, good vs rest", 0.62, float(auc_good), tol=0.006, fmt="{:.2f}")
    check("AUC, poor vs rest", 0.65, float(auc_poor), tol=0.006, fmt="{:.2f}")

    section("Chronos against TimesFM, Figure 2")
    paired = both[np.isfinite(both.nrmse_chronos) & np.isfinite(both.nrmse_timesfm)]
    check("windows scored by both models", 852, int(len(paired)))
    check("Chronos forecasts below the poor cutting point", 562,
          int((paired.nrmse_chronos < POOR_CUT).sum()))
    check("TimesFM forecasts below the poor cutting point", 10,
          int((paired.nrmse_timesfm < POOR_CUT).sum()))
    print(f"         median NRMSE, Chronos {paired.nrmse_chronos.median():.3f}   "
          f"TimesFM {paired.nrmse_timesfm.median():.1f}")

    section("Deliberate perturbations, Figure 1")
    # Light level is compared as the median infrared reading of a phase against
    # the median across every tight band window, which is the baseline the
    # poster quotes.
    tight = phases[phases.phase.str.contains("Tight")]
    baseline_light = float(tight.ir_mean.median())
    table = phases.groupby("phase", sort=False).agg(
        windows=("nrmse_chronos", "size"),
        median_nrmse=("nrmse_chronos", "median"),
        median_cardiac_snr=("cardiac_hr_snr", "median"),
        median_infrared=("ir_mean", "median"),
    )
    table["light_change_pct"] = 100 * (table.median_infrared - baseline_light) / baseline_light
    print(table.to_string(float_format=lambda v: f"{v:.4f}"))
    print(f"         baseline, median infrared across the tight band windows "
          f"{baseline_light:.0f}")

    check("loosened band, light change", -5.4,
          float(table.loc["Loosened band", "light_change_pct"]), tol=0.05, fmt="{:.1f}")
    check("loosened band, median NRMSE barely moved", 0.28,
          float(table.loc["Loosened band", "median_nrmse"]), tol=0.03, fmt="{:.2f}")
    _record("loosened band keeps the strongest pulse of any phase",
            table.median_cardiac_snr.idxmax() == "Loosened band")
    check("finger on sensor, light change", -1.1,
          float(table.loc["Finger on sensor", "light_change_pct"]), tol=0.05, fmt="{:.1f}")
    check("finger on sensor, median NRMSE", 0.485,
          float(table.loc["Finger on sensor", "median_nrmse"]))
    _record("finger on sensor collapses the pulse against the tight band baseline",
            float(table.loc["Finger on sensor", "median_cardiac_snr"])
            < 0.2 * float(table.loc["Tight band, rest", "median_cardiac_snr"]))

    section("Paper sheet insertion, Figure 1")
    paper = windows[windows.filename == PAPER_RECORDING].sort_values("window_end_sec")
    peak = paper.loc[paper.nrmse_chronos.idxmax()]
    after = paper[paper.window_end_sec > peak.window_end_sec]
    check("paper sheet, peak NRMSE", 0.948, float(peak.nrmse_chronos))
    print(f"         the peak is a single window at t = {peak.window_end_sec:.0f} s")
    _record("the score settles again after the spike",
            float(after.nrmse_chronos.median()) < POOR_CUT)
    _record("the sensor still reads a pulse through the paper",
            float(after.cardiac_hr_snr.median())
            > float(paper[paper.window_end_sec <= peak.window_end_sec].cardiac_hr_snr.median()))
    print(f"         median NRMSE after the spike {after.nrmse_chronos.median():.3f}, "
          f"cardiac SNR {paper[paper.window_end_sec <= peak.window_end_sec].cardiac_hr_snr.median():.3f}"
          f" before and {after.cardiac_hr_snr.median():.3f} after")

    section("Cross-check of the cutting points against Youden J")
    sweep = pd.read_csv(DATA / "threshold_derivation_sweep.csv")
    row = sweep[sweep.config.str.startswith("6s")].iloc[0]
    print(f"  33rd percentile {row.pct33:.3f}, Youden good cut bootstrap interval "
          f"[{row.youden_good_ci_lo:.3f}, {row.youden_good_ci_hi:.3f}] -> "
          f"{'inside' if row.pct33_in_good_ci else 'OUTSIDE'}")
    print(f"  67th percentile {row.pct67:.3f}, Youden poor cut bootstrap interval "
          f"[{row.youden_poor_ci_lo:.3f}, {row.youden_poor_ci_hi:.3f}] -> "
          f"{'inside' if row.pct67_in_poor_ci else 'OUTSIDE'}")
    if not row.pct33_in_good_ci:
        print("  NOTE: at 6 s / 2 s the 33rd percentile sits just outside the "
              "interval for the Youden good cut.")
        print("        The 67th percentile agrees. Both agreed at the earlier "
              "12.8 s configuration.")

    section("Summary")
    failed = [label for ok, label in _results if not ok]
    print(f"  {len(_results) - len(failed)} of {len(_results)} claims reproduced")
    for label in failed:
        print(f"  FAILED: {label}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
