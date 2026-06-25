import os
import re
import time
import requests

try:
    # pyrefly: ignore [missing-import]
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# LLM Configuration
MODE = os.getenv("LLM_MODE", "local")  # "local" for Ollama, "cloud" for Groq
OLLAMA_API_URL = "http://localhost:11434/api/generate"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Default cloud model is groq/compound-mini due to its high 70,000 TPM limit.
# Fallback / local is mistral.
MODEL_NAME = os.getenv(
    "MODEL_NAME", 
    "mistral" if MODE == "local" else "groq/compound-mini"
)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")


def parse_duration_string(s: str) -> float:
    """Parse duration strings like '1m26.4s', '205ms', '1.5s' into seconds."""
    total_seconds = 0.0
    s = s.strip()
    
    # Parse ms first
    ms_match = re.search(r"(\d+(?:\.\d+)?)ms", s)
    if ms_match:
        total_seconds += float(ms_match.group(1)) / 1000.0
        s = s.replace(ms_match.group(0), "")
        
    # Parse m (minutes)
    m_match = re.search(r"(\d+(?:\.\d+)?)m", s)
    if m_match:
        total_seconds += float(m_match.group(1)) * 60
        s = s.replace(m_match.group(0), "")
        
    # Parse s (seconds)
    s_match = re.search(r"(\d+(?:\.\d+)?)s", s)
    if s_match:
        total_seconds += float(s_match.group(1))
        
    return total_seconds


def execute_llm_request(prompt: str, system_prompt: str = None, chat_history: list = None, max_retries: int = 5) -> str:
    """
    Execute an LLM request. Supports local (Ollama) and cloud (Groq) modes.
    Handles Groq rate limits (429) automatically with parse-and-wait retries.
    """
    if MODE == "local":
        # Ollama local mode
        payload = {
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False
        }
        if system_prompt:
            payload["system"] = system_prompt
            
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=90)
        if response.status_code == 200:
            return response.json().get("response", "").strip()
        else:
            raise RuntimeError(f"Ollama request failed: {response.status_code}, {response.text}")
            
    else:
        # Groq cloud mode
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Build messages payload
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
            
        if chat_history:
            # Format chat history standard openai style
            for msg in chat_history:
                messages.append({"role": msg["role"], "content": msg["content"]})
            
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": MODEL_NAME,
            "messages": messages,
            "temperature": 0
        }
        
        for attempt in range(max_retries):
            try:
                response = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=60)
                if response.status_code == 200:
                    return response.json()["choices"][0]["message"]["content"].strip()
                
                elif response.status_code == 429:
                    # Parse wait time
                    wait_time = 0.0
                    
                    # 1. Check Retry-After header
                    retry_after = response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            wait_time = float(retry_after)
                        except ValueError:
                            pass
                            
                    # 2. Check JSON error message
                    if wait_time <= 0:
                        try:
                            err_json = response.json()
                            err_msg = err_json.get("error", {}).get("message", "")
                            match = re.search(r"try again in ([0-9\.]+)s", err_msg)
                            if match:
                                wait_time = float(match.group(1))
                        except Exception:
                            pass
                            
                    # 3. Check rate limit reset headers
                    if wait_time <= 0:
                        reset_tokens = response.headers.get("x-ratelimit-reset-tokens")
                        if reset_tokens:
                            wait_time = parse_duration_string(reset_tokens)
                            
                    # Fallback
                    if wait_time <= 0:
                        wait_time = 5.0
                        
                    # Add a safety buffer (1 second)
                    wait_time += 1.0
                    
                    print(f"Groq Rate Limit (429) hit for model '{MODEL_NAME}'. Waiting {wait_time:.2f}s before retry (attempt {attempt + 1}/{max_retries})...")
                    
                    # Notify UI if in Streamlit context
                    try:
                        # pyrefly: ignore [missing-import]
                        import streamlit as st
                        st.toast(f"⏳ Rate limit reached for {MODEL_NAME}. Retrying in {wait_time:.1f}s...", icon="⏳")
                    except Exception:
                        pass
                        
                    time.sleep(wait_time)
                    continue
                else:
                    raise RuntimeError(f"Groq request failed: {response.status_code}, {response.text}")
                    
            except requests.RequestException as e:
                if attempt == max_retries - 1:
                    raise RuntimeError(f"Groq request failed due to connection error: {e}")
                time.sleep(2.0)
                
        # If we exit the loop without returning, it means we exhausted retries and still got 429
        raise RuntimeError(f"Groq request failed: Rate limit exceeded after {max_retries} attempts.")
