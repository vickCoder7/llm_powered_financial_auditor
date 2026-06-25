# extraction/extract_metrics.py

import sys
import os
import re
import json

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from llm_module.client import execute_llm_request
from llm_module.retriever import chunk_text, BM25Retriever

# Prompt (shared with Ollama/Groq)
EXTRACTION_PROMPT = """You are a financial data extraction assistant analyzing a financial report or filing.

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


def _parse_json_response(raw: str) -> dict:
    """Strip markdown code fences and parse JSON from LLM response."""
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()
    parsed = json.loads(cleaned)
    return {k: float(v) for k, v in parsed.items() if v is not None}


def _llm_extract(text: str) -> dict:
    """LLM-based extraction using RAG context retrieval."""
    # Chunk the text into smaller searchable segments
    chunks = chunk_text(text, chunk_size=3000, overlap=500)
    
    # Fit the BM25 index on these chunks
    retriever = BM25Retriever()
    retriever.fit(chunks)
    
    # Query for statement of operations (income statement) and balance sheet sections
    results_ops = retriever.search("Consolidated Statements of Operations Income Revenue Sales Cost of Sales", top_n=2)
    results_bs = retriever.search("Consolidated Balance Sheets Assets Liabilities Equity", top_n=2)
    
    # Merge retrieved chunks based on their original order index
    retrieved_chunks = []
    seen_indices = set()
    for r in results_ops + results_bs:
        if r["index"] not in seen_indices:
            seen_indices.add(r["index"])
            retrieved_chunks.append(r)
            
    # Sort chunks to preserve the original sequence of the tables
    retrieved_chunks.sort(key=lambda x: x["index"])
    
    context = "\n...\n".join(c["text"] for c in retrieved_chunks)
    prompt = EXTRACTION_PROMPT.format(text=context)
    
    system_prompt = "You are a financial data extraction assistant. Return only valid JSON with no extra text."
    raw = execute_llm_request(prompt=prompt, system_prompt=system_prompt)
    
    return _parse_json_response(raw)


def extract_metrics_from_text(text: str) -> dict:
    """
    Extract key financial metrics from the provided 10-K text.
    Uses BM25 Retrieval to isolate the balance sheet and income statement chunks,
    then feeds them to the LLM (Groq or Ollama) for structured JSON extraction.

    Returns a dict of {metric_name: float_in_millions}.
    """
    try:
        return _llm_extract(text)
    except Exception as e:
        raise RuntimeError(f"Metric extraction failed: {e}") from e


# Standalone test
if __name__ == "__main__":
    from extraction.parse_html import extract_sections_from_html

    sample_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "raw_documents", "apple_10k_2023.html"
    )
    if not os.path.exists(sample_path):
        print(f"Sample document not found at {sample_path}")
        sys.exit(1)
        
    with open(sample_path, "r", encoding="utf-8") as f:
        html = f.read()

    sections = extract_sections_from_html(html)
    combined = ""
    for title, text in sections.items():
        if title.lower().startswith("item 7") or title.lower().startswith("item 8"):
            combined += text + "\n"

    print(f"Combined text: {len(combined):,} chars")
    print("Running LLM extraction (RAG-based)...")
    try:
        metrics = extract_metrics_from_text(combined)
        print("\nExtracted Financial Metrics:")
        if metrics:
            for k, v in metrics.items():
                print(f"  {k}: ${v:,.2f}M")
        else:
            print("  (no metrics extracted)")
    except Exception as e:
        print("Extraction failed:", e)
