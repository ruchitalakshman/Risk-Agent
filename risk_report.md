# Market Risk Data-Quality Report

- Generated: 2026-11-02T13:52:21  |  Model: `openai/gpt-oss-120b`
- Rows checked: 300  |  Exceptions: 11  |  LLM attempts: 1
- **Overall status: RED**

**Summary:** The data-quality checks identified 11 high-severity exceptions across missing values, outliers, and day-on-day VaR breaches. All issues are flagged as high severity, indicating critical data integrity problems that require immediate investigation. Overall status is red.

| Date | Desk | Issue | Severity | Commentary | Action |
|---|---|---|---|---|---|
| 2025-01-15 | Commodities | outlier | high | Commodities var_99 on 2025-01-15 is an extreme outlier (z-score -6.1). | Validate the underlying trade data and calculation for var_99. |
| 2025-01-15 | Commodities | dod_breach | high | Commodities VaR moved -62% day-on-day on 2025-01-15, exceeding the 30% threshold. | Investigate the cause of the VaR shift and ensure model parameters are correct. |
| 2025-01-15 | Equities | missing_value | high | Equities desk exposure is missing on 2025-01-15. | Verify exposure calculation inputs and repopulate. |
| 2025-01-15 | Rates | missing_value | high | Rates desk reports missing var_99 on 2025-01-15. | Identify source of missing var_99 and restore data. |
| 2025-01-16 | Commodities | dod_breach | high | Commodities VaR increased +143% day-on-day on 2025-01-16, exceeding the 30% threshold. | Check for data spikes or model issues driving the VaR jump. |
| 2025-01-22 | FX | missing_value | high | FX desk has missing pnl on 2025-01-22. | Check data pipeline for pnl feed and reload. |
| 2025-01-29 | Credit | outlier | high | Credit desk pnl on 2025-01-29 is a severe negative outlier (z-score -7.6). | Review credit positions and pnl attribution for errors. |
| 2025-02-26 | FX | outlier | high | FX var_99 on 2025-02-26 is a high positive outlier (z-score 7.5). | Confirm FX market data and VaR model inputs. |
| 2025-02-26 | FX | dod_breach | high | FX VaR rose +147% day-on-day on 2025-02-26, exceeding the 30% threshold. | Review FX market movements and VaR model inputs for anomalies. |
| 2025-02-27 | FX | dod_breach | high | FX VaR fell -60% day-on-day on 2025-02-27, exceeding the 30% threshold. | Assess whether the drop reflects genuine risk change or data error. |
| 2025-03-05 | Rates | outlier | high | Rates desk pnl on 2025-03-05 is a large positive outlier (z-score 7.6). | Inspect rates trade entries and pnl calculation. |
