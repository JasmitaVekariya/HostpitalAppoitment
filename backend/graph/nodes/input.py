from typing import Dict, Any
from langchain_core.messages import AIMessage
from backend.graph.state import HospitalState
from backend.utils.llm import call_openrouter_api, parse_json_markdown
from backend.prompts.intent import INPUT_AGENT_SYSTEM_PROMPT

MAX_INPUT_CHARS = 2000

def input_node(state: HospitalState) -> Dict[str, Any]:
    """Node to clean the patient's text and detect their language."""
    messages = state.get("messages", [])
    if not messages:
        return {"errors": ["No input message found"]}

    last_message = messages[-1].content
    if not last_message or not last_message.strip():
        return {"errors": ["Received empty message"]}

    # ── Input length guard ────────────────────────────────────────────────────
    if len(last_message) > MAX_INPUT_CHARS:
        notice = (
            "✍️ Your message is a bit long for me to process accurately. "
            "Could you please describe your health concern in a few sentences? "
            f"(Tip: keep it under {MAX_INPUT_CHARS} characters for the best experience.)"
        )
        return {
            "language": "English",
            "messages": [AIMessage(content=notice)],
            "booking_status": "awaiting_symptoms",
            "errors": []
        }

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
