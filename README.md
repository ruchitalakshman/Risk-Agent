# Risk Data Validation & AI Reporting Agent

A pipeline that runs automated data-quality checks on (synthetic) market-risk data, then uses an LLM
to draft risk commentary as schema-validated JSON, with logging and retries for an auditable result.

```
CSV -> load_data -> run_checks -> draft (LLM, function calling) -> validate -> save_report
                        |                   ^                        |
                        | (no issues)       +------ retry edge ------+ (invalid, attempts < 3)
                        +-> no_issues -> save_report
```

## What it does
- **Data-quality checks (pandas/NumPy):** missing values, per-desk z-score outliers, day-on-day VaR threshold breaches -> exception log.
- **LLM commentary (Groq, `openai/gpt-oss-120b`):** function calling forces output into a JSON Schema.
- **Validation (never trusts the model):** schema, one finding per exception, severity/status consistency with the log, and no unverifiable numbers in the summary.
- **Orchestration (LangGraph):** conditional retry loop; gives up after 3 attempts and records the failure.
- **Audit trail:** `pipeline.log`, `exception_log.csv`, `risk_report.json`.
- **Streamlit UI:** adjustable thresholds, CSV upload, charts, filterable tables.

## Setup
```
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```
Create a `.env` file (never commit it) with a free key from console.groq.com:
```
GROQ_API_KEY=your_key_here
```

## Run
```
python generate_data.py          # creates market_risk_sample.csv (with planted errors)
python main.py                   # command-line pipeline -> risk_report.md / .json
streamlit run app.py             # web UI
python -m pytest -q              # offline tests (no API calls)
```

## Files
| File | Role |
|---|---|
| `generate_data.py` | Synthetic data with 7 planted problems |
| `checks.py` | The three data-quality checks |
| `schema.py` | JSON Schema for the LLM output |
| `llm.py` | Model call (function calling) + validation rules |
| `graph.py` | LangGraph workflow and retry logic |
| `main.py` / `app.py` | CLI and Streamlit front ends |
| `test_pipeline.py` | Tests, incl. simulated bad model output |

## Limitations
- Data is synthetic; thresholds (30% day-on-day, z > 4) are illustrative, not production limits.
- Validation checks structure and facts, not tone; a human should still review commentary.
