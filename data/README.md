# Data

Per window results behind the poster. Raw OpenSignals recordings are not included
because of their size; these are the exported analysis outputs.

Every file uses the 6 s context and 2 s horizon configuration unless the name or
the `config` column says otherwise.

| file | rows | what it holds |
|------|------|---------------|
| `poster_numbers_6s2s.csv` | 905 | one row per analysis window across 24 recordings: cardiac harmonic SNR, heart rate, Chronos NRMSE, latency. The main table behind Figures 3 and 4. |
| `both_models_6s2s.csv` | 908 | both models at the adopted 6 s / 2 s operating point, 905 windows finite for both. This is the head to head comparison the poster reports. |
| `both_models_windows.csv` | 856 | SUPERSEDED, kept only as a record. Its `nrmse_timesfm` column is a numerical artifact, see the warning below. |
| `coupling_phases_6s2s.csv` | 31 | the deliberate perturbation protocol, labelled by phase, with mean infrared level per window. Behind Figure 1. |
| `sweep_discrimination.csv` | 4 | median NRMSE, AUC and Spearman rho for each context and horizon combination that was swept. |
| `threshold_derivation_sweep.csv` | 4 | Youden J cutting points with 10,000 resample bootstrap intervals, and the 33rd and 67th percentiles, for each swept configuration. |
| `coupling_protocol_results.csv` | 61 | the earlier 12.8 s configuration of the same perturbation protocol, kept for comparison. |
| `paper_test_results.csv` | 26 | the paper sheet insertion test, 12.8 s configuration. |

The 6 s / 2 s scoring of the paper sheet recording is in `poster_numbers_6s2s.csv`
under the filename `coupling_test2.txt`. That is where the 0.948 spike on the
poster comes from.

## Columns

| column | meaning |
|--------|---------|
| `cardiac_hr_snr` | ratio of power in the cardiac band (0.8 to 3 Hz) to total power above 0.1 Hz. Despite the column name this is a band to total power ratio, not a signal to noise ratio, so it falls when broadband noise rises even while the cardiac peak is unchanged. |
| `hr_bpm` | heart rate estimated from that band |
| `nrmse_chronos`, `nrmse_timesfm` | forecast error, RMSE divided by the range of the true segment |
| `ir_mean` | mean raw 860 nm intensity in the window, a proxy for how much light reached the detector |
| `latency_ms` | wall clock time for one forecast |
| `window_end_sec` | position of the window within its recording |

## A warning about the TimesFM column in `both_models_windows.csv`

That column ranges from 0.21 to 1.65e10 with a median of 412. Those are not
model results. The benchmark that produced them loaded TimesFM with
`torch_compile=True`, which intermittently returns garbage on this workload.

Re-running the identical windows with `torch_compile=False` puts TimesFM level
with Chronos, a median NRMSE of 0.384 against 0.391, Wilcoxon p = 0.29. Any
claim that TimesFM failed on these signals is therefore withdrawn. Chronos was
adopted because it is smaller, not because it was more accurate.

`rerun_both_models_6s2s.py` in the repository root regenerates
`both_models_6s2s.csv` from the raw recordings.

## Reproducing

From the repository root:

```
python reproduce_poster_numbers.py
```
