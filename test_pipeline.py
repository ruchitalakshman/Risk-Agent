"""Offline tests (no API calls). Run: python -m pytest -q"""
import copy

import pandas as pd
import pytest
from jsonschema import ValidationError

import graph
from checks import run_all_checks
from llm import validate_commentary

EXC = [
    {"check": "missing_value", "date": "2025-01-15", "desk": "Rates", "column": "var_99",
     "value": None, "detail": "var_99 is missing", "severity": "high"},
]
GOOD = {
    "overall_summary": "One issue.", "overall_status": "red",
    "findings": [{"desk": "Rates", "date": "2025-01-15", "issue_type": "missing_value",
                  "severity": "high", "commentary": "x", "recommended_action": "y"}],
}


def test_checks_find_all_planted_problems():
    df = pd.read_csv("market_risk_sample.csv", parse_dates=["date"])
    log = run_all_checks(df)
    counts = log["check"].value_counts().to_dict()
    assert counts["missing_value"] == 3
    assert counts["outlier"] >= 2          # the two absurd P&L values (plus VaR spikes)
    assert counts["dod_breach"] >= 2       # the two planted VaR jumps


def test_good_commentary_passes():
    validate_commentary(GOOD, EXC)


@pytest.mark.parametrize("mutate", [
    lambda c: c["findings"][0].update(desk="Narnia"),          # invented desk
    lambda c: c["findings"][0].update(severity="low"),         # wrong severity
    lambda c: c.update(overall_status="green"),                # wrong status
    lambda c: c["findings"].clear(),                           # missing findings (schema minItems)
    lambda c: c["findings"][0].update(issue_type="magic"),     # not in enum
    lambda c: c["findings"].append(copy.deepcopy(c["findings"][0])),  # duplicate
    lambda c: c.update(overall_summary="All twelve checks failed."),  # invented number
])
def test_bad_commentary_is_rejected(mutate):
    bad = copy.deepcopy(GOOD)
    mutate(bad)
    with pytest.raises(ValidationError):
        validate_commentary(bad, EXC)


def test_graph_retries_then_succeeds(monkeypatch):
    """First answer is bad, second is good -> graph should loop once and succeed."""
    answers = [dict(GOOD, overall_status="green"), GOOD]
    monkeypatch.setattr(graph, "draft_once", lambda exc, fb=None, **kw: answers.pop(0))
    monkeypatch.setattr(graph, "run_all_checks", lambda df, **kw: pd.DataFrame(EXC))
    final = graph.build_graph().invoke({"data_path": "market_risk_sample.csv"})
    assert final["valid"] is True and final["attempts"] == 2


def test_graph_gives_up_after_max_attempts(monkeypatch):
    monkeypatch.setattr(graph, "draft_once", lambda exc, fb=None, **kw: dict(GOOD, overall_status="green"))
    monkeypatch.setattr(graph, "run_all_checks", lambda df, **kw: pd.DataFrame(EXC))
    final = graph.build_graph().invoke({"data_path": "market_risk_sample.csv"})
    assert final["valid"] is False and final["attempts"] == graph.MAX_ATTEMPTS


def test_no_exceptions_skips_llm(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("LLM must not be called when there is nothing to report")
    monkeypatch.setattr(graph, "draft_once", boom)
    # absurdly loose thresholds + data without missing cells -> nothing flagged
    df = pd.read_csv("market_risk_sample.csv", parse_dates=["date"]).dropna()
    final = graph.build_graph().invoke({"df": df, "dod_threshold": 50.0, "z_threshold": 50.0})
    assert final["valid"] is True and final["commentary"]["overall_status"] == "green"


def test_threshold_changes_results():
    df = pd.read_csv("market_risk_sample.csv", parse_dates=["date"])
    loose = run_all_checks(df, dod_threshold=2.0)
    tight = run_all_checks(df, dod_threshold=0.05)
    assert (tight["check"] == "dod_breach").sum() > (loose["check"] == "dod_breach").sum()


def test_missing_columns_rejected():
    with pytest.raises(ValueError):
        graph.build_graph().invoke({"df": pd.DataFrame({"date": ["2025-01-01"], "desk": ["FX"]})})
