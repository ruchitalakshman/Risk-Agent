"""The LLM layer: ask the model for commentary, then VALIDATE what it says.

KEY IDEA: with function calling the model does NOT run any code. It returns
the *arguments* it would pass to a function we declared. We force it to do
that (tool_choice), so the answer comes back as structured data, not free text.

This module has two jobs, deliberately kept separate:
  draft_once()           -> one call to the model (can fail: network, bad output)
  validate_commentary()  -> deterministic checks on the answer (never trusts the model)
The retry loop lives in graph.py, where it is visible as an edge in the graph.
"""
import json
import logging
import os
import re

from dotenv import load_dotenv
from groq import Groq
from jsonschema import ValidationError, validate

from schema import COMMENTARY_SCHEMA

load_dotenv()
log = logging.getLogger("risk_agent.llm")

MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

SYSTEM_PROMPT = (
    "You are a market-risk analyst assistant. You receive an exception log from "
    "automated data-quality checks. Draft concise commentary for a risk manager.\n"
    "Rules:\n"
    "1. Use ONLY facts in the log; never invent numbers, desks or dates.\n"
    "2. Write exactly ONE finding per exception in the log.\n"
    "3. Copy each finding's severity EXACTLY from the log.\n"
    "4. A 'dod_breach' means VaR moved more than {threshold_pct}% day-on-day. It is a data-quality "
    "threshold, NOT a formal risk-limit breach - never call it a 'limit breach'.\n"
    "5. overall_status: 'red' if any exception is high severity, 'amber' if the highest "
    "is medium, 'green' if there are none.\n"
    "Always respond by calling the submit_risk_commentary function."
)

TOOL_NAME = "submit_risk_commentary"
COMMENTARY_TOOL = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "Submit the final structured risk commentary.",
        "parameters": COMMENTARY_SCHEMA,   # same JSON Schema we validate against later
    },
}


def draft_once(exceptions, feedback=None, dod_threshold=0.30):
    """One call to the model. Returns the function-call arguments as a dict."""
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    prompt = (f"The log below has exactly {len(exceptions)} exceptions "
              f"(from 3 types of check: missing_value, outlier, dod_breach). "
              f"Avoid other counts in the summary.\n"
              f"Exception log (JSON):\n{json.dumps(exceptions, indent=2)}")
    if feedback:  # on a retry, tell the model what was wrong with its last answer
        prompt += f"\n\nYour previous answer was rejected: {feedback}\nFix it."
    log.info("Calling model %s", MODEL)
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system",
             "content": SYSTEM_PROMPT.format(threshold_pct=round(dod_threshold * 100))},
            {"role": "user", "content": prompt},
        ],
        tools=[COMMENTARY_TOOL],
        tool_choice={"type": "function", "function": {"name": TOOL_NAME}},
        temperature=0.2,  # low = more consistent, less creative
    )
    calls = response.choices[0].message.tool_calls
    if not calls:
        raise ValueError("model returned no function call")
    # the arguments arrive as a JSON *string*; parse it into a dict
    return json.loads(calls[0].function.arguments)


def _expected_status(exceptions):
    severities = {e["severity"] for e in exceptions}
    return "red" if "high" in severities else "amber" if "medium" in severities else "green"


_NUMBER_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}


def _check_numbers_in_summary(summary, n_exceptions, threshold_pct=30):
    """The free-text summary may only contain numbers we can verify:
    the true exception count, or the day-on-day threshold. Catches 'all twelve checks...' slips."""
    text = summary.lower().replace("‑", "-")
    allowed = {n_exceptions, threshold_pct}
    for token in re.findall(r"\d+|[a-z]+", text):
        value = int(token) if token.isdigit() else _NUMBER_WORDS.get(token)
        if value is not None and value not in allowed:
            raise ValidationError(
                f"overall_summary mentions the number '{token}', which is not verifiable. "
                f"Only {n_exceptions} (exception count) or {threshold_pct} (threshold) may appear; "
                f"better: avoid numbers in the summary.")


def validate_commentary(commentary, exceptions, dod_threshold=0.30):
    """Raise ValidationError if the model's answer breaks any rule. Four layers:
    1. structure   - matches the JSON Schema (right fields, allowed values)
    2. coverage    - exactly one finding per exception, none invented
    3. consistency - severity matches the log; overall status is right
    4. numbers     - the summary contains no unverifiable counts
    """
    validate(instance=commentary, schema=COMMENTARY_SCHEMA)               # 1. structure

    truth = {(e["desk"], e["date"], e["check"]): e["severity"] for e in exceptions}
    seen = {}
    for f in commentary["findings"]:
        key = (f["desk"], f["date"], f["issue_type"])
        if key not in truth:                                              # 2. no invention
            raise ValidationError(f"finding not in exception log: {key}")
        if key in seen:
            raise ValidationError(f"duplicate finding for {key}")
        if f["severity"] != truth[key]:                                   # 3. severity matches
            raise ValidationError(
                f"severity for {key} should be '{truth[key]}', got '{f['severity']}'")
        seen[key] = True
    missing = set(truth) - set(seen)                                      # 2. full coverage
    if missing:
        raise ValidationError(f"missing findings for {sorted(missing)}")
    _check_numbers_in_summary(commentary["overall_summary"], len(exceptions),
                              round(dod_threshold * 100))                     # 4. no invented counts
    expected = _expected_status(exceptions)
    if commentary["overall_status"] != expected:                          # 3. status right
        raise ValidationError(
            f"overall_status should be '{expected}', got '{commentary['overall_status']}'")
