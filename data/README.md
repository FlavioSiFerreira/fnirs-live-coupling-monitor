# Data

Per window analysis outputs behind the reported numbers. Raw OpenSignals
recordings are not included because of their size.

Every file uses the 6 s context and 2 s horizon configuration unless the table
says otherwise.

| file | rows | what it holds |
|------|------|---------------|
| `poster_numbers_6s2s.csv` | 905 | one row per analysis window across 24 recordings: cardiac band ratio, heart rate, Chronos NRMSE, latency. The main table behind Figures 3 and 4. |
| `both_models_6s2s.csv` | 908 | Chronos and TimesFM over the same windows, 905 of them finite for both. The head to head comparison. |
| `coupling_phases_6s2s.csv` | 31 | the deliberate perturbation protocol, labeled by phase, with mean infrared level per window. Behind Figure 1. |
| `sweep_discrimination.csv` | 4 | median NRMSE, AUC and Spearman rho for each context and horizon combination that was swept. |
| `threshold_derivation_sweep.csv` | 4 | Youden J cutting points with 10,000 resample bootstrap intervals, and the 33rd and 67th percentiles, for each swept configuration. |
| `coupling_protocol_results.csv` | 61 | the same perturbation protocol scored with a 12.8 s context. |
| `paper_test_results.csv` | 26 | the paper sheet insertion test, 12.8 s context. |

The 6 s / 2 s scoring of the paper sheet recording is in
`poster_numbers_6s2s.csv` under the filename `coupling_test2.txt`, which is
where the 0.948 spike comes from.

## Columns

| column | meaning |
|--------|---------|
| `cardiac_hr_snr` | ratio of power in the cardiac band (0.8 to 3 Hz) to total power above 0.1 Hz. Despite the column name this is a band to total power ratio, not a signal to noise ratio, so it falls when broadband noise rises even while the cardiac peak is unchanged. |
| `hr_bpm` | heart rate estimated from that band |
| `nrmse_chronos`, `nrmse_timesfm` | forecast error, RMSE divided by the range of the true segment |
| `ir_mean` | mean raw 860 nm intensity in the window, a proxy for how much light reached the detector |
| `latency_ms` | wall clock time for one forecast |
| `window_end_sec` | position of the window within its recording |

## Reproducing

From the repository root:

```
python reproduce_poster_numbers.py
```
