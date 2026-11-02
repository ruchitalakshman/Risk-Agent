"""Entry point: python main.py   (run generate_data.py once first)"""
import json
import logging

from graph import build_graph

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.FileHandler("pipeline.log"), logging.StreamHandler()],
)
logging.getLogger("httpx").setLevel(logging.WARNING)   # hide noisy HTTP lines


def write_markdown(report):
    """Human-readable version of risk_report.json."""
    c = report["commentary"]
    lines = [
        "# Market Risk Data-Quality Report", "",
        f"- Generated: {report['generated_at']}  |  Model: `{report['model']}`",
        f"- Rows checked: {report['rows_checked']}  |  Exceptions: {report['exceptions_found']}"
        f"  |  LLM attempts: {report['llm_attempts']}",
        f"- **Overall status: {c['overall_status'].upper()}**", "",
        f"**Summary:** {c['overall_summary']}", "",
        "| Date | Desk | Issue | Severity | Commentary | Action |",
        "|---|---|---|---|---|---|",
    ]
    for f in sorted(c["findings"], key=lambda f: (f["date"], f["desk"])):
        lines.append(f"| {f['date']} | {f['desk']} | {f['issue_type']} | {f['severity']} "
                     f"| {f['commentary']} | {f['recommended_action']} |")
    text = "\n".join(lines).replace("‑", "-").replace(" ", " ")  # model's special hyphens/spaces
    open("risk_report.md", "w", encoding="utf-8").write(text + "\n")


def main():
    app = build_graph()
    open("graph.mmd", "w").write(app.get_graph().draw_mermaid())   # diagram of the graph
    app.invoke({"data_path": "market_risk_sample.csv"})
    report = json.load(open("risk_report.json"))
    if report["commentary"]:
        write_markdown(report)
        print("\nDone. See risk_report.md, risk_report.json, exception_log.csv, pipeline.log")
    else:
        print("\nLLM step failed:", report["llm_status"])


if __name__ == "__main__":
    main()
