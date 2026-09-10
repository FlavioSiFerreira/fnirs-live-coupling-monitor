"""
Forecasting evaluation metrics.
All functions take (ground_truth, prediction) as 1D arrays and return a scalar.
"""
import numpy as np

def mae(y_true, y_pred):
    return float(np.mean(np.abs(y_true - y_pred)))

def rmse(y_true, y_pred):
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))

def mape(y_true, y_pred):
    """Mean Absolute Percentage Error. Returns NaN if any y_true == 0."""
    mask = y_true != 0
    if not mask.any():
        return float("nan")
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)

def smape(y_true, y_pred):
    """Symmetric Mean Absolute Percentage Error (0-200 scale)."""
    denom = np.abs(y_true) + np.abs(y_pred)
    mask = denom != 0
    if not mask.any():
        return float("nan")
    return float(np.mean(2.0 * np.abs(y_true[mask] - y_pred[mask]) / denom[mask]) * 100)

def r_squared(y_true, y_pred):
    """Coefficient of determination (R^2)."""
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    if ss_tot == 0:
        return float("nan")
    return float(1.0 - ss_res / ss_tot)

def nrmse(y_true, y_pred):
    """Normalized RMSE (divided by signal range). Scale-independent error measure."""
    signal_range = float(np.max(y_true) - np.min(y_true))
    if signal_range == 0:
        return float("nan")
    return rmse(y_true, y_pred) / signal_range

def dtw_distance(y_true, y_pred):
    """
    Dynamic Time Warping distance (shape similarity).
    Uses a simple O(n^2) implementation suitable for horizon-length arrays.
    """
    n, m = len(y_true), len(y_pred)
    cost = np.full((n + 1, m + 1), np.inf)
    cost[0, 0] = 0.0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d = abs(float(y_true[i - 1]) - float(y_pred[j - 1]))
            cost[i, j] = d + min(cost[i - 1, j], cost[i, j - 1], cost[i - 1, j - 1])
    return float(cost[n, m] / max(n, m))

def phase_error(y_true, y_pred):
    """
    Phase error via cross-correlation lag.
    Returns the lag (in samples) where cross-correlation is maximized.
    Positive = prediction lags behind ground truth.
    """
    y_true_centered = y_true - np.mean(y_true)
    y_pred_centered = y_pred - np.mean(y_pred)
    correlation = np.correlate(y_true_centered, y_pred_centered, mode="full")
    best_lag = np.argmax(correlation) - (len(y_true) - 1)
    return float(best_lag)

METRIC_FUNCTIONS = {
    "MAE": mae,
    "RMSE": rmse,
    "NRMSE": nrmse,
    "MAPE": mape,
    "sMAPE": smape,
    "R2": r_squared,
    "DTW": dtw_distance,
    "Phase_Lag": phase_error,
}

def compute_all_metrics(
    y_true,
    y_pred,
):
    return {name: fn(y_true, y_pred) for name, fn in METRIC_FUNCTIONS.items()}

if __name__ == "__main__":
    rng = np.random.default_rng(42)
    t = np.linspace(0, 4 * np.pi, 128)
    y_true = np.sin(t).astype(np.float32)
    y_pred = (np.sin(t + 0.2) * 0.95).astype(np.float32)

    results = compute_all_metrics(y_true, y_pred)
    print("Metrics (sine vs shifted/scaled sine):")
    for name, val in results.items():
        print(f"  {name}: {val:.4f}", flush=True)
