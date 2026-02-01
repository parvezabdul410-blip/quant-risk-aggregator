from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import pandas as pd
import requests


@dataclass(frozen=True)
class StooqSpec:
    symbol: str
    interval: str = "d"  # d=day


def stooq_url(spec: StooqSpec) -> str:
    s = spec.symbol.strip().lower()
    return f"https://stooq.com/q/d/l/?s={s}&i={spec.interval}"


def download_csv(symbol: str, cache_dir: Path, force: bool = False, timeout_s: int = 20) -> Path:
    """
    Download daily OHLCV CSV from Stooq into cache_dir.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / f"{symbol.lower().replace('/', '_')}_stooq_d.csv"
    if out.exists() and not force:
        return out

    url = stooq_url(StooqSpec(symbol=symbol))
    resp = requests.get(url, timeout=timeout_s)
    resp.raise_for_status()
    out.write_bytes(resp.content)
    return out


def load_ohlcv(path: Path) -> pd.DataFrame:
    """
    Canonical format:
      index: Date (datetime)
      cols: Open, High, Low, Close, Volume
    """
    df = pd.read_csv(path)
    required = {"Date", "Open", "High", "Low", "Close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing columns {missing}. Columns={list(df.columns)}")

    df["Date"] = pd.to_datetime(df["Date"], utc=False)
    df = df.sort_values("Date").set_index("Date")

    for c in ["Open", "High", "Low", "Close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if "Volume" in df.columns:
        df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce").fillna(0).astype("int64")
    else:
        df["Volume"] = 0

    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    return df
