# fNIRS Live Coupling Quality Monitor

Scores fNIRS sensor coupling while the recording is running, so a bad placement
can be caught during the session instead of after the participant leaves.

A pretrained time series model forecasts the next 2 seconds of the optical
signal from the previous 6. A sensor in good contact carries a steady cardiac
pulsation, which the model predicts easily. When ambient light leaks under the
optode or the sensor slides, the pulsation is buried, the forecast error rises,
and the score turns red. The model is used exactly as shipped, with no training
or calibration on fNIRS data.

## Read this first

This is a feasibility check, not a validated instrument. Every number here comes
from 24 recordings of a single healthy adult. The question it was built to
answer is narrow: is the sensor picking up a real physiological pulse, or is the
trace dominated by light contamination and movement. Optimal performance on
other people, other hardware, or other montages is not claimed and has not been
tested. Nothing here is clinically validated.

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

The cutting points are the 33rd and 67th percentiles of 905 windows from those
24 recordings, cross checked against Youden J cut points from an independent
cardiac reference. That pooled distribution has a median NRMSE of 0.387 and an
interquartile range of 0.278 to 0.570. Treat the tiers as a starting point and
re-derive them on your own setup before relying on them.

## Which model

Chronos T5 Small (46M) runs the forecast. TimesFM 2.5 (200M) was compared on the
same 905 windows, a median NRMSE of 0.391 against 0.384 with a Wilcoxon p of
0.29, so the smaller model was adopted.

Read that comparison at the level it was measured. It says the two error
distributions sit in the same place, not that the two models agree on a given
window. Window by window they agree only moderately, Spearman rho 0.62, and they
place the same window in the same tier about 60 per cent of the time, so a single
window can change tier if the model is swapped. A non-significant test is also
not proof of equivalence, only a failure to detect a difference at n = 905.

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

## The model is downloaded, not bundled

Chronos T5 Small is distributed by Amazon and is not redistributed here. The
launcher installs the `chronos-forecasting` package and downloads the checkpoint
(about 190 MB) on first run. No action is needed.

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

- One healthy adult, 24 recordings, biceps brachii and forehead, one sensor
  model, 905 windows. No second participant, no second device, no test retest,
  no clinical validation.
- Agreement with the cardiac reference is weak, AUC 0.62 to 0.65 and Spearman
  rho of -0.27 across the 905 windows. On the conventional reading of AUC, 0.5
  to 0.7 is poor discrimination. This is a prompt to go and look at the signal,
  not a measurement of coupling and not a replacement for offline quality
  control.
- The tiers are percentiles of one pooled distribution, so about a third of
  windows land in each tier by construction. A tier is a position within this
  participant's own recordings, not an absolute quality threshold.
- The two cutting points are not equally well supported. The 67th percentile
  falls inside the bootstrap interval of the Youden J poor cut, the 33rd
  percentile falls just outside the interval for the good cut.
  `reproduce_poster_numbers.py` prints both intervals.
- Chronos decoding is sampled and no seed is fixed, so the same window can score
  slightly differently on two runs.
- In the deliberate perturbation tests the cardiac rhythm stayed recoverable
  throughout, so none of them produced a true loss of signal. The tests show
  what the score reacts to, which is light contamination and movement rather
  than pressure, and not that it detects a lost sensor.
- It answers whether a physiological signal is being collected, not whether the
  light intensity is right. Different headband pressures are not detected.
- Each score costs about 0.4 s of CPU, so updates are a couple of seconds apart.

## Reproducing the reported numbers

```
python reproduce_poster_numbers.py
```

Recomputes every number reported on the poster from the CSV files in `data/` and
prints PASS or FAIL for each. See `data/README.md` for what each file holds.

## Citation

Ferreira F, Ferreira H, Placido da Silva H. Zero-shot signal quality assessment
for physiological recordings using pretrained time series foundation models.
Poster, 2026.

Ansari AF, Stella L, Turkmen C, et al. Chronos: learning the language of time
series. Transactions on Machine Learning Research. 2024.

## License

MIT, see `LICENSE`. Chronos T5 Small is distributed separately by Amazon under
its own license.
