"""Stage 0: generate sample market-risk data with deliberately planted problems.

Each row = one trading desk on one business day, with:
  - var_99   : 1-day 99% Value-at-Risk (USD). "How much could we lose in a day,
               with 99% confidence?" Core market-risk number.
  - pnl      : profit & loss for the day (USD)
  - exposure : total notional exposure (USD)

We plant: missing values, extreme outliers, and big day-on-day jumps,
so we KNOW what our checks should catch.
"""
import numpy as np
import pandas as pd

rng = np.random.default_rng(seed=42)  # fixed seed -> same data every run (reproducible)

dates = pd.bdate_range("2025-01-01", periods=60)  # 60 business days
desks = ["Rates", "FX", "Equities", "Credit", "Commodities"]
base_var = {"Rates": 2.0e6, "FX": 1.2e6, "Equities": 3.0e6, "Credit": 1.8e6, "Commodities": 0.9e6}

rows = []
for desk in desks:
    # VaR drifts slowly day to day (random walk with small steps)
    var = base_var[desk] * np.cumprod(1 + rng.normal(0, 0.02, len(dates)))
    pnl = rng.normal(0, base_var[desk] * 0.4, len(dates))
    exposure = var * rng.uniform(40, 60, len(dates))
    for i, d in enumerate(dates):
        rows.append({"date": d, "desk": desk, "var_99": var[i], "pnl": pnl[i], "exposure": exposure[i]})

df = pd.DataFrame(rows)

# ---- plant problems (we remember where, to verify the checks later) ----
df.loc[10, "var_99"] = np.nan            # missing VaR
df.loc[75, "pnl"] = np.nan               # missing P&L
df.loc[130, "exposure"] = np.nan         # missing exposure
df.loc[45, "pnl"] = 9.0e7                # absurd P&L outlier
df.loc[200, "pnl"] = -8.5e7              # absurd negative outlier
df.loc[100, "var_99"] *= 2.5             # VaR jumps 150% in one day (breach)
df.loc[250, "var_99"] *= 0.4             # VaR collapses 60% (breach)

df.to_csv("market_risk_sample.csv", index=False)
print(f"Wrote market_risk_sample.csv with {len(df)} rows")
