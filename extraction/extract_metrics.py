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

# ── Prompt (cloud only) ────────────────────────────────────────────────────────
EXTRACTION_PROMPT = """You are a financial data extraction assistant analyzing an SEC 10-K annual report.

Extract the following financial metrics for the MOST RECENT fiscal year from the text below.
Return ONLY a valid JSON object — no markdown, no code fences, no explanation, no extra text.

Rules:
- All values must be expressed in MILLIONS (e.g. $383,285M -> 383285).
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

# ── Regex Patterns (local fallback) ───────────────────────────────────────────
# Broader label synonyms to handle Apple-style "Net sales", "Total net sales" etc.
METRIC_PATTERNS = {
    "Revenue":            r"(?:Total\s+)?(?:Net\s+)?(?:Revenue|Sales|Net\s+sales)[^\d\(\-]{0,20}([\(\-]?[\d,]+(?:\.\d+)?[\)]?)",
    "Net Income":         r"Net\s+(?:income|earnings|loss)[^\d\(\-]{0,20}([\(\-]?[\d,]+(?:\.\d+)?[\)]?)",
    "Operating Expenses": r"(?:Total\s+)?Operating\s+(?:expenses|costs)[^\d\(\-]{0,20}([\(\-]?[\d,]+(?:\.\d+)?[\)]?)",
    "Gross Profit":       r"Gross\s+(?:profit|margin)[^\d\(\-]{0,20}([\(\-]?[\d,]+(?:\.\d+)?[\)]?)",
    "Total Assets":       r"Total\s+assets[^\d\(\-]{0,20}([\(\-]?[\d,]+(?:\.\d+)?[\)]?)",
    "Total Liabilities":  r"Total\s+(?:liabilities|liabilities\s+and)[^\d\(\-]{0,20}([\(\-]?[\d,]+(?:\.\d+)?[\)]?)",
}


def _parse_value(raw_str: str) -> float:
    """Convert a raw matched string like '(1,234)' or '383,285' to a float."""
    s = raw_str.strip()
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    value = float(s.replace(",", ""))
    return -value if negative else value


def _detect_scale(text: str) -> float:
    """
    Detect the reporting scale from the document preamble.
    Returns the multiplier to convert reported numbers to millions.
    e.g. 'in thousands' → 0.001, 'in millions' → 1.0, 'in billions' → 1000.0
    """
    snippet = text[:5000].lower()
    if re.search(r"in\s+thousands", snippet):
        return 0.001
    if re.search(r"in\s+billions", snippet):
        return 1000.0
    # Default assumption for large-cap 10-Ks: values already in millions
    return 1.0


def _regex_extract(text: str) -> dict:
    """
    Regex-based metric extraction with scale detection.
    Used as the local-mode fallback when Mistral is too slow.
    """
    scale = _detect_scale(text)
    metrics = {}
    for name, pattern in METRIC_PATTERNS.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                value = _parse_value(match.group(1)) * scale
                metrics[name] = value
            except (ValueError, IndexError):
                continue
    return metrics


# ── Cloud (LLM) helpers ────────────────────────────────────────────────────────
_FINANCE_SIGNAL = re.compile(
    r"(\$[\d,]+|\d[\d,]+\.\d|\b(?:million|billion|thousand|revenue|income|"
    r"assets|liabilities|profit|expenses|earnings|net sales|total)\b)",
    re.IGNORECASE,
)


def _find_densest_chunk(text: str, chunk_size: int, top_n: int = 3) -> str:
    """Return the top_n highest-density financial windows concatenated."""
    step = chunk_size // 2
    windows = []
    for start in range(0, max(1, len(text) - chunk_size + 1), step):
        window = text[start: start + chunk_size]
        score = len(_FINANCE_SIGNAL.findall(window))
        windows.append((score, start, window))

    windows.sort(key=lambda x: x[0], reverse=True)
    selected: list[tuple[int, str]] = []
    used: list[tuple[int, int]] = []
    for score, start, window in windows:
        end = start + chunk_size
        if any(start < u_end and end > u_start for u_start, u_end in used):
            continue
        selected.append((start, window))
        used.append((start, end))
        if len(selected) >= top_n:
            break

    selected.sort(key=lambda x: x[0])
    return "\n...\n".join(w for _, w in selected)


def _parse_json_response(raw: str) -> dict:
    """Strip markdown code fences and parse JSON from LLM response."""
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()
    parsed = json.loads(cleaned)
    return {k: float(v) for k, v in parsed.items() if v is not None}


def _llm_extract(text: str) -> dict:
    """LLM-based extraction via Groq. For cloud mode only."""
    context = _find_densest_chunk(text, chunk_size=6000, top_n=3)
    prompt = EXTRACTION_PROMPT.format(text=context)

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
        "temperature": 0,
    }
    response = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    raw = response.json()["choices"][0]["message"]["content"]
    return _parse_json_response(raw)


# ── Public API ─────────────────────────────────────────────────────────────────
def extract_metrics_from_text(text: str) -> dict:
    """
    Extract key financial metrics from the provided 10-K text.

    Strategy:
      - Cloud mode (Groq/Llama 3.3): LLM structured extraction — handles semantic
        label variations, scale normalization, and table ambiguity automatically.
      - Local mode (Ollama/Mistral): Smart regex with scale detection — fast and
        reliable; Mistral 7B is too slow for structured JSON extraction from large
        financial tables within a practical timeout.

    Returns a dict of {metric_name: float_in_millions}.
    """
    try:
        if MODE == "cloud":
            return _llm_extract(text)
        else:
            return _regex_extract(text)
    except (requests.RequestException, json.JSONDecodeError, KeyError, ValueError) as e:
        raise RuntimeError(f"Metric extraction failed: {e}") from e


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

    print(f"Mode: {MODE}  |  Combined text: {len(combined):,} chars")
    metrics = extract_metrics_from_text(combined)
    print("\nExtracted Financial Metrics:")
    if metrics:
        for k, v in metrics.items():
            print(f"  {k}: ${v:,.2f}M")
    else:
        print("  (no metrics extracted)")
