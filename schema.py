"""The contract for the LLM's output, written once as a JSON Schema.

It is used twice:
  1. Sent to Gemini as the function's parameters -> tells the model the shape to produce.
  2. Used by `jsonschema` to VALIDATE what comes back -> we never trust the model blindly.
"""

COMMENTARY_SCHEMA = {
    "type": "object",
    "properties": {
        "overall_summary": {
            "type": "string",
            "description": "2-3 sentence summary of the data-quality and risk picture.",
        },
        "overall_status": {
            "type": "string",
            "enum": ["green", "amber", "red"],
            "description": "green = clean, amber = issues to review, red = critical issues.",
        },
        "findings": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "desk": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "issue_type": {
                        "type": "string",
                        "enum": ["missing_value", "outlier", "dod_breach"],
                    },
                    "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                    "commentary": {
                        "type": "string",
                        "description": "One or two sentences for a risk manager. Use only facts from the input.",
                    },
                    "recommended_action": {"type": "string"},
                },
                "required": ["desk", "date", "issue_type", "severity", "commentary", "recommended_action"],
            },
        },
    },
    "required": ["overall_summary", "overall_status", "findings"],
}
