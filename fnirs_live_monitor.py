"""Live fNIRS sensor coupling-quality monitor.

Watches the OpenSignals temp/files directories for an active recording, reads
the growing .txt file incrementally, converts the red and infrared intensities
to delta-HbO with the Modified Beer-Lambert Law, and displays a rolling Chronos
forecast NRMSE as a coupling-quality score.

Three-tier scheme (pooled 905-window cutting points, Chronos NRMSE):
    good        NRMSE < 0.31   proceed
    acceptable  0.31 to 0.49   usable, minor adjustment
    poor        NRMSE > 0.49   reposition the sensor

Context and horizon (60 points of 6 s context, 20 points of 2 s horizon at
10 Hz) are the configuration reported on the poster. The cutting points are the
33rd and 67th percentiles of the pooled 6 s / 2 s NRMSE distribution
(0.3097 and 0.4924), cross-checked against Youden J against the cardiac
harmonic signal to noise reference. See data/ and reproduce_poster_numbers.py.

Modes
-----
    python fnirs_live_monitor.py                 live watch of OpenSignals
    python fnirs_live_monitor.py --selftest      end-to-end check, no hardware
    python fnirs_live_monitor.py --make-demo F   write a synthetic recording F
    python fnirs_live_monitor.py --replay F       replay recording F as if live

Start recording in OpenSignals after launching in live mode. Press Ctrl+C to
stop.
"""
from __future__ import annotations

import argparse
import datetime
import os
import sys
import time
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

# Extinction coefficients (SENSADV-FNIRS, 660 and 860 nm), cm^-1 / (mol/L).
E_HBO_660 = 319.6
E_HBR_660 = 3226.56
E_HBO_860 = 1092.0
E_HBR_860 = 694.32
MBLL_DET = E_HBO_660 * E_HBR_860 - E_HBO_860 * E_HBR_660

THRESH_GOOD = 0.31     # 33rd percentile of the pooled 6 s / 2 s distribution
THRESH_OK = 0.49       # 67th percentile of the same distribution

FS_RAW = 1000              # biosignalsplux sampling rate
FS_DOWN = 10               # analysis rate after polyphase downsampling
CONTEXT_SAMPLES = 60       # 6 s context, the configuration the tiers came from
HORIZON_SAMPLES = 20       # 2 s forecast horizon
UPDATE_INTERVAL = 2.0      # seconds between quality updates

# Column indices in the OpenSignals .txt (0-based). CH9A (660 nm) and
# CH9B (860 nm) land in columns 2 and 3 for the single-sensor montage used
# here. Override with --red-col / --ir-col if the montage differs.
DEFAULT_RED_COL = 2
DEFAULT_IR_COL = 3
MIN_INTENSITY = 5.0        # raw counts below this are device warm-up / dropout

# Seconds of raw signal to pull from the file tail each update. Comfortably
# larger than context + horizon so a full window is always available and the
# read stays O(1) regardless of total recording length.
TAIL_SECONDS = 40
_BYTES_PER_LINE = 96       # generous upper bound for one OpenSignals data row

WINDOW_SAMPLES = CONTEXT_SAMPLES + HORIZON_SAMPLES  # 80 downsampled samples

OPENSIGNALS_DIRS = [
    Path.home() / "Documents" / "OpenSignals (r)evolution" / "temp",
    Path.home() / "Documents" / "OpenSignals (r)evolution" / "files",
]


# --------------------------------------------------------------------------- #
# terminal helpers
# --------------------------------------------------------------------------- #
def enable_ansi() -> None:
    """Enable ANSI colour on Windows 10+ consoles (no-op elsewhere)."""
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass


COLORS = {"GOOD": "\033[92m", "ACCEPTABLE": "\033[93m", "POOR": "\033[91m"}
RESET = "\033[0m"
BOLD = "\033[1m"
_use_color = True
_show_r2 = False   # tier uses NRMSE only; R2 is a secondary diagnostic


def paint(text: str, code: str) -> str:
    return f"{code}{text}{RESET}" if _use_color else text


# --------------------------------------------------------------------------- #
# signal processing
# --------------------------------------------------------------------------- #
def _to_2d(data: np.ndarray) -> np.ndarray | None:
    if data.ndim == 1:
        data = data.reshape(1, -1)
    if data.ndim != 2 or data.shape[0] < 2:
        return None
    return data


def parse_columns(data_lines: list[str], red_col: int, ir_col: int):
    """Parse red/IR columns from a list of OpenSignals data rows."""
    if len(data_lines) < 10:
        return None, None
    try:
        data = np.loadtxt(data_lines)
    except (ValueError, IndexError):
        return None, None
    data = _to_2d(data)
    if data is None or data.shape[1] <= max(red_col, ir_col):
        return None, None
    return data[:, red_col].astype(np.float64), data[:, ir_col].astype(np.float64)


def read_tail(path: Path, red_col: int, ir_col: int, tail_seconds: int = TAIL_SECONDS):
    """Read red/IR intensities from the tail of a growing OpenSignals file.

    Returns (red, ir) 1D arrays trimmed of any leading warm-up run, or
    (None, None) if not enough live data is present yet.
    """
    try:
        size = path.stat().st_size
        want = int(tail_seconds * FS_RAW * _BYTES_PER_LINE)
        start = max(0, size - want)
        with open(path, "rb") as f:
            f.seek(start)
            chunk = f.read()
    except (OSError, PermissionError):
        return None, None

    text = chunk.decode("utf-8", errors="ignore")
    lines = text.splitlines()
    if start > 0 and lines:
        lines = lines[1:]  # drop the partial first line after a mid-file seek
    data_lines = [ln for ln in lines if ln and not ln.startswith("#")]

    red, ir = parse_columns(data_lines, red_col, ir_col)
    if red is None:
        return None, None

    # Trim only a leading run of warm-up / dropout samples; keep interior
    # low-intensity samples so genuine coupling loss is not silently removed.
    live = (red > MIN_INTENSITY) & (ir > MIN_INTENSITY)
    if not live.any():
        return None, None
    first = int(np.argmax(live))
    red, ir = red[first:], ir[first:]
    if len(red) < WINDOW_SAMPLES * (FS_RAW // FS_DOWN):
        return None, None
    return red, ir


def compute_hbo(red_raw: np.ndarray, ir_raw: np.ndarray):
    """Convert raw red/IR intensity to delta-HbO at FS_DOWN via the MBLL.

    The forecast NRMSE is scale and offset independent, so the rolling
    baseline reproduces the tier behaviour of the offline batch analysis.
    """
    n = min(len(red_raw), len(ir_raw))
    red = resample_poly(red_raw[:n], 1, FS_RAW // FS_DOWN)
    ir = resample_poly(ir_raw[:n], 1, FS_RAW // FS_DOWN)
    n = min(len(red), len(ir))
    red, ir = red[:n], ir[:n]

    bl_n = min(50, max(1, n // 3))
    bl_red = float(np.mean(red[:bl_n]))
    bl_ir = float(np.mean(ir[:bl_n]))
    if bl_red <= 0 or bl_ir <= 0:
        return None

    dod_red = -np.log(np.clip(red / bl_red, 1e-10, None))
    dod_ir = -np.log(np.clip(ir / bl_ir, 1e-10, None))
    dhbo = (E_HBR_860 * dod_red - E_HBR_660 * dod_ir) / MBLL_DET
    return dhbo.astype(np.float32)


def score_window(dhbo: np.ndarray, model):
    """Return (nrmse, r2) for the most recent window, or (None, None)."""
    from chronos_wrapper import chronos_forecast_single
    from metrics import nrmse, r_squared

    if dhbo is None or len(dhbo) < WINDOW_SAMPLES:
        return None, None

    window = dhbo[-WINDOW_SAMPLES:]
    context = np.asarray(window[:CONTEXT_SAMPLES], dtype=np.float32)
    truth = np.asarray(window[CONTEXT_SAMPLES:], dtype=np.float32)

    if not np.all(np.isfinite(context)):
        context = np.nan_to_num(context, nan=0.0, posinf=0.0, neginf=0.0)
    if not np.all(np.isfinite(truth)):
        return None, None

    pred = chronos_forecast_single(model, context, horizon_len=HORIZON_SAMPLES)
    return nrmse(truth, pred), r_squared(truth, pred)


def quality_label(value: float) -> str:
    if value < THRESH_GOOD:
        return "GOOD"
    if value <= THRESH_OK:
        return "ACCEPTABLE"
    return "POOR"


# --------------------------------------------------------------------------- #
# synthetic recordings (for testing without hardware)
# --------------------------------------------------------------------------- #
def synth_intensities(seconds: float, quality: str, seed: int = 0):
    """Generate plausible raw red/IR intensities at FS_RAW.

    Good coupling shows a clear cardiac pulsation on a slow hemodynamic
    baseline; the periodic cardiac component is what a pretrained forecaster
    predicts with low error. Poor coupling destroys the cardiac rhythm and
    replaces it with erratic light-loss steps (sensor slipping off the skin),
    which a forecaster cannot anticipate. This mirrors the cardiac-SNR ground
    truth used to derive the tiers.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * FS_RAW)) / FS_RAW
    if quality == "good":
        slow = np.sin(2 * np.pi * 0.05 * t)
        resp = np.sin(2 * np.pi * 0.25 * t + 0.5)
        cardiac = np.sin(2 * np.pi * 1.1 * t)
        red = 600 + 2 * slow + 2 * resp + 3 * cardiac + rng.normal(0, 0.6, t.size)
        ir = 500 + 1.6 * slow + 1.6 * resp + 2.4 * cardiac + rng.normal(0, 0.6, t.size)
        return red, ir

    # poor: sustained decoupling, piecewise random light loss (no cardiac)
    n = t.size
    red = np.full(n, 600.0)
    i = 0
    while i < n:
        j = min(n, i + int(rng.uniform(0.6, 1.2) * FS_RAW))
        red[i:j] = 600 * rng.uniform(0.45, 1.05)
        i = j
    ir = (500.0 / 600.0) * red + rng.normal(0, 4, n)
    red = red + rng.normal(0, 4, n)
    return np.clip(red, 20, None), np.clip(ir, 20, None)


def synth_decouple_window(seconds: float, seed: int = 0):
    """Clean cardiac coupling that loses contact over the final 2 s (an acute
    decoupling / paper-insertion event). The last scored window is POOR."""
    red, ir = synth_intensities(seconds, "good", seed)
    rng = np.random.default_rng(seed + 100)
    n = len(red)
    k = int(2.0 * FS_RAW)
    seg = slice(n - k, n)
    ramp = np.linspace(0, 1, k)
    red[seg] = red[seg] * (1 - 0.85 * ramp) + rng.normal(0, 12, k) * ramp
    ir[seg] = ir[seg] * (1 - 0.77 * ramp) + rng.normal(0, 11, k) * ramp
    return np.clip(red, 20, None), np.clip(ir, 20, None)


def write_opensignals(path: Path, red: np.ndarray, ir: np.ndarray) -> None:
    """Write a minimal OpenSignals-format .txt with red/IR in columns 2 and 3."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n = min(len(red), len(ir))
    seq = np.arange(n)
    di = np.zeros(n, dtype=int)
    cols = np.column_stack([seq, di, np.round(red[:n]).astype(int),
                            np.round(ir[:n]).astype(int)])
    header = (
        "# OpenSignals Text File Format (synthetic)\n"
        "# {\"synthetic\": {\"sampling rate\": 1000, "
        "\"channels\": [1], \"label\": [\"CH9A\", \"CH9B\"]}}\n"
        "# EndOfHeader\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(header)
        np.savetxt(f, cols, fmt="%d", delimiter="\t")


# --------------------------------------------------------------------------- #
# modes
# --------------------------------------------------------------------------- #
def print_banner() -> None:
    print(paint("fNIRS Sensor Coupling-Quality Monitor", BOLD))
    print(f"  context {CONTEXT_SAMPLES/FS_DOWN:.1f} s + {HORIZON_SAMPLES/FS_DOWN:.0f} s horizon, "
          f"update every {UPDATE_INTERVAL:.0f} s")
    print(f"  tiers: {paint('good', COLORS['GOOD'])} < {THRESH_GOOD}   "
          f"{paint('acceptable', COLORS['ACCEPTABLE'])} {THRESH_GOOD}-{THRESH_OK}   "
          f"{paint('poor', COLORS['POOR'])} > {THRESH_OK}")


def render_line(elapsed: float, value: float, r2: float, stable: bool) -> str:
    label = quality_label(value)
    lock = paint("  [placement stable]", COLORS["GOOD"]) if stable else ""
    r2_str = f"  R2={r2:+.2f}" if _show_r2 else ""
    return (f"\r  [{elapsed:6.1f}s] {paint(f'{label:10s}', COLORS[label])} "
            f"NRMSE={value:.3f}{r2_str}{lock}        ")


def open_log(script_dir: Path):
    log_path = script_dir / "results" / "fnirs" / "live_monitor_log.csv"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("timestamp,elapsed_sec,nrmse,r2,quality,filename\n")
        return log_path
    except OSError:
        return None


def log_row(log_path, elapsed, value, r2, label, filename) -> None:
    if log_path is None:
        return
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            f.write(f"{ts},{elapsed:.1f},{value:.4f},{r2:.4f},{label},{filename}\n")
    except OSError:
        pass


def find_latest_recording(watch_dirs):
    latest, latest_mtime = None, 0.0
    for d in watch_dirs:
        if not d.exists():
            continue
        for f in d.glob("opensignals_*.txt"):
            m = f.stat().st_mtime
            if m > latest_mtime:
                latest, latest_mtime = f, m
    return latest


def run_live(model, watch_dirs, red_col, ir_col, log_path) -> None:
    print_banner()
    print("  waiting for an OpenSignals recording...\n", flush=True)
    last_file, last_size, consecutive_good = None, 0, 0

    while True:
        current = find_latest_recording(watch_dirs)
        if current is None:
            print("\r  no recording detected, start OpenSignals...      ",
                  end="", flush=True)
            time.sleep(1)
            continue

        size = current.stat().st_size
        if current != last_file:
            last_file, last_size, consecutive_good = current, size, 0
            print(f"\n  detected {current.name}\n  collecting data...\n", flush=True)
            time.sleep(UPDATE_INTERVAL)
            continue
        if size == last_size:
            time.sleep(1)
            continue
        last_size = size

        red, ir = read_tail(current, red_col, ir_col)
        if red is None:
            print(f"\r  collecting data ({size // 1024} KB)      ", end="", flush=True)
            time.sleep(UPDATE_INTERVAL)
            continue

        dhbo = compute_hbo(red, ir)
        value, r2 = score_window(dhbo, model)
        if value is None or not np.isfinite(value):
            print("\r  waiting for a full window...      ", end="", flush=True)
            time.sleep(UPDATE_INTERVAL)
            continue

        consecutive_good = consecutive_good + 1 if value < THRESH_GOOD else 0
        elapsed = len(dhbo) / FS_DOWN
        print(render_line(elapsed, value, r2, consecutive_good >= 3), end="", flush=True)
        log_row(log_path, elapsed, value, r2, quality_label(value), current.name)
        time.sleep(UPDATE_INTERVAL)


def run_replay(model, path: Path, red_col, ir_col, speed: float, loop: bool,
               log_path) -> None:
    red_all, ir_all = read_full(path, red_col, ir_col)
    if red_all is None:
        print(f"  could not read a valid recording from {path}", flush=True)
        return
    dhbo_all = compute_hbo(red_all, ir_all)
    if dhbo_all is None or len(dhbo_all) < WINDOW_SAMPLES:
        print(f"  {path.name} is too short to score", flush=True)
        return

    print_banner()
    print(f"  replaying {path.name} ({len(dhbo_all)/FS_DOWN:.0f} s, speed x{speed:g})\n",
          flush=True)
    step = max(1, int(round(UPDATE_INTERVAL * FS_DOWN)))
    consecutive_good = 0
    while True:
        for end in range(WINDOW_SAMPLES, len(dhbo_all) + 1, step):
            value, r2 = score_window(dhbo_all[:end], model)
            if value is None or not np.isfinite(value):
                continue
            consecutive_good = consecutive_good + 1 if value < THRESH_GOOD else 0
            print(render_line(end / FS_DOWN, value, r2, consecutive_good >= 3),
                  end="", flush=True)
            log_row(log_path, end / FS_DOWN, value, r2, quality_label(value), path.name)
            if speed > 0:
                time.sleep(UPDATE_INTERVAL / speed)
        if not loop:
            break
    print("\n\n  replay complete", flush=True)


def read_full(path: Path, red_col: int, ir_col: int):
    try:
        with open(path, "r", errors="ignore") as f:
            lines = f.readlines()
    except OSError:
        return None, None
    data_lines = [ln for ln in lines if ln.strip() and not ln.startswith("#")]
    red, ir = parse_columns(data_lines, red_col, ir_col)
    if red is None:
        return None, None
    live = (red > MIN_INTENSITY) & (ir > MIN_INTENSITY)
    if not live.any():
        return None, None
    first = int(np.argmax(live))
    return red[first:], ir[first:]


def run_selftest(model) -> int:
    """Score a clean and a degraded synthetic window; confirm the pipeline
    and thresholds behave. Returns a process exit code."""
    print_banner()
    print("\n  self-test (no hardware): scoring synthetic windows\n", flush=True)
    cases = [
        ("clean coupling", lambda: synth_intensities(30, "good", seed=1)),
        ("decoupling event", lambda: synth_decouple_window(30, seed=1)),
    ]
    results = {}
    for name, gen in cases:
        dhbo = compute_hbo(*gen())
        value, r2 = score_window(dhbo, model)
        if value is None:
            print(f"  {name}: FAILED to produce a score", flush=True)
            return 1
        label = quality_label(value)
        print(f"  {name:18s} -> "
              f"{paint(label, COLORS[label]):20s} NRMSE={value:.3f}  R2={r2:+.3f}",
              flush=True)
        results[name] = (value, label)

    ok = (results["clean coupling"][1] == "GOOD"
          and results["decoupling event"][1] == "POOR"
          and results["decoupling event"][0] > results["clean coupling"][0])
    if ok:
        print("\n  " + paint("PASS", COLORS["GOOD"])
              + ": clean coupling scores in the good tier and above the"
              " degraded trace.", flush=True)
    else:
        print("\n  " + paint("FAIL", COLORS["POOR"])
              + ": tiers did not separate as expected.", flush=True)
    return 0 if ok else 1


# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Live fNIRS coupling-quality monitor.")
    p.add_argument("--selftest", action="store_true",
                   help="score synthetic clean/degraded windows and exit (no hardware)")
    p.add_argument("--make-demo", metavar="FILE",
                   help="write a synthetic OpenSignals recording to FILE and exit")
    p.add_argument("--demo-quality", choices=("good", "poor", "mixed"), default="mixed",
                   help="quality profile for --make-demo (default: mixed)")
    p.add_argument("--demo-seconds", type=int, default=90,
                   help="length of the --make-demo recording (default: 90)")
    p.add_argument("--replay", metavar="FILE",
                   help="replay an existing recording FILE window-by-window as if live")
    p.add_argument("--speed", type=float, default=8.0,
                   help="replay speed multiplier, 0 for as-fast-as-possible (default: 8)")
    p.add_argument("--loop", action="store_true", help="loop the replay")
    p.add_argument("--watch-dir", action="append", default=None,
                   help="override the OpenSignals directory (repeatable)")
    p.add_argument("--red-col", type=int, default=DEFAULT_RED_COL,
                   help=f"0-based red (660 nm) column (default: {DEFAULT_RED_COL})")
    p.add_argument("--ir-col", type=int, default=DEFAULT_IR_COL,
                   help=f"0-based IR (860 nm) column (default: {DEFAULT_IR_COL})")
    p.add_argument("--no-color", action="store_true", help="disable ANSI colour")
    p.add_argument("--show-r2", action="store_true",
                   help="also show R2 in the readout (secondary; the tier uses NRMSE only)")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    global _use_color, _show_r2
    _use_color = not args.no_color
    _show_r2 = args.show_r2
    if _use_color:
        enable_ansi()

    script_dir = Path(__file__).resolve().parent

    if args.make_demo:
        out = Path(args.make_demo)
        if args.demo_quality == "mixed":
            # clean -> decoupling band -> recovery, so a replay shows the
            # quality drop into the poor tier and the return to good.
            third = args.demo_seconds // 3
            g1 = synth_intensities(third, "good", seed=1)
            bad = synth_intensities(third, "poor", seed=2)
            g2 = synth_intensities(args.demo_seconds - 2 * third, "good", seed=3)
            red = np.concatenate([g1[0], bad[0], g2[0]])
            ir = np.concatenate([g1[1], bad[1], g2[1]])
        else:
            red, ir = synth_intensities(args.demo_seconds, args.demo_quality, seed=3)
        write_opensignals(out, red, ir)
        print(f"wrote synthetic recording: {out}  ({args.demo_seconds} s, "
              f"{args.demo_quality})\nreplay it with:  python {Path(__file__).name} "
              f"--replay \"{out}\"", flush=True)
        return 0

    print("  loading Chronos model (first run downloads ~150 MB)...", flush=True)
    from chronos_wrapper import load_chronos_model
    try:
        model = load_chronos_model()
    except Exception as exc:  # noqa: BLE001
        print(f"\n  ERROR: could not load the Chronos model: {exc}\n"
              "  Check the internet connection for the first run, or that the\n"
              "  pre-cached model on the drive is reachable (HF_HOME).", flush=True)
        return 1
    print("  model ready\n", flush=True)

    if args.selftest:
        return run_selftest(model)

    log_path = open_log(script_dir)
    if log_path:
        print(f"  logging to {log_path}\n", flush=True)

    try:
        if args.replay:
            run_replay(model, Path(args.replay), args.red_col, args.ir_col,
                       args.speed, args.loop, log_path)
        else:
            watch = [Path(d) for d in args.watch_dir] if args.watch_dir else OPENSIGNALS_DIRS
            run_live(model, watch, args.red_col, args.ir_col, log_path)
    except KeyboardInterrupt:
        print("\n\n  monitor stopped", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
