# llm_module/explainer.py

import os
import requests
import json

# Configuration
MODE = os.getenv("LLM_MODE", "local")  # "local" for Ollama, "cloud" for Groq
OLLAMA_API_URL = "http://localhost:11434/api/generate"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL_NAME = os.getenv("MODEL_NAME", "mistral") if MODE == "local" else "llama3-70b-8192"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

def explain_anomaly(metric_name: str, section_text: str, anomaly_reason: str) -> str:
    """
    Generate a human-readable explanation of the detected anomaly using an LLM.
    Supports local (Ollama) and cloud (Groq) providers based on environment variables.
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
    
    if MODE == "local":
        response = requests.post(OLLAMA_API_URL, json={
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False
        })
        if response.status_code == 200:
            return response.json().get("response", "").strip()
        else:
            raise RuntimeError(f"Ollama request failed: {response.status_code}, {response.text}")
            
    else:  # Cloud (Groq)
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": MODEL_NAME,
            "messages": [{"role": "user", "content": prompt}]
        }
        response = requests.post(GROQ_API_URL, headers=headers, json=payload)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"].strip()
        else:
            raise RuntimeError(f"Groq request failed: {response.status_code}, {response.text}")
