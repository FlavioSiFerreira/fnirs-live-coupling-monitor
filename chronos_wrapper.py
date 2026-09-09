"""Chronos T5 Small wrapper for live fNIRS coupling-quality scoring.

Chronos is Amazon's model and is not redistributed here. The checkpoint is
resolved in this order:

1. the CHRONOS_LOCAL_DIR environment variable, if it holds a model folder
2. ./models/chronos-t5-small next to this file, which is the offline route
3. the Hugging Face Hub identifier amazon/chronos-t5-small, needs internet once
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import torch
from chronos import ChronosPipeline

CHRONOS_MODEL_ID = "amazon/chronos-t5-small"
LOCAL_MODEL_DIR = Path(__file__).resolve().parent / "models" / "chronos-t5-small"

CONTEXT_LEN = 60       # 6 s of 10 Hz signal
HORIZON_LEN = 20       # 2 s forecast horizon


def resolve_checkpoint() -> str:
    """Return a local model folder if one is present, else the Hub identifier."""
    env_dir = os.environ.get("CHRONOS_LOCAL_DIR", "").strip()
    if env_dir:
        candidate = Path(env_dir)
        if (candidate / "config.json").is_file():
            return str(candidate)
        print(f"  CHRONOS_LOCAL_DIR is set but {candidate} has no config.json, "
              f"falling back to the Hub.", flush=True)
    if (LOCAL_MODEL_DIR / "config.json").is_file():
        return str(LOCAL_MODEL_DIR)
    return CHRONOS_MODEL_ID


def _from_pretrained(checkpoint):
    """Load the checkpoint, tolerating the transformers rename of torch_dtype."""
    try:
        return ChronosPipeline.from_pretrained(
            checkpoint, device_map="cpu", dtype=torch.float32)
    except TypeError:
        # transformers below 4.56 only accepts the older keyword
        return ChronosPipeline.from_pretrained(
            checkpoint, device_map="cpu", torch_dtype=torch.float32)


def load_chronos_model():
    """Load Chronos T5 Small onto the CPU."""
    checkpoint = resolve_checkpoint()
    from_hub = checkpoint == CHRONOS_MODEL_ID
    where = "Hugging Face Hub" if from_hub else "local folder"
    print(f"Loading Chronos T5 Small from the {where}...", flush=True)
    if from_hub:
        print("  about 190 MB is downloaded the first time", flush=True)
    try:
        pipeline = _from_pretrained(checkpoint)
    except Exception as exc:                       # noqa: BLE001 - user facing
        raise RuntimeError(
            "could not load Chronos T5 Small.\n"
            f"  tried:  {checkpoint}\n"
            f"  reason: {exc}\n\n"
            "  If this machine has no internet, download the model on another\n"
            "  machine and copy it into:\n"
            f"    {LOCAL_MODEL_DIR}\n"
            "  See the offline section of README.md."
        ) from exc
    print("Chronos model loaded.", flush=True)
    return pipeline


def chronos_forecast_single(pipeline, context, horizon_len=HORIZON_LEN):
    """Forecast horizon_len steps ahead from a single 1D context array.

    Returns the median prediction as a 1D float32 array.
    """
    context_tensor = torch.tensor(np.asarray(context, dtype=np.float32)).unsqueeze(0)
    forecast = pipeline.predict(
        context_tensor,
        prediction_length=horizon_len,
        num_samples=1,
    )
    return forecast[0, 0].numpy().astype(np.float32)


def chronos_forecast_batch(pipeline, contexts, horizon_len=HORIZON_LEN):
    """Forecast each context in a sequence of 1D arrays."""
    return [chronos_forecast_single(pipeline, ctx, horizon_len) for ctx in contexts]


if __name__ == "__main__":
    print("Testing the Chronos wrapper...", flush=True)
    model = load_chronos_model()
    t = np.linspace(0, 6 * np.pi, CONTEXT_LEN)
    prediction = chronos_forecast_single(model, np.sin(t).astype(np.float32))
    print(f"  prediction shape {prediction.shape}, "
          f"range [{prediction.min():.4f}, {prediction.max():.4f}]", flush=True)
    print("Chronos wrapper OK.", flush=True)
