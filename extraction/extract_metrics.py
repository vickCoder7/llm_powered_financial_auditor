# extraction/extract_metrics.py

import os
import re
import json
import requests

# ── LLM Configuration (shared with explainer.py) ──────────────────────────────
MODE = os.getenv("LLM_MODE", "local")
OLLAMA_API_URL = "http://localhost:11434/api/generate"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL_NAME = os.getenv("MODEL_NAME", "mistral") if MODE == "local" else "llama-3.3-70b-versatile"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ── Prompt ─────────────────────────────────────────────────────────────────────
EXTRACTION_PROMPT = """You are a financial data extraction assistant analyzing an SEC 10-K annual report.

Extract the following financial metrics for the MOST RECENT fiscal year from the text below.
Return ONLY a valid JSON object — no markdown, no code fences, no explanation, no extra text.

Rules:
- All values must be expressed in MILLIONS (e.g. $383,285M → 383285).
- If a value is in thousands, divide by 1000. If in billions, multiply by 1000.
- Negative values written as (1,234) must be returned as -1234.
- If a metric is not found, use null.

Required JSON schema (exact keys):
{{
  "Revenue": <float or null>,
  "Net Income": <float or null>,
  "Operating Expenses": <float or null>,
  "Gross Profit": <float or null>,
  "Total Assets": <float or null>,
  "Total Liabilities": <float or null>
}}

Financial Statement Text:
\"\"\"
{text}
\"\"\"
"""


def _parse_json_response(raw: str) -> dict:
    """Strip markdown code fences and parse JSON from LLM response."""
    # Remove ```json ... ``` wrappers if present
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()
    parsed = json.loads(cleaned)
    # Drop null entries and ensure float values
    return {k: float(v) for k, v in parsed.items() if v is not None}


def extract_metrics_from_text(text: str) -> dict:
    """
    Extract key financial metrics from the provided text using an LLM.
    Routes to Ollama (local) or Groq (cloud) based on LLM_MODE env var.
    Falls back to empty dict if the LLM fails or returns unparseable output.
    """
    # Limit context size: cloud handles large context well; local must stay tight
    # to avoid Mistral timing out on dense financial tables
    limit = 20000 if MODE == "cloud" else 3000
    prompt = EXTRACTION_PROMPT.format(text=text[:limit])

    try:
        if MODE == "local":
            response = requests.post(
                OLLAMA_API_URL,
                json={"model": MODEL_NAME, "prompt": prompt, "stream": False},
                timeout=180,
            )
            response.raise_for_status()
            raw = response.json().get("response", "")

        else:  # Cloud (Groq)
            headers = {
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": MODEL_NAME,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a financial data extraction assistant. Return only valid JSON with no extra text.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,  # Deterministic output for structured extraction
            }
            response = requests.post(
                GROQ_API_URL, headers=headers, json=payload, timeout=60
            )
            response.raise_for_status()
            raw = response.json()["choices"][0]["message"]["content"]

        return _parse_json_response(raw)

    except (requests.RequestException, json.JSONDecodeError, KeyError, ValueError) as e:
        # Surface a clear warning rather than crashing the Streamlit app
        raise RuntimeError(f"LLM metric extraction failed: {e}") from e


# ── Standalone test ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from extraction.parse_html import extract_sections_from_html

    sample_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "raw_documents", "apple_10k_2023.html"
    )
    with open(sample_path, "r", encoding="utf-8") as f:
        html = f.read()

    sections = extract_sections_from_html(html)
    combined = ""
    for title, text in sections.items():
        if title.lower().startswith("item 7") or title.lower().startswith("item 8"):
            combined += text + "\n"

    metrics = extract_metrics_from_text(combined)
    print("\n📊 LLM-Extracted Financial Metrics:")
    for k, v in metrics.items():
        print(f"  {k}: ${v:,.2f}M")
