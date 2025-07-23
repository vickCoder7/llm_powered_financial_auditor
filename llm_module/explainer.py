# llm_module/explainer.py

import requests

OLLAMA_API_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "mistral"

def explain_anomaly(metric_name: str, section_text: str, anomaly_reason: str) -> str:
    """
    Generate a human-readable explanation of the detected anomaly using an LLM.
    
    Args:
        metric_name (str): The financial metric or rule being evaluated.
        section_text (str): The section of the 10-K form that triggered the anomaly.
        anomaly_reason (str): The specific rule or logic that caused the anomaly flag.
    
    Returns:
        str: An LLM-generated explanation.
    """
    prompt = f"""
You are a financial auditing assistant. A potential anomaly was detected in a 10-K financial document.
    
Metric: {metric_name}
Rule Violation: {anomaly_reason}

Section Text:
\"\"\"
{section_text}
\"\"\"

Please explain why this anomaly might be important in a professional and clear manner.
"""
    response = requests.post(OLLAMA_API_URL, json={
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False
    })

    if response.status_code == 200:
        return response.json().get("response", "").strip()
    else:
        raise RuntimeError(f"LLM request failed: {response.status_code}, {response.text}")
