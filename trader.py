from __future__ import annotations

from dataclasses import dataclass
import pandas as pd


@dataclass(frozen=True)
class TraderConfig:
    """
    Demo trader: generates BUY/SELL signals using a moving-average crossover.
    It is intentionally simple; the focus of this repo is risk + portfolio aggregation.
    """
    fast: int = 20
    slow: int = 100
    trade_size: int = 25  # shares per trade event (capped by cash / position)


def generate_signals(close: pd.Series, fast: int, slow: int) -> pd.Series:
    fast_ma = close.rolling(fast, min_periods=fast).mean()
    slow_ma = close.rolling(slow, min_periods=slow).mean()
    sig = (fast_ma > slow_ma).astype(int)  # 1 long regime, 0 flat regime
    sig.name = "regime"
    return sig


def decide_fill(date: pd.Timestamp, symbol: str, regime_today: int, current_qty: int, cfg: TraderConfig):
    """
    If regime_today == 1: target is to be long (accumulate in chunks).
    If regime_today == 0: target is flat (sell down in chunks).
    Returns (side, qty) or None.
    """
    if regime_today not in (0, 1):
        return None

    if regime_today == 1:
        # accumulate up to some exposure externally controlled by risk limits
        return ("BUY", cfg.trade_size)

    # regime 0: de-risk
    if current_qty <= 0:
        return None
    return ("SELL", min(cfg.trade_size, current_qty))
