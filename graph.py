"""LangGraph orchestration: the pipeline as a graph of steps ("nodes") that share a state.

    load_data -> run_checks --(no exceptions)--> no_issues --> save_report
                    |
                    v
                  draft -> validate --valid--------> save_report
                                 ^         |
                                 |         +--invalid, tries left--+
                                 +-----------(retry edge)---------+
                                           |
                                           +--invalid, out of tries--> save_report (marked failed)
"""
import json
import logging
from datetime import datetime
from typing import Optional, TypedDict

import pandas as pd
from jsonschema import ValidationError
from langgraph.graph import END, START, StateGraph

from checks import run_all_checks
from llm import MODEL, draft_once, validate_commentary

log = logging.getLogger("risk_agent.graph")
MAX_ATTEMPTS = 3


class State(TypedDict, total=False):
    """The shared notebook every node reads from and writes to."""
    data_path: str             # where to read the CSV from (ignored if df is supplied)
    df: pd.DataFrame           # the data; the app can pass an uploaded one directly
    dod_threshold: float       # e.g. 0.30 = flag VaR moves bigger than 30% in a day
    z_threshold: float         # e.g. 4.0 = flag values > 4 std-devs from the desk mean
    exceptions: list           # the exception log, as a list of dicts
    commentary: Optional[dict]  # the model's answer (None until drafted)
    feedback: Optional[str]    # why the last answer was rejected (sent back on retry)
    attempts: int
    valid: bool
    status: str


REQUIRED_COLUMNS = {"date", "desk", "var_99", "pnl", "exposure"}


def load_data(state):
    if "df" in state:                       # data handed in directly (e.g. uploaded in the app)
        df = state["df"].copy()
        df["date"] = pd.to_datetime(df["date"])
        log.info("Using supplied data: %d rows", len(df))
    else:
        df = pd.read_csv(state["data_path"], parse_dates=["date"])
        log.info("Loaded %d rows from %s", len(df), state["data_path"])
    missing_cols = REQUIRED_COLUMNS - set(df.columns)
    if missing_cols:                        # fail early with a clear message
        raise ValueError(f"Data is missing required columns: {sorted(missing_cols)}")
    return {"df": df, "attempts": 0}


def run_checks(state):
    exception_log = run_all_checks(
        state["df"],
        dod_threshold=state.get("dod_threshold", 0.30),
        z_threshold=state.get("z_threshold", 4.0),
    )
    exception_log.to_csv("exception_log.csv", index=False)
    log.info("Checks found %d exceptions -> exception_log.csv", len(exception_log))
    return {"exceptions": exception_log.to_dict("records")}


def route_after_checks(state):
    """No problems found -> no need to pay for an LLM call."""
    return "draft" if state["exceptions"] else "no_issues"


def no_issues(state):
    log.info("No exceptions found; skipping the LLM step")
    return {
        "valid": True, "attempts": 0,
        "commentary": {"overall_summary": "No data-quality exceptions were found.",
                       "overall_status": "green", "findings": []},
    }


def draft(state):
    attempt = state["attempts"] + 1
    log.info("Draft attempt %d/%d", attempt, MAX_ATTEMPTS)
    try:
        commentary = draft_once(state["exceptions"], state.get("feedback"),
                                dod_threshold=state.get("dod_threshold", 0.30))
        return {"commentary": commentary, "attempts": attempt}
    except Exception as e:   # network error, bad JSON, no function call...
        log.error("Model call failed on attempt %d: %s", attempt, e)
        return {"commentary": None, "feedback": f"API/parse error: {e}", "attempts": attempt}


def validate(state):
    if state["commentary"] is None:
        return {"valid": False}
    try:
        validate_commentary(state["commentary"], state["exceptions"],
                            dod_threshold=state.get("dod_threshold", 0.30))
        log.info("Validation passed on attempt %d", state["attempts"])
        return {"valid": True, "feedback": None}
    except ValidationError as e:
        log.warning("Validation FAILED on attempt %d: %s", state["attempts"], e.message)
        return {"valid": False, "feedback": e.message}


def route_after_validate(state):
    """The decision point (a 'conditional edge')."""
    if state["valid"]:
        return "save_report"
    if state["attempts"] < MAX_ATTEMPTS:
        return "draft"          # loop back and try again
    return "save_report"        # give up, but still save an auditable record


def save_report(state):
    ok = state.get("valid", False)
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "model": MODEL,
        "rows_checked": len(state["df"]),
        "exceptions_found": len(state["exceptions"]),
        "llm_attempts": state["attempts"],
        "llm_status": "ok" if ok else f"failed: {state.get('feedback')}",
        "commentary": state["commentary"] if ok else None,
    }
    with open("risk_report.json", "w") as f:
        json.dump(report, f, indent=2)
    log.info("Wrote risk_report.json (status=%s)", report["llm_status"])
    return {"status": report["llm_status"]}


def build_graph():
    g = StateGraph(State)
    g.add_node("load_data", load_data)
    g.add_node("run_checks", run_checks)
    g.add_node("no_issues", no_issues)
    g.add_node("draft", draft)
    g.add_node("validate", validate)
    g.add_node("save_report", save_report)

    g.add_edge(START, "load_data")
    g.add_edge("load_data", "run_checks")
    g.add_conditional_edges("run_checks", route_after_checks, ["draft", "no_issues"])
    g.add_edge("no_issues", "save_report")
    g.add_edge("draft", "validate")
    g.add_conditional_edges("validate", route_after_validate, ["draft", "save_report"])
    g.add_edge("save_report", END)
    return g.compile()
