from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RiskLimits:
    max_gross_exposure: float = 200_000.0
    max_drawdown: float = 0.20
    max_var: float = 2_500.0  # currency units (e.g., dollars)


@dataclass(frozen=True)
class VaRSpec:
    window: int = 250
    alpha: float = 0.99  # 0.99 => 99% VaR


def rolling_historical_var(pnl_series: pd.Series, window: int, alpha: float) -> pd.Series:
    """
    Historical VaR on PnL (not returns):
      VaR_t = -quantile(pnl_{t-window+1..t}, 1-alpha)
    If PnL is negative at left tail, VaR becomes positive number.
    """
    if window < 20:
        raise ValueError("window too small; use >= 20")

    def var_of_window(x: np.ndarray) -> float:
        q = np.quantile(x, 1.0 - alpha)
        return float(max(0.0, -q))

    vals = pnl_series.astype(float).to_numpy()
    out = np.full_like(vals, fill_value=np.nan, dtype=float)
    for i in range(window - 1, len(vals)):
        out[i] = var_of_window(vals[i - window + 1 : i + 1])
    return pd.Series(out, index=pnl_series.index, name="VaR")


def compute_drawdown(equity: pd.Series) -> pd.Series:
    peak = equity.cummax()
    dd = (peak - equity) / peak.replace(0, np.nan)
    return dd.fillna(0.0).rename("Drawdown")


def check_limits(
    date: pd.Timestamp,
    snapshot: Dict,
    var_value: Optional[float],
    limits: RiskLimits,
) -> List[Dict]:
    alerts: List[Dict] = []

    gross = float(snapshot["GrossExposure"])
    dd = float(snapshot.get("Drawdown", 0.0))
    eq = float(snapshot["Equity"])

    if gross > limits.max_gross_exposure:
        alerts.append({"Date": date, "Type": "GROSS_EXPOSURE", "Value": gross, "Limit": limits.max_gross_exposure})

    if dd >= limits.max_drawdown:
        alerts.append({"Date": date, "Type": "DRAWDOWN", "Value": dd, "Limit": limits.max_drawdown})

    if var_value is not None and not np.isnan(var_value) and var_value > limits.max_var:
        alerts.append({"Date": date, "Type": "VAR", "Value": float(var_value), "Limit": limits.max_var})

    # sanity
    if eq <= 0:
        alerts.append({"Date": date, "Type": "EQUITY_NONPOSITIVE", "Value": eq, "Limit": 0})

    return alerts
