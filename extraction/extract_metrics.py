# extraction/extract_metrics.py

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from anomaly_detection.rules import detect_anomalies


import re
import json

# Define metric extraction patterns
METRIC_PATTERNS = {
    "Revenue": r"(?:Total\s+)?Revenue[\s:\-]*\$?([\d,]+(?:\.\d+)?)",
    "Net Income": r"Net\s+Income[\s:\-]*\$?([\d,]+(?:\.\d+)?)",
    "Operating Expenses": r"Operating\s+Expenses[\s:\-]*\$?([\d,]+(?:\.\d+)?)",
    "Gross Profit": r"Gross\s+Profit[\s:\-]*\$?([\d,]+(?:\.\d+)?)",
    "Total Assets": r"Total\s+Assets[\s:\-]*\$?([\d,]+(?:\.\d+)?)",
    "Total Liabilities": r"Total\s+Liabilities[\s:\-]*\$?([\d,]+(?:\.\d+)?)"
}

def extract_metrics_from_text(text):
    metrics = {}
    for name, pattern in METRIC_PATTERNS.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value_str = match.group(1).replace(",", "")
            try:
                metrics[name] = float(value_str)
            except:
                continue
    return metrics

def load_sections(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)

if __name__ == "__main__":
    sections = load_sections("../outputs/structured_data/apple_sections.json")

    # Combine text from Item 7 and Item 8 (financials are usually here)
    combined_text = ""
    for title, text in sections.items():
        if title.lower().startswith("item 7") or title.lower().startswith("item 8"):
            combined_text += text + "\n"

    metrics = extract_metrics_from_text(combined_text)

    print("📊 Extracted Financial Metrics:")
    for k, v in metrics.items():
        print(f"{k}: ${v:,.2f}")


from anomaly_detection.rules import detect_anomalies

if __name__ == "__main__":
    # ... existing metric extraction ...

    anomalies = detect_anomalies(metrics)

    print("\n🚨 Detected Anomalies:")
    if not anomalies:
        print("No anomalies found.")
    for a in anomalies:
        print(f"- [{a['severity'].upper()}] {a['reason']}")
