# anomaly_detection/rules.py

from typing import Dict, List

def detect_anomalies(metrics: Dict[str, float]) -> List[Dict]:
    anomalies = []

    # Rule 1: Negative Net Income
    if "Net Income" in metrics and metrics["Net Income"] < 0:
        anomalies.append({
            "metric": "Net Income",
            "value": metrics["Net Income"],
            "type": "Negative",
            "reason": "Net income is negative, indicating a net loss.",
            "severity": "high"
        })

    # Rule 2: Operating Expenses > Revenue
    if "Operating Expenses" in metrics and "Revenue" in metrics:
        if metrics["Operating Expenses"] > metrics["Revenue"]:
            anomalies.append({
                "metric": "Operating Expenses vs Revenue",
                "value": {
                    "Operating Expenses": metrics["Operating Expenses"],
                    "Revenue": metrics["Revenue"]
                },
                "type": "Overspend",
                "reason": "Operating expenses exceed total revenue.",
                "severity": "critical"
            })

    # Rule 3: Gross Profit Margin < 20%
    if "Gross Profit" in metrics and "Revenue" in metrics:
        margin = metrics["Gross Profit"] / metrics["Revenue"]
        if margin < 0.2:
            anomalies.append({
                "metric": "Gross Profit Margin",
                "value": margin,
                "type": "Low Margin",
                "reason": f"Gross profit margin is low ({margin:.2%}), below 20%.",
                "severity": "medium"
            })

    # Rule 4: High Liabilities vs Assets (> 80%)
    if "Total Liabilities" in metrics and "Total Assets" in metrics:
        ratio = metrics["Total Liabilities"] / metrics["Total Assets"]
        if ratio > 0.8:
            anomalies.append({
                "metric": "Liabilities-to-Assets Ratio",
                "value": ratio,
                "type": "High Leverage",
                "reason": f"Liabilities-to-assets ratio is high ({ratio:.2%}).",
                "severity": "medium"
            })

    return anomalies

if __name__ == "__main__":
    metrics = {
        "Net Income": -500,
        "Revenue": 1000,
        "Operating Expenses": 1200
    }

    result = detect_anomalies(metrics)
    print(result)