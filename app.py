"""Streamlit front end.  Run:  streamlit run app.py

The app is a thin layer: it collects settings, calls the SAME LangGraph pipeline
as main.py, then displays whatever the pipeline returns.
"""
import json
import logging
import os
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from graph import MAX_ATTEMPTS, REQUIRED_COLUMNS, build_graph

load_dotenv()
SAMPLE_PATH = "market_risk_sample.csv"

st.set_page_config(page_title="Risk Data Validation Agent", page_icon="📊", layout="wide")

# Streamlit re-runs this whole script on every click, so only attach log handlers once.
_root = logging.getLogger()
if not any(isinstance(h, logging.FileHandler) for h in _root.handlers):
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.FileHandler("pipeline.log")])
    logging.getLogger("httpx").setLevel(logging.WARNING)


def clean(text):
    """The model sometimes emits special hyphens/spaces; normalise for display."""
    return str(text).replace("‑", "-").replace(" ", " ")


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("Settings")
    source = st.radio("Data source", ["Sample data", "Upload CSV"])
    uploaded = None
    if source == "Upload CSV":
        uploaded = st.file_uploader("CSV with columns: " + ", ".join(sorted(REQUIRED_COLUMNS)),
                                    type="csv")
    st.subheader("Check thresholds")
    dod_pct = st.slider("Day-on-day VaR change limit (%)", 5, 100, 30, step=5,
                        help="Flag a desk when its VaR moves more than this in one day.")
    z_thr = st.slider("Outlier z-score limit", 2.0, 6.0, 4.0, step=0.5,
                      help="Flag values this many standard deviations from the desk's own average.")
    can_run = source == "Sample data" or uploaded is not None
    run = st.button("Run analysis", type="primary", disabled=not can_run, width="stretch")
    if not os.getenv("GROQ_API_KEY"):
        st.warning("GROQ_API_KEY not found in .env - checks will run but AI commentary will fail.")

st.title("📊 Risk Data Validation & AI Reporting Agent")
st.caption("Automated data-quality checks on market-risk data, then LLM-drafted commentary "
           "that is validated before it is trusted.")

# ------------------------------------------------------------------ run pipeline
if run:
    try:
        df_in = pd.read_csv(uploaded) if uploaded is not None else pd.read_csv(SAMPLE_PATH)
        with st.spinner("Running checks and drafting commentary..."):
            final = build_graph().invoke({
                "df": df_in,
                "dod_threshold": dod_pct / 100,
                "z_threshold": z_thr,
            })
        st.session_state["result"] = final
        st.session_state["params"] = (dod_pct, z_thr)
    except Exception as e:
        st.session_state.pop("result", None)
        st.error(f"Could not run the analysis: {e}")

result = st.session_state.get("result")
if result is None:
    st.info("Choose settings in the sidebar and click **Run analysis**.")
    st.stop()

# ------------------------------------------------------------------ results
exceptions = pd.DataFrame(result["exceptions"])
commentary = result["commentary"] if result.get("valid") else None
n_high = int((exceptions["severity"] == "high").sum()) if len(exceptions) else 0

if commentary:
    status = commentary["overall_status"]
    banner = {"red": st.error, "amber": st.warning, "green": st.success}[status]
    banner(f"**{status.upper()}** - {clean(commentary['overall_summary'])}")
else:
    st.error("The AI commentary could not be validated "
             f"({result.get('feedback') or 'unknown error'}). "
             "The data-quality results below are still valid - they come from code, not the AI.")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Rows checked", len(result["df"]))
c2.metric("Exceptions found", len(exceptions))
c3.metric("High severity", n_high)
c4.metric("LLM attempts", f"{result['attempts']} / {MAX_ATTEMPTS}")

tab_ai, tab_exc, tab_chart, tab_audit = st.tabs(
    ["AI commentary", "Exceptions", "VaR chart", "Audit trail"])

# ---- AI commentary
with tab_ai:
    if commentary and commentary["findings"]:
        f = pd.DataFrame(commentary["findings"])
        f = f[["date", "desk", "issue_type", "severity", "commentary", "recommended_action"]]
        f = f.sort_values(["date", "desk"]).map(clean)
        st.dataframe(f, hide_index=True, width="stretch", column_config={
            "commentary": st.column_config.TextColumn(width="large"),
            "recommended_action": st.column_config.TextColumn("action", width="large"),
        })
        st.caption("Every row above passed 4 automated checks: schema, coverage (one per exception), "
                   "consistency (severity/status match the log) and number verification.")
    elif commentary:
        st.success("No exceptions found - nothing to comment on.")
    else:
        st.warning("No validated commentary available for this run.")

# ---- Exceptions
with tab_exc:
    if exceptions.empty:
        st.success("No exceptions found at these thresholds.")
    else:
        a, b, c = st.columns(3)
        pick_check = a.multiselect("Check", sorted(exceptions["check"].unique()),
                                   default=sorted(exceptions["check"].unique()))
        pick_desk = b.multiselect("Desk", sorted(exceptions["desk"].unique()),
                                  default=sorted(exceptions["desk"].unique()))
        pick_sev = c.multiselect("Severity", ["high", "medium", "low"],
                                 default=["high", "medium", "low"])
        view = exceptions[exceptions["check"].isin(pick_check)
                          & exceptions["desk"].isin(pick_desk)
                          & exceptions["severity"].isin(pick_sev)]
        st.dataframe(view, hide_index=True, width="stretch")
        st.download_button("Download exception log (CSV)", exceptions.to_csv(index=False),
                           "exception_log.csv", "text/csv")

# ---- Chart
with tab_chart:
    data = result["df"].copy()
    data["date"] = pd.to_datetime(data["date"])
    desk = st.selectbox("Desk", sorted(data["desk"].unique()))
    d = data[data["desk"] == desk]
    line = alt.Chart(d).mark_line().encode(
        x=alt.X("date:T", title="Date"),
        y=alt.Y("var_99:Q", title="1-day 99% VaR (USD)"),
        tooltip=["date:T", alt.Tooltip("var_99:Q", format=",.0f")],
    )
    layers = [line]
    if not exceptions.empty:
        pts = exceptions[(exceptions["desk"] == desk) & (exceptions["column"] == "var_99")
                         & exceptions["value"].notna()].copy()
        if not pts.empty:
            pts["date"] = pd.to_datetime(pts["date"])
            layers.append(alt.Chart(pts).mark_point(size=140, filled=True).encode(
                x="date:T", y="value:Q", color=alt.Color("check:N", title="Flagged by"),
                tooltip=["date:T", "check:N", "detail:N", alt.Tooltip("value:Q", format=",.0f")]))
    st.altair_chart(alt.layer(*layers).interactive(), width="stretch")
    st.caption("Dots mark days where this desk's VaR was flagged. "
               "Missing values can't be drawn - see the Exceptions tab.")

# ---- Audit trail
with tab_audit:
    st.markdown("**What happened in this run** (from `pipeline.log`):")
    log_path = Path("pipeline.log")
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-25:]
        st.code("\n".join(lines), language="text")
    report_path = Path("risk_report.json")
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        with st.expander("Saved report (risk_report.json)"):
            st.json(report)
        st.download_button("Download report (JSON)", json.dumps(report, indent=2),
                           "risk_report.json", "application/json")
