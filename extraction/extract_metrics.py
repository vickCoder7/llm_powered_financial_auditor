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

# Financial density signal patterns
_FINANCE_PATTERN = re.compile(
    r"(\$[\d,]+|\d[\d,]+\.\d|\b(?:million|billion|thousand|revenue|income|"
    r"assets|liabilities|profit|expenses|earnings|net sales|total)\b)",
    re.IGNORECASE,
)


def _find_densest_chunk(text: str, chunk_size: int, top_n: int = 3) -> str:
    """
    Score overlapping windows of `chunk_size` chars by financial signal density.
    Returns the concatenation of the top_n highest-scoring non-overlapping windows.

    This ensures we feed the LLM the most number-rich portion of the document
    rather than blindly taking the first N characters (which is often just prose).
    """
    step = chunk_size // 2  # 50 % overlap so we don't split tables mid-row
    windows = []
    for start in range(0, max(1, len(text) - chunk_size + 1), step):
        window = text[start: start + chunk_size]
        score = len(_FINANCE_PATTERN.findall(window))
        windows.append((score, start, window))

    # Sort by score descending; pick top_n non-overlapping windows
    windows.sort(key=lambda x: x[0], reverse=True)
    selected = []
    used_ranges: list[tuple[int, int]] = []
    for score, start, window in windows:
        end = start + chunk_size
        # Skip if this window overlaps with an already-selected one
        if any(start < u_end and end > u_start for u_start, u_end in used_ranges):
            continue
        selected.append((start, window))
        used_ranges.append((start, end))
        if len(selected) >= top_n:
            break

    # Re-sort selected windows by document position so text reads naturally
    selected.sort(key=lambda x: x[0])
    return "\n...\n".join(w for _, w in selected)


def _parse_json_response(raw: str) -> dict:
    """Strip markdown code fences and parse JSON from LLM response."""
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()
    parsed = json.loads(cleaned)
    # Drop null entries and ensure float values
    return {k: float(v) for k, v in parsed.items() if v is not None}


def extract_metrics_from_text(text: str) -> dict:
    """
    Extract key financial metrics from the provided text using an LLM.
    Uses density-based chunking to feed the most number-rich section to the model.
    Routes to Ollama (local) or Groq (cloud) based on LLM_MODE env var.
    """
    if MODE == "local":
        # For local Mistral, select the single densest 3000-char window
        context = _find_densest_chunk(text, chunk_size=3000, top_n=1)
    else:
        # For cloud (Groq/Llama), grab the top-3 densest windows up to ~18k chars
        context = _find_densest_chunk(text, chunk_size=6000, top_n=3)

    prompt = EXTRACTION_PROMPT.format(text=context)

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
                "temperature": 0,
            }
            response = requests.post(
                GROQ_API_URL, headers=headers, json=payload, timeout=60
            )
            response.raise_for_status()
            raw = response.json()["choices"][0]["message"]["content"]

        return _parse_json_response(raw)

    except (requests.RequestException, json.JSONDecodeError, KeyError, ValueError) as e:
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

    print(f"Combined text length: {len(combined):,} chars")
    metrics = extract_metrics_from_text(combined)
    print("\nLLM-Extracted Financial Metrics:")
    if metrics:
        for k, v in metrics.items():
            print(f"  {k}: ${v:,.2f}M")
    else:
        print("  (no metrics extracted)")
