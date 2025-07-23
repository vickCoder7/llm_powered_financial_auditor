import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from llm_module.explainer import explain_anomaly

explanation = explain_anomaly(
    metric_name="Revenue Growth",
    section_text="Revenue increased by 250% year-over-year due to unexpected licensing agreements...",
    anomaly_reason="Growth > 200% triggers anomaly"
)

print("LLM Explanation:", explanation)
