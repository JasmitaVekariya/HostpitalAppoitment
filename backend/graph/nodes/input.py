from typing import Dict, Any
from backend.graph.state import HospitalState
from backend.utils.llm import call_openrouter_api, parse_json_markdown
from backend.prompts.intent import INPUT_AGENT_SYSTEM_PROMPT

def input_node(state: HospitalState) -> Dict[str, Any]:
    """Node to clean the patient's text and detect their language."""
    messages = state.get("messages", [])
    if not messages:
        return {"errors": ["No input message found"]}
        
    last_message = messages[-1].content
    if not last_message or not last_message.strip():
        return {"errors": ["Received empty message"]}

    # Call OpenRouter API directly
    try:
        response_content = call_openrouter_api([
            {"role": "system", "content": INPUT_AGENT_SYSTEM_PROMPT},
            {"role": "user", "content": last_message}
        ])
        result_dict = parse_json_markdown(response_content)
        print(f"[DEBUG] Input processing LLM parsed result: {result_dict}")
        
        detected_lang = str(result_dict.get("language", "English")).strip().capitalize()
        if detected_lang not in ["English", "Hindi", "Gujarati"]:
            detected_lang = "English"

        return {
            "language": detected_lang,
            "errors": []
        }
    except Exception as e:
        print(f"[DEBUG] Input processing failed with error: {e}")
        return {
            "language": "English",
            "errors": [f"Input processing warning: {e}"]
        }
