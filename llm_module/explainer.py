# llm_module/explainer.py

from llm_module.client import execute_llm_request

def explain_anomaly(metric_name: str, section_text: str, anomaly_reason: str) -> str:
    """
    Generate a human-readable explanation of the detected anomaly using an LLM.
    Supports local (Ollama) and cloud (Groq) providers based on environment variables.
    """
    prompt = f"""
You are a financial auditing assistant. A potential anomaly was detected in a financial document.
    
Metric: {metric_name}
Rule Violation: {anomaly_reason}

Section Text:
\"\"\"
{section_text}
\"\"\"

Please explain why this anomaly might be important in a professional and clear manner.
"""
    return execute_llm_request(prompt=prompt)


def answer_document_question(query: str, context: str, history: list) -> str:
    """
    Answer a user question based on the provided 10-K document context.
    Includes chat history for conversational context.
    """
    # Build prompt with system instructions, context, and conversation history
    history_str = ""
    for msg in history[-5:]:  # Keep last 5 messages for context
        role = "User" if msg["role"] == "user" else "Assistant"
        history_str += f"{role}: {msg['content']}\n"

    prompt = f"""You are a professional financial auditor assistant. You are answering questions about a company's financial report.
Use ONLY the provided Section Text below to answer the user's question. 
If the answer cannot be found or reasonably inferred from the provided text, politely explain that the information is not available in the document. Do not invent facts.

Section Text (document context):
\"\"\"
{context}
\"\"\"

Conversation History:
{history_str}
User: {query}
Assistant:"""

    system_prompt = "You are a professional financial auditor assistant. Answer questions based only on the provided context."
    return execute_llm_request(prompt=prompt, system_prompt=system_prompt, chat_history=history[-5:])

