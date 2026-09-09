# fNIRS Live Coupling Quality Monitor

Tells you **while the recording is running** whether the fNIRS sensor is properly
coupled to the skin, so you can fix it before the participant goes home.

It works by asking a pretrained time series model to forecast the next 2 seconds
of the optical signal from the previous 6 seconds. A well coupled sensor carries
a steady cardiac pulsation, which the model predicts easily. Lose contact and the
pulsation goes with it, the forecast error jumps, and the score turns red.

Nothing is trained, fitted or calibrated. The model has never seen fNIRS data.

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
recordings, checked against Youden J cut points derived from an independent
cardiac reference. `reproduce_poster_numbers.py` prints how closely the two
agree.

---

## Quick start on Windows, three steps

1. **Install Python.** Get it from <https://www.python.org/downloads/> and, in
   the installer, **tick "Add python.exe to PATH"**. Any version from 3.10
   onwards works. If Python is already installed, skip this.
2. **Download this repository.** Green **Code** button at the top of the page,
   then **Download ZIP**. Unzip it anywhere you can write to, for example your
   Desktop.
3. **Double-click `Start Monitor.bat`.**

That is the whole install. The first run takes a few minutes: it builds a private
Python environment inside the folder and downloads the Chronos model. Every run
after that starts in seconds.

### Three things you can double-click

| file | what happens |
|------|--------------|
| `Run Self Test.bat` | checks the whole chain end to end, no sensor needed. **Start here.** |
| `Run Demo.bat` | writes a synthetic recording that loses contact and replays it, so you can watch the tier drop and recover. No sensor needed. |
| `Start Monitor.bat` | the real thing. Watches the OpenSignals folder and scores your live recording. |

### Using it with the hardware

1. Double-click `Start Monitor.bat` and wait for it to say it is watching.
2. Start OpenSignals (r)evolution and connect the biosignalsplux device.
3. Press record. The monitor finds the new `.txt` file on its own and prints a
   score every 2 seconds.
4. Press Ctrl+C when you are done.

Every score is also written to `results/fnirs/live_monitor_log.csv`.

---

## Chronos is not in this repository

Chronos T5 Small is Amazon's model, not ours, so it is not redistributed here.
The launcher installs the `chronos-forecasting` package and downloads the
checkpoint (about 190 MB) from the Hugging Face Hub the first time you run it.
You do not have to do anything.

### No internet on the recording computer

Recording machines are often offline. Set it up once on a machine that does have
internet, then carry the folder across.

1. On a computer with internet, download the model. Either run
   `Run Self Test.bat` once, which caches it, or fetch the files directly from
   <https://huggingface.co/amazon/chronos-t5-small> (the **Files and versions**
   tab, take everything).
2. Put the model files in a folder called `chronos-t5-small` inside a folder
   called `models`, next to the launchers:

   ```
   fnirs-live-coupling-monitor\
       Start Monitor.bat
       fnirs_live_monitor.py
       models\
           chronos-t5-small\
               config.json
               model.safetensors
               ... the rest of the files
   ```

3. Copy the whole `fnirs-live-coupling-monitor` folder, including the `.venv`
   folder the first run created, onto the offline machine.
4. Double-click `Start Monitor.bat`. It finds `models\chronos-t5-small` by itself
   and never touches the network.

You can also point at a model folder anywhere on disk by setting the
`CHRONOS_LOCAL_DIR` environment variable.

---

## Not on Windows

The launchers are Windows batch files, but nothing else is Windows specific.

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python fnirs_live_monitor.py --selftest
python fnirs_live_monitor.py --watch-dir /path/to/opensignals/files
```

---

## Options

| flag | effect |
|------|--------|
| `--selftest` | score synthetic clean and degraded windows, then exit |
| `--make-demo FILE` | write a synthetic OpenSignals recording |
| `--demo-quality good\|poor\|mixed` | profile for `--make-demo` (default mixed) |
| `--replay FILE` | replay a recording window by window as if it were live |
| `--speed S`, `--loop` | replay speed multiplier, loop the replay |
| `--watch-dir PATH` | watch a different OpenSignals folder, repeatable |
| `--red-col N`, `--ir-col N` | 0-based columns of the 660 and 860 nm channels (default 2 and 3) |
| `--show-r2` | also display R squared, a secondary diagnostic |
| `--no-color` | plain text output |

Pass them straight to the launcher, for example `Start Monitor.bat --show-r2`.

---

## Reproducing the poster numbers

```
python reproduce_poster_numbers.py
```

It recomputes every number printed on the poster from the CSV files in `data/`
and prints PASS or FAIL for each. All 24 pass at the 6 s context and 2 s horizon
configuration, including the three deliberate perturbations and the paper sheet
spike. The script also reports where the percentile cutting points sit against
the Youden J bootstrap intervals rather than only asserting that they agree.

---

## What is in here

| file | purpose |
|------|---------|
| `Start Monitor.bat` | live monitoring, double-click to run |
| `Run Demo.bat` | synthetic recording plus replay, no hardware |
| `Run Self Test.bat` | end to end check, no hardware |
| `_setup.bat` | shared first-run setup, called by the three above |
| `fnirs_live_monitor.py` | the monitor: file watching, Beer Lambert conversion, scoring, replay, demo generator |
| `chronos_wrapper.py` | loads Chronos T5 Small from the Hub or a local folder |
| `metrics.py` | NRMSE, R squared and the other forecast metrics |
| `reproduce_poster_numbers.py` | recomputes the poster numbers from `data/` |
| `data/` | per window results behind the poster, see `data/README.md` |
| `requirements.txt` | Python dependencies |

---

## How the score is computed

1. Read the tail of the growing OpenSignals `.txt` file, columns 2 and 3, at
   1000 Hz.
2. Downsample to 10 Hz by polyphase resampling.
3. Convert the 660 and 860 nm intensities to delta HbO with the modified Beer
   Lambert law, against a 5 second rolling baseline.
4. Give the model the last 6 seconds (60 samples) and ask for the next 2 seconds
   (20 samples).
5. Report the normalised RMSE between the forecast and what actually arrived.
   NRMSE is divided by the signal range, so it does not care about scale or
   offset.

The score follows the pulse, not the brightness. Ordinary changes in headband
pressure move the light level without moving the score.

---

## Limitations, please read

- Validated on **one healthy adult**, 24 recordings, biceps brachii and
  forehead. Nothing here is clinically validated.
- Agreement with the cardiac reference is **weak**, AUC 0.62 to 0.65. This is a
  live triage aid, not a replacement for offline quality control.
- It answers "is this collecting a physiological signal" and not "is the light
  intensity right". Different headband pressures are not detected.
- Each score costs about 0.4 s of CPU time, so the practical update rate is a
  couple of seconds.

---

## Citation

Ferreira F, Ferreira H, Placido da Silva H. Zero-shot signal quality assessment
for physiological recordings using pretrained time series foundation models.
Poster, 2026.

The forecasting model is Chronos:

Ansari AF, Stella L, Turkmen C, et al. Chronos: learning the language of time
series. Transactions on Machine Learning Research. 2024.

---

## Licence

MIT, see `LICENSE`. Chronos T5 Small is distributed separately by Amazon under
its own licence, which applies to the model you download.
