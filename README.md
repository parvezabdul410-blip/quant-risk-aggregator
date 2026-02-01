# quant-risk-aggregator — Real-time PnL + Risk Aggregator (Python)

A quant-dev style **portfolio + risk monitoring system** that:
- downloads **market data from an online CSV source** (Stooq daily OHLCV),
- simulates a stream of **fills** (trades) to update positions,
- computes **portfolio PnL + exposures** day-by-day,
- calculates rolling **Drawdown** and **Historical VaR**,
- writes **alerts** when risk limits are breached.

This is the kind of component you’d run alongside an OMS/EMS: it ingests prices + fills and answers “what’s my risk right now?”

---

## Outputs

Generated into `outputs/`:

- `pnl_timeseries.csv` — daily portfolio state + risk (equity, realized/unrealized PnL, exposures, drawdown, VaR)
- `positions.csv` — final position snapshot (qty, avg cost, cash, realized PnL)
- `alerts.csv` — risk limit breach log (may be empty)
- `risk_report.json` — summary report (max DD, max gross, max VaR, etc.)
- `equity_curve.png` — equity curve plot

---

## Data Source (Online CSV)

The engine downloads daily OHLCV from Stooq:

`https://stooq.com/q/d/l/?s=<symbol>&i=d`

Example symbols:
- `spy.us`
- `aapl.us`
- `msft.us`

CSV schema is typically:
`Date,Open,High,Low,Close,Volume`

Downloads are cached locally in `data/` to make reruns faster.

---

## Quickstart (macOS zsh / Linux)

### 1) Create and activate a virtual environment
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2) Install dependencies
```bash
pip install -r requirements.txt
```

### 3) Install the package (important)
Because the code uses a `src/` layout, install it into your venv:
```bash
pip install -e .
```

### 4) Run (auto-downloads the CSV)
```bash
python3 -m quant_risk_engine.run --ticker spy.us --start 2015-01-01 --cash 100000
```

---

## Example: Tighter Limits + VaR Config

```bash
python3 -m quant_risk_engine.run \
  --ticker aapl.us \
  --start 2015-01-01 \
  --cash 100000 \
  --trade-size 25 \
  --slippage-bps 2 \
  --commission 1.0 \
  --var-window 250 \
  --var-alpha 0.99 \
  --max-gross 150000 \
  --max-dd 0.15 \
  --max-var 2000
```

---

## How It Works (High Level)

1. **Download/Load Prices**
   - Pull daily OHLCV CSV from Stooq and load to a DataFrame.

2. **Generate Demo Fills (Trader)**
   - A simple MA regime model decides whether to BUY (accumulate) or SELL (de-risk).
   - Trades fill at the **day’s OPEN** with slippage + commission.

3. **Mark-to-Market**
   - Portfolio is valued at the **day’s CLOSE**.

4. **Risk Computation**
   - **Drawdown** computed from the equity curve.
   - **Historical VaR** computed using a rolling window on **DailyPnL** (equity differences).

5. **Limit Checks + Alerts**
   - If limits are breached, rows are appended to `alerts.csv`.

---

## Repo Structure

```
src/quant_risk_engine/
  data.py        # online CSV download + load
  portfolio.py   # positions, avg-cost, PnL accounting
  risk.py        # drawdown, VaR, limit checks
  trader.py      # demo fill generator (signals -> fills)
  run.py         # CLI entry point
data/            # cached CSV downloads
outputs/         # generated reports and plots
```

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'quant_risk_engine'`
You likely skipped the editable install:
```bash
pip install -e .
```

### “Not enough rows for the MA windows”
Use an earlier `--start` date or smaller MA windows:
```bash
python3 -m quant_risk_engine.run --ticker spy.us --start 2000-01-01 --fast 10 --slow 50
```

---

## Interview-Grade Upgrades
- Multi-asset portfolio (N tickers) with netting
- Real fills ingestion (CSV trade blotter or OMS log)
- Intraday bars (minute data) + true streaming loop
- Execution realism: partial fills, volume participation, limit orders
- Unit tests for accounting invariants (PnL consistency, exposure checks)

---

## License
Educational use.
