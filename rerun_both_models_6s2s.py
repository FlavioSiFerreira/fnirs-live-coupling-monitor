"""
Re-run BOTH models at the adopted 6 s context + 2 s horizon operating point,
over the same 24 recordings behind the published window set.

Motivation: the stored `nrmse_timesfm` column in both_models_windows.csv spans
0.21 to 1.65e10 (median 412). Re-running the same windows with
torch_compile=False gives TimesFM errors near 0.2, so that column is an
artifact and Figure 2 cannot rest on it.

Output: results/fnirs/both_models_6s2s.csv
"""
from __future__ import annotations

import csv
import glob
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch
from chronos import ChronosPipeline
from scipy.signal import resample_poly

PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR / "submission" / "code"))

from benchmark_fnirs_both_models import (  # noqa: E402
    FS_RAW,
    FS_DOWN,
    beer_lambert_hbo,
    cardiac_hr_snr,
    nrmse,
    parse_recording,
)

OUT_DIR = PROJECT_DIR / "results" / "fnirs"
OUT_CSV = OUT_DIR / "both_models_6s2s.csv"
REFERENCE_CSV = OUT_DIR / "both_models_windows.csv"

STEP_SEC = 5
NUM_SAMPLES = 20
CTX_N = 60          # 6 s at 10 Hz
HOR_N = 20          # 2 s at 10 Hz

SEARCH_ROOTS = [
    "C:/Users/User/OneDrive/Documentos/OpenSignals (r)evolution",
    "C:/Users/User/OneDrive/Documentos/PC-Handover-Backup/OpenSignals-data",
    str(PROJECT_DIR),
]


def target_filenames() -> list[str]:
    with open(REFERENCE_CSV, newline="") as f:
        return sorted({row["filename"] for row in csv.DictReader(f)})


def build_index() -> dict[str, str]:
    idx: dict[str, str] = {}
    for root in SEARCH_ROOTS:
        for p in glob.glob(root + "/**/*.txt", recursive=True):
            idx.setdefault(os.path.basename(p).lower(), p)
    return idx


def windows_for(dhbo, ir_raw, ctx_n, hor_n):
    total = ctx_n + hor_n
    win_sec = int(round(total / FS_DOWN))
    step = STEP_SEC * FS_DOWN
    for end in range(total, len(dhbo) + 1, step):
        context = dhbo[end - total: end - hor_n]
        truth = dhbo[end - hor_n: end]
        raw_end = (end * FS_RAW) // FS_DOWN
        raw_start = raw_end - win_sec * FS_RAW
        if raw_start < 0 or raw_end > len(ir_raw):
            continue
        snr, peak_f = cardiac_hr_snr(ir_raw[raw_start:raw_end])
        yield end / FS_DOWN, context, truth, snr, peak_f


def main() -> None:
    names = target_filenames()
    index = build_index()
    paths = []
    for n in names:
        hit = index.get(n.lower())
        if hit is None:
            print(f"  MISSING {n}", flush=True)
        else:
            paths.append(Path(hit))
    print(f"recordings: {len(paths)} of {len(names)} located", flush=True)

    print("loading chronos-t5-small ...", flush=True)
    chronos = ChronosPipeline.from_pretrained(
        "amazon/chronos-t5-small", device_map="cpu", torch_dtype=torch.float32
    )

    print("loading timesfm 2.5 (torch_compile=False) ...", flush=True)
    import timesfm
    from huggingface_hub import hf_hub_download
    weights = hf_hub_download(
        repo_id="google/timesfm-2.5-200m-pytorch",
        filename="model.safetensors",
        local_files_only=True,
    )
    tfm = timesfm.TimesFM_2p5_200M_torch(torch_compile=False)
    tfm.model.load_checkpoint(weights, torch_compile=False)
    tfm.compile(timesfm.ForecastConfig(
        max_context=320, max_horizon=128, infer_is_positive=False
    ))
    print("models loaded.", flush=True)

    parsed = []
    for p in paths:
        rec = parse_recording(p)
        if rec is None:
            print(f"  unusable {p.name}", flush=True)
            continue
        red_down = resample_poly(rec["red"], 1, FS_RAW // FS_DOWN).astype(np.float64)
        ir_down = resample_poly(rec["ir"], 1, FS_RAW // FS_DOWN).astype(np.float64)
        n_down = min(len(red_down), len(ir_down))
        dhbo = beer_lambert_hbo(red_down[:n_down], ir_down[:n_down],
                                baseline_n=min(50, n_down // 3))
        if dhbo.size == 0:
            continue
        parsed.append((rec["filename"], dhbo, rec["ir"]))
    print(f"parsed: {len(parsed)} recordings", flush=True)

    rows = []
    t_start = time.perf_counter()
    for fi, (fname, dhbo, ir_raw) in enumerate(parsed, 1):
        if dhbo.size < CTX_N + HOR_N:
            continue
        for end_sec, context, truth, snr, peak_f in windows_for(dhbo, ir_raw, CTX_N, HOR_N):
            context = np.nan_to_num(np.asarray(context, dtype=np.float32),
                                    nan=0.0, posinf=0.0, neginf=0.0)

            t0 = time.perf_counter()
            ct = torch.tensor(context).unsqueeze(0)
            out = chronos.predict(ct, prediction_length=HOR_N, num_samples=NUM_SAMPLES)
            pred_c = torch.median(out, dim=1).values[0].numpy().astype(np.float32)
            lat_c = (time.perf_counter() - t0) * 1000.0

            t0 = time.perf_counter()
            pf, _ = tfm.forecast(horizon=HOR_N, inputs=[context])
            pred_t = np.asarray(pf)[0, :HOR_N].astype(np.float32)
            lat_t = (time.perf_counter() - t0) * 1000.0

            rows.append({
                "filename": fname,
                "window_end_sec": end_sec,
                "cardiac_hr_snr": snr,
                "hr_bpm": peak_f * 60 if np.isfinite(peak_f) else np.nan,
                "nrmse_chronos": nrmse(truth, pred_c),
                "nrmse_timesfm": nrmse(truth, pred_t),
                "latency_chronos_ms": lat_c,
                "latency_timesfm_ms": lat_t,
            })
        print(f"  [{fi}/{len(parsed)}] {fname[:44]:44s} rows={len(rows):4d} "
              f"({time.perf_counter() - t_start:.0f}s)", flush=True)

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {OUT_CSV} ({len(rows)} rows)", flush=True)

    import pandas as pd
    d = pd.read_csv(OUT_CSV).replace([np.inf, -np.inf], np.nan)
    d = d.dropna(subset=["nrmse_chronos", "nrmse_timesfm"])
    print(f"\n=== {len(d)} windows with both finite ===")
    for m in ["chronos", "timesfm"]:
        e = d[f"nrmse_{m}"]
        print(f"  {m:8s} median={e.median():.4f}  IQR=[{e.quantile(.25):.4f}, "
              f"{e.quantile(.75):.4f}]  max={e.max():.4g}  "
              f"n<0.49={int((e < 0.49).sum())}  n>5={int((e > 5).sum())}")


if __name__ == "__main__":
    main()
