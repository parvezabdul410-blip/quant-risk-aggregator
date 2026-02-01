from __future__ import annotations

import argparse
from pathlib import Path
import json

import matplotlib.pyplot as plt
import pandas as pd

from .data import download_csv, load_ohlcv
from .portfolio import Portfolio, Fill
from .risk import RiskLimits, VaRSpec, rolling_historical_var, compute_drawdown, check_limits
from .trader import TraderConfig, generate_signals, decide_fill


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Real-time PnL and Risk Aggregator (Stooq CSV + simulated fills).")
    p.add_argument("--ticker", required=True, help="Stooq symbol, e.g. spy.us, aapl.us")
    p.add_argument("--start", default=None, help="Start date YYYY-MM-DD")
    p.add_argument("--end", default=None, help="End date YYYY-MM-DD")
    p.add_argument("--cash", type=float, default=100000.0, help="Initial cash")

    # execution costs
    p.add_argument("--slippage-bps", type=float, default=2.0, help="Slippage in bps (applied on fill price)")
    p.add_argument("--commission", type=float, default=1.0, help="Fixed commission per fill")

    # trader (demo)
    p.add_argument("--fast", type=int, default=20, help="Fast MA window")
    p.add_argument("--slow", type=int, default=100, help="Slow MA window")
    p.add_argument("--trade-size", type=int, default=25, help="Shares per trade event")

    # risk
    p.add_argument("--var-window", type=int, default=250, help="Rolling window length for historical VaR")
    p.add_argument("--var-alpha", type=float, default=0.99, help="VaR confidence level (e.g., 0.99)")
    p.add_argument("--max-gross", type=float, default=200000.0, help="Max gross exposure")
    p.add_argument("--max-dd", type=float, default=0.20, help="Max drawdown before alert")
    p.add_argument("--max-var", type=float, default=2500.0, help="Max VaR before alert")

    # IO
    p.add_argument("--cache-dir", default="data", help="Cache directory for downloaded CSV")
    p.add_argument("--out-dir", default="outputs", help="Outputs directory")
    p.add_argument("--force-download", action="store_true", help="Force re-download even if cached")

    return p.parse_args()


def apply_slippage(price: float, side: str, bps: float) -> float:
    slip = bps / 10000.0
    if side == "BUY":
        return price * (1.0 + slip)
    if side == "SELL":
        return price * (1.0 - slip)
    raise ValueError("side must be BUY or SELL")


def main() -> None:
    args = parse_args()
    cache_dir = Path(args.cache_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = download_csv(args.ticker, cache_dir=cache_dir, force=args.force_download)
    ohlcv = load_ohlcv(csv_path)

    if args.start:
        ohlcv = ohlcv.loc[pd.to_datetime(args.start):]
    if args.end:
        ohlcv = ohlcv.loc[:pd.to_datetime(args.end)]

    if len(ohlcv) < max(args.fast, args.slow) + 5:
        raise ValueError("Not enough rows for the MA windows. Use an earlier start or smaller windows.")

    close = ohlcv["Close"].astype(float)
    regime = generate_signals(close, fast=args.fast, slow=args.slow)

    portfolio = Portfolio(initial_cash=float(args.cash))
    limits = RiskLimits(
        max_gross_exposure=float(args.max_gross),
        max_drawdown=float(args.max_dd),
        max_var=float(args.max_var),
    )
    varspec = VaRSpec(window=int(args.var_window), alpha=float(args.var_alpha))
    trader_cfg = TraderConfig(fast=args.fast, slow=args.slow, trade_size=int(args.trade_size))

    # Walk forward day-by-day:
    # - at each day OPEN: optionally generate a fill event (demo trader) and apply it
    # - at each day CLOSE: mark the portfolio, compute rolling risk, log alerts
    pnl_rows = []
    alert_rows = []

    for dt, row in ohlcv.iterrows():
        open_px = float(row["Open"])
        close_px = float(row["Close"])

        # --- simulate a fill at OPEN (demo) ---
        pos = portfolio.get_position(args.ticker)
        reg = int(regime.loc[dt]) if pd.notna(regime.loc[dt]) else 0
        decision = decide_fill(dt, args.ticker, reg, pos.qty, trader_cfg)

        if decision is not None:
            side, qty = decision
            fill_px = apply_slippage(open_px, side=side, bps=float(args.slippage_bps))
            fill = Fill(
                date=dt,
                symbol=args.ticker,
                side=side,
                qty=int(qty),
                price=float(fill_px),
                commission=float(args.commission),
            )
            portfolio.apply_fill(fill)

        # --- mark to market at CLOSE ---
        snap = portfolio.snapshot(date=dt, prices={args.ticker: close_px})
        pnl_rows.append(snap)

    pnl_df = pd.DataFrame(pnl_rows).set_index("Date")
    pnl_df["Drawdown"] = compute_drawdown(pnl_df["Equity"])

    # Compute portfolio daily PnL for VaR: delta in equity
    pnl_df["DailyPnL"] = pnl_df["Equity"].diff().fillna(0.0)
    pnl_df["VaR"] = rolling_historical_var(pnl_df["DailyPnL"], window=varspec.window, alpha=varspec.alpha)

    # Alerts pass
    for dt, r in pnl_df.iterrows():
        snap = r.to_dict()
        var_val = float(snap.get("VaR")) if "VaR" in snap else None
        alert_rows.extend(check_limits(dt, snap, var_val, limits))

    alerts_df = pd.DataFrame(alert_rows)
    if len(alerts_df):
        alerts_df = alerts_df.sort_values(["Date", "Type"])

    # Positions snapshot table (end-of-run)
    pos = portfolio.get_position(args.ticker)
    positions_df = pd.DataFrame([{
        "Symbol": args.ticker,
        "Qty": pos.qty,
        "AvgCost": pos.avg_cost,
        "Cash": portfolio.cash,
        "RealizedPnL": portfolio.realized_pnl,
    }])

    # Write outputs
    pnl_path = out_dir / "pnl_timeseries.csv"
    pos_path = out_dir / "positions.csv"
    alerts_path = out_dir / "alerts.csv"
    report_path = out_dir / "risk_report.json"
    plot_path = out_dir / "equity_curve.png"

    pnl_df.to_csv(pnl_path)
    positions_df.to_csv(pos_path, index=False)
    if len(alerts_df):
        alerts_df.to_csv(alerts_path, index=False)
    else:
        alerts_path.write_text("", encoding="utf-8")

    report = {
        "symbol": args.ticker,
        "start": str(pnl_df.index.min().date()),
        "end": str(pnl_df.index.max().date()),
        "initial_cash": float(args.cash),
        "final_equity": float(pnl_df["Equity"].iloc[-1]),
        "final_drawdown": float(pnl_df["Drawdown"].iloc[-1]),
        "max_drawdown": float(pnl_df["Drawdown"].max()),
        "max_gross_exposure": float(pnl_df["GrossExposure"].max()),
        "max_var": float(pnl_df["VaR"].max(skipna=True)) if pnl_df["VaR"].notna().any() else None,
        "num_fills": len(portfolio.fills),
        "num_alerts": int(len(alerts_df)) if len(alerts_df) else 0,
        "limits": {
            "max_gross_exposure": limits.max_gross_exposure,
            "max_drawdown": limits.max_drawdown,
            "max_var": limits.max_var,
        },
        "var": {"window": varspec.window, "alpha": varspec.alpha},
        "execution": {"slippage_bps": float(args.slippage_bps), "commission": float(args.commission)},
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Plot
    plt.figure()
    pnl_df["Equity"].plot()
    plt.title(f"Equity (with risk tracking): {args.ticker.upper()}")
    plt.xlabel("Date")
    plt.ylabel("Equity")
    plt.tight_layout()
    plt.savefig(plot_path)

    print("Done.")
    print(f"Data CSV:   {csv_path}")
    print(f"Outputs:    {out_dir.resolve()}")
    print(f"  - {pnl_path.name}")
    print(f"  - {pos_path.name}")
    print(f"  - {alerts_path.name}")
    print(f"  - {report_path.name}")
    print(f"  - {plot_path.name}")


if __name__ == "__main__":
    main()
