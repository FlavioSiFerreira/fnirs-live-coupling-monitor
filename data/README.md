# Data

Per window results behind the poster. Raw OpenSignals recordings are not included
because of their size; these are the exported analysis outputs.

Every file uses the 6 s context and 2 s horizon configuration unless the name or
the `config` column says otherwise.

| file | rows | what it holds |
|------|------|---------------|
| `poster_numbers_6s2s.csv` | 905 | one row per analysis window across 24 recordings: cardiac harmonic SNR, heart rate, Chronos NRMSE, latency. The main table behind Figures 3 and 4. |
| `both_models_windows.csv` | 856 | the windows scored by both Chronos and TimesFM, 852 of which produced a finite result for both. Behind Figure 2. |
| `coupling_phases_6s2s.csv` | 31 | the deliberate perturbation protocol, labelled by phase, with mean infrared level per window. Behind Figure 1. |
| `sweep_discrimination.csv` | 5 | median NRMSE, AUC and Spearman rho for each context and horizon combination that was swept. |
| `threshold_derivation_sweep.csv` | 5 | Youden J cutting points with 10,000 resample bootstrap intervals, and the 33rd and 67th percentiles, for each swept configuration. |
| `coupling_protocol_results.csv` | 61 | the earlier 12.8 s configuration of the same perturbation protocol, kept for comparison. |
| `paper_test_results.csv` | 26 | the paper sheet insertion test, 12.8 s configuration. |

## Columns

| column | meaning |
|--------|---------|
| `cardiac_hr_snr` | harmonic signal to noise ratio of the cardiac band, the independent physiological reference |
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
