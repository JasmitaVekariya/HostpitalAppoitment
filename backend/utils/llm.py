import time
import requests
import json
import re
from backend.config import settings

def convert_messages_to_dict(messages: list) -> list:
    """Utility to convert LangChain Message objects (HumanMessage, SystemMessage, AIMessage)
    into standard dictionary format for raw API payloads.
    """
    dict_messages = []
    for msg in messages:
        if hasattr(msg, "type"):
            if msg.type == "human":
                role = "user"
            elif msg.type == "system":
                role = "system"
            elif msg.type == "ai":
                role = "assistant"
            else:
                role = msg.type
            dict_messages.append({"role": role, "content": msg.content})
        elif isinstance(msg, dict):
            dict_messages.append(msg)
    return dict_messages

def call_openrouter_api_raw(messages: list, temperature: float = 0.1) -> str:
    """Invokes the OpenRouter completions API directly via HTTP POST with exponential backoff on 429."""
    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://sunrisehospital.com",
        "X-Title": "AI Hospital Appointment Orchestrator",
        "Content-Type": "application/json",
    }
    
    # Format messages array to standard API format
    api_messages = convert_messages_to_dict(messages)
    
    payload = {
        "model": settings.OPENROUTER_MODEL,
        "messages": api_messages,
        "temperature": temperature,
    }
    
    max_retries = 12
    backoff = 2
    
    for attempt in range(max_retries):
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            # Handle rate-limiting gracefully
            if response.status_code == 429:
                print(f"[DEBUG] Direct API rate limit hit (429). Retrying in {backoff}s...")
                time.sleep(backoff)
                backoff = min(backoff * 2, 10)
                continue
                
            response.raise_for_status()
            data = response.json()
            
            # Pacing cooldown to avoid back-to-back 429 triggers in multi-agent runs
            time.sleep(1.5)
            
            return data["choices"][0]["message"]["content"]
            
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            print(f"[DEBUG] Direct API connection error: {e}. Retrying in {backoff}s...")
            time.sleep(backoff)
            backoff = min(backoff * 2, 10)
            
    raise Exception("Failed to call OpenRouter API after maximum retry attempts.")

def call_ollama_api(messages: list, temperature: float = 0.1) -> str:
    """Invokes a local Ollama instance chat API directly via HTTP POST."""
    headers = {
        "Content-Type": "application/json",
    }
    
    api_messages = convert_messages_to_dict(messages)
    
    payload = {
        "model": settings.OLLAMA_MODEL,
        "messages": api_messages,
        "stream": False,
        "options": {
            "temperature": temperature,
        }
    }
    
    try:
        url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/chat"
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        return data["message"]["content"]
    except Exception as e:
        print(f"[DEBUG] Local Ollama API call failed: {e}")
        raise e

def call_openrouter_api(messages: list, temperature: float = 0.1) -> str:
    """Dynamic wrapper that routes LLM calls to either OpenRouter or local Ollama depending on settings."""
    provider = getattr(settings, "LLM_PROVIDER", "openrouter").lower()
    if provider == "ollama":
        return call_ollama_api(messages, temperature)
    else:
        return call_openrouter_api_raw(messages, temperature)

def parse_json_markdown(text: str) -> dict:
    """Robust utility to extract and parse JSON from LLM text responses, 
    supporting markdown backticks (e.g. ```json ... ```) or raw strings.
    """
    text = text.strip()
    
    # 1. Try finding JSON inside markdown backticks
    pattern = r"```(?:json)?\s*(\{.*?\})\s*```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        # 2. Try finding the first '{' and last '}'
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            json_str = text[start:end+1]
        else:
            json_str = text
            
    json_str = json_str.strip()
    
    # 3. Attempt standard parsing
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        # Fallback: attempt key-value line parsing
        extracted = {}
        for line in text.split("\n"):
            line = line.strip("-* ").strip()
            if ":" in line:
                key, val = line.split(":", 1)
                key_clean = key.strip().lower()
                val_clean = val.strip().strip('"\'')
                if "name" in key_clean:
                    extracted["name"] = val_clean
                elif "age" in key_clean:
                    age_digits = re.findall(r"\d+", val_clean)
                    if age_digits:
                        extracted["age"] = int(age_digits[0])
                elif "gender" in key_clean:
                    extracted["gender"] = val_clean
                elif "phone" in key_clean:
                    extracted["phone"] = val_clean
        if extracted:
            return extracted
        raise e
