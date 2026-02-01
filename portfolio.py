from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional
import pandas as pd


@dataclass
class Fill:
    date: pd.Timestamp
    symbol: str
    side: str           # BUY or SELL
    qty: int
    price: float
    commission: float


@dataclass
class Position:
    symbol: str
    qty: int = 0
    avg_cost: float = 0.0  # average cost per share

    def market_value(self, price: float) -> float:
        return self.qty * price


class Portfolio:
    """
    Single-currency, single-symbol friendly, but written to generalize to multi-symbol.
    Accounting:
      - Avg cost tracking for realized PnL
      - Cash updates with commissions
    """
    def __init__(self, initial_cash: float):
        if initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.positions: Dict[str, Position] = {}
        self.realized_pnl = 0.0
        self.fills: List[Fill] = []

    def get_position(self, symbol: str) -> Position:
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol=symbol)
        return self.positions[symbol]

    def apply_fill(self, fill: Fill) -> None:
        if fill.qty <= 0:
            raise ValueError("fill qty must be positive")
        if fill.side not in ("BUY", "SELL"):
            raise ValueError("fill.side must be BUY or SELL")

        pos = self.get_position(fill.symbol)
        qty = fill.qty
        px = float(fill.price)
        comm = float(fill.commission)

        if fill.side == "BUY":
            total_cost = qty * px + comm
            if total_cost > self.cash:
                # clamp to affordable
                max_qty = int((self.cash - comm) // px)
                if max_qty <= 0:
                    return
                qty = max_qty
                total_cost = qty * px + comm
            # update avg cost
            new_qty = pos.qty + qty
            if new_qty == 0:
                pos.avg_cost = 0.0
            else:
                pos.avg_cost = (pos.avg_cost * pos.qty + px * qty) / new_qty
            pos.qty = new_qty
            self.cash -= total_cost
        else:
            # SELL
            sell_qty = min(qty, pos.qty)  # no shorting in this demo
            if sell_qty <= 0:
                return
            proceeds = sell_qty * px - comm
            # realized pnl = (sell_px - avg_cost) * qty - comm
            self.realized_pnl += (px - pos.avg_cost) * sell_qty - comm
            pos.qty -= sell_qty
            if pos.qty == 0:
                pos.avg_cost = 0.0
            self.cash += proceeds

        self.fills.append(Fill(date=fill.date, symbol=fill.symbol, side=fill.side, qty=qty, price=px, commission=comm))

    def snapshot(self, date: pd.Timestamp, prices: Dict[str, float]) -> Dict:
        gross = 0.0
        net = 0.0
        mv_total = 0.0
        unreal = 0.0

        for sym, pos in self.positions.items():
            px = float(prices.get(sym, 0.0))
            mv = pos.market_value(px)
            mv_total += mv
            gross += abs(mv)
            net += mv
            unreal += (px - pos.avg_cost) * pos.qty if pos.qty != 0 else 0.0

        equity = self.cash + mv_total
        return {
            "Date": date,
            "Cash": self.cash,
            "MarketValue": mv_total,
            "Equity": equity,
            "RealizedPnL": self.realized_pnl,
            "UnrealizedPnL": unreal,
            "GrossExposure": gross,
            "NetExposure": net,
        }
