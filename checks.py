"""Stage 1-4: automated data-quality checks + exception log.

Every check returns a list of "exceptions" (dicts). Together they form the
exception log, which is later fed to the LLM and saved for audit.
"""
import numpy as np
import pandas as pd

NUMERIC_COLS = ["var_99", "pnl", "exposure"]
DOD_THRESHOLD = 0.30   # flag day-on-day change bigger than 30%
Z_THRESHOLD = 4.0      # flag values more than 4 std-devs from the desk's mean


def _exc(check, row, column, value, detail, severity):
    """Build one standardized exception record."""
    return {
        "check": check,
        "date": row["date"].strftime("%Y-%m-%d"),
        "desk": row["desk"],
        "column": column,
        "value": None if pd.isna(value) else float(value),
        "detail": detail,
        "severity": severity,
    }


def check_missing(df):
    """Flag any NaN in the numeric columns."""
    out = []
    for col in NUMERIC_COLS:
        for _, row in df[df[col].isna()].iterrows():
            out.append(_exc("missing_value", row, col, np.nan,
                            f"{col} is missing", "high"))
    return out


def check_outliers(df, z_threshold=Z_THRESHOLD):
    """Flag values far from the desk's own average (z-score), per desk."""
    out = []
    for desk, g in df.groupby("desk"):
        for col in NUMERIC_COLS:
            mean, std = g[col].mean(), g[col].std()
            if std == 0 or pd.isna(std):
                continue
            z = (g[col] - mean) / std
            for idx in g.index[z.abs() > z_threshold]:
                out.append(_exc("outlier", df.loc[idx], col, df.loc[idx, col],
                                f"z-score {z[idx]:.1f} vs {desk} history", "high"))
    return out


def check_dod_breach(df, threshold=DOD_THRESHOLD):
    """Flag day-on-day % change in VaR above the threshold, per desk."""
    out = []
    df = df.sort_values(["desk", "date"]).copy()   # copy: never modify the caller's data
    df["var_chg"] = df.groupby("desk")["var_99"].pct_change()
    for _, row in df[df["var_chg"].abs() > threshold].iterrows():
        sev = "high" if abs(row["var_chg"]) > 2 * threshold else "medium"
        out.append(_exc("dod_breach", row, "var_99", row["var_99"],
                        f"VaR changed {row['var_chg']:+.0%} day-on-day "
                        f"(limit ±{threshold:.0%})", sev))
    return out


EXCEPTION_COLUMNS = ["check", "date", "desk", "column", "value", "detail", "severity"]


def run_all_checks(df, dod_threshold=DOD_THRESHOLD, z_threshold=Z_THRESHOLD):
    """Run every check and return the combined exception log as a DataFrame."""
    exceptions = (check_missing(df) + check_outliers(df, z_threshold)
                  + check_dod_breach(df, dod_threshold))
    return pd.DataFrame(exceptions, columns=EXCEPTION_COLUMNS)  # columns kept even if empty
