# fNIRS Live Coupling Quality Monitor

Tells you during a recording whether the fNIRS sensor is properly coupled, so you
can fix it before the participant goes home.

A pretrained time series model forecasts the next 2 seconds of the optical signal
from the previous 6. A well coupled sensor carries a steady cardiac pulsation,
which the model predicts easily. Lose contact and the pulsation goes with it, the
forecast error jumps, and the score turns red. The model is used as shipped, with
no training or calibration on fNIRS data.

```
  [  42.0s] GOOD       NRMSE=0.184  [placement stable]
  [  44.0s] GOOD       NRMSE=0.207  [placement stable]
  [  46.0s] POOR       NRMSE=0.883
  [  48.0s] ACCEPTABLE NRMSE=0.402
```

| tier | forecast NRMSE | what to do |
|------|----------------|------------|
| GOOD | below 0.31 | carry on recording |
| ACCEPTABLE | 0.31 to 0.49 | usable, consider a small adjustment |
| POOR | above 0.49 | reposition the sensor |

The cutting points are the 33rd and 67th percentiles of 905 windows from 24
recordings, checked against Youden J cut points from an independent cardiac
reference. That pooled distribution has a median NRMSE of 0.387 and an
interquartile range of 0.278 to 0.570. `reproduce_poster_numbers.py` prints how
closely the two agree.

## Status: this is a feasibility test

Not a validated instrument, and not a clinical device. Every number here comes
from one healthy adult, 24 recordings, 905 analysis windows, one sensor model.
Nothing has been replicated on a second person, on a second device, or in a
clinical setting. The perturbation tests show what the score reacts to, not that
it detects a lost sensor, because the cardiac rhythm stayed recoverable in all of
them. Read the Limitations section before acting on a score, and treat the tier
as a prompt to look at the signal rather than a verdict on it.

## Which model

Chronos T5 Small (46M) and TimesFM 2.5 (200M) were compared on the same 905
windows at this operating point. The two error distributions are equivalent, a
median NRMSE of 0.391 against 0.384, Wilcoxon p = 0.29. Chronos was adopted
because it is the smaller of the two.

Read that equivalence at the level it was measured. It is a statement about the
two distributions, not about individual windows. Window by window the two models
agree only moderately, Spearman rho = 0.62, and they place the same window in the
same tier in 59.4 per cent of cases. A single window can change tier if the model
is swapped. A non-significant Wilcoxon test is also not a proof of equivalence,
only a failure to detect a difference at n = 905.

The median of 0.391 above comes from the paired two-model run
(`data/both_models_6s2s.csv`). The 0.387 quoted with the cutting points comes
from the sweep that derived them (`data/sweep_discrimination.csv`). Same
configuration and same 905 windows, two separate runs, and Chronos sampling is
stochastic, which is the whole of the difference.

An earlier run that appeared to show TimesFM failing was a `torch_compile`
artifact and is withdrawn, see `data/README.md`.

## Quick start on Windows

1. Install Python 3.10 or newer from <https://www.python.org/downloads/>. Tick
   **Add python.exe to PATH** in the installer. Skip this if you already have it.
2. Download this repository: green **Code** button, **Download ZIP**, unzip it
   somewhere you can write to.
3. Double-click **`Run Self Test.bat`**.

The first run builds a Python environment inside the folder and downloads
Chronos, which takes a few minutes. Later runs start in seconds. If it is
interrupted, run it again and it picks up where it stopped.

| file | what it does |
|------|--------------|
| `Run Self Test.bat` | checks the whole chain, no sensor needed. Start here. |
| `Run Demo.bat` | writes a synthetic recording that loses contact and replays it, so you can watch the tier drop and recover. No sensor needed. |
| `Start Monitor.bat` | the real thing. Watches the OpenSignals folder and scores your live recording. |

### With the hardware

Launch `Start Monitor.bat`, then start OpenSignals (r)evolution and press record.
The monitor picks up the new file and prints a score every 2 seconds. Ctrl+C to
stop. Scores are appended to `results/fnirs/live_monitor_log.csv`.

Detection looks for files named `opensignals_*.txt`, which is what OpenSignals
writes by default. Point it elsewhere with `--watch-dir`.

## Chronos is not in this repository

Chronos T5 Small is Amazon's model, not ours, so it is not redistributed here.
The launcher installs the `chronos-forecasting` package and downloads the
checkpoint (about 190 MB) on first run. You do not have to do anything.

### No internet on the recording computer

On a computer that does have internet, in this folder:

```
py -3 -m pip download -r requirements.txt -d wheels
```

Then download the model files from
<https://huggingface.co/amazon/chronos-t5-small> (the **Files and versions** tab)
into `models\chronos-t5-small`, so the folder looks like this:

```
fnirs-live-coupling-monitor\
    Start Monitor.bat
    wheels\               the downloaded packages
    models\
        chronos-t5-small\
            config.json
            model.safetensors
            ...
```

Copy the folder across and double-click `Start Monitor.bat`. It installs from
`wheels\`, loads the model from `models\`, and never touches the network. Python
still has to be installed on that computer.

Do not copy the `.venv` folder between machines. It hardcodes paths from the
machine that built it and will not start elsewhere. The launcher rebuilds it.

`CHRONOS_LOCAL_DIR` points at a model folder anywhere on disk if you prefer.

## Not on Windows

Only the launchers are Windows specific.

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python fnirs_live_monitor.py --selftest
python fnirs_live_monitor.py --watch-dir /path/to/opensignals/files
```

## Options

| flag | effect |
|------|--------|
| `--selftest` | score synthetic clean and degraded windows, then exit |
| `--make-demo FILE` | write a synthetic OpenSignals recording |
| `--demo-quality good\|poor\|mixed` | profile for `--make-demo` (default mixed) |
| `--replay FILE` | replay a recording window by window as if it were live |
| `--speed S`, `--loop` | replay speed multiplier, loop the replay |
| `--watch-dir PATH` | watch a different folder, repeatable |
| `--red-col N`, `--ir-col N` | 0-based columns of the 660 and 860 nm channels (default 2 and 3) |
| `--show-r2` | also display R squared, a secondary diagnostic |
| `--no-color` | plain text output |

Pass them to the launcher, for example `Start Monitor.bat --show-r2`.

## Reproducing the poster numbers

```
python reproduce_poster_numbers.py
```

Recomputes every number on the poster from the CSV files in `data/` and prints
PASS or FAIL for each. All 24 pass. See `data/README.md` for what each file
holds.

## How the score is computed

Read the tail of the growing OpenSignals file at 1000 Hz, downsample to 10 Hz,
convert the 660 and 860 nm intensities to delta HbO with the modified Beer
Lambert law against a 5 second baseline, give the model the last 60 samples and
ask for the next 20, then report the RMSE of that forecast divided by the range
of the measured segment.

Dividing by the range makes the score independent of scale and offset, so it
follows the pulse rather than the brightness. Changing headband pressure moves
the light level without moving the score.

## Limitations

- This is a feasibility test. One healthy adult, 24 recordings, biceps brachii
  and forehead, one sensor model, 905 analysis windows. No second participant, no
  second device, no clinical validation, no test-retest.
- Agreement with the cardiac reference is weak, AUC 0.62 to 0.65, Spearman
  rho = -0.27 across the 905 windows. On the conventional reading of AUC, the
  0.5 to 0.7 band is poor discrimination. This is a live triage aid that tells
  you to go and look at the signal, not a replacement for offline quality
  control, and not a measurement of coupling.
- The two cutting points are not equally well supported. At this 6 s
  configuration the 67th percentile falls inside the bootstrap interval of the
  Youden J poor cut, while the 33rd percentile falls just outside it. Both
  agreed at the earlier 12.8 s configuration. `reproduce_poster_numbers.py`
  prints both intervals.
- The tiers are percentiles of one pooled distribution, so roughly a third of
  windows land in each tier by construction. A tier is a position within this
  participant's own recordings, not an absolute quality threshold, and it does
  not transfer to another person or device without re-deriving it.
- In the deliberate perturbation tests the cardiac rhythm stayed recoverable
  throughout, so none of them produced a true loss of signal. The tests show
  what the score reacts to, which is light contamination and movement rather
  than pressure, and not that it detects a lost sensor.
- It answers whether a physiological signal is being collected, not whether the
  light intensity is right. Different headband pressures are not detected.
- Each score costs about 0.4 s of CPU, so updates are a couple of seconds apart.

## Citation

Ferreira F, Ferreira H, Placido da Silva H. Zero-shot signal quality assessment
for physiological recordings using pretrained time series foundation models.
Poster, 2026.

Ansari AF, Stella L, Turkmen C, et al. Chronos: learning the language of time
series. Transactions on Machine Learning Research. 2024.

## Licence

MIT, see `LICENSE`. Chronos T5 Small is distributed separately by Amazon under
its own licence.
