from typing import Dict, Any, Optional
from langchain_core.messages import AIMessage
from backend.graph.state import HospitalState
from backend.utils.llm import call_openrouter_api, parse_json_markdown
from backend.prompts.intent import INTENT_AGENT_SYSTEM_PROMPT

def intent_node(state: HospitalState) -> Dict[str, Any]:
    """Node to classify user intent and handle general greetings, with full conversation history context."""
    messages = state.get("messages", [])
    if not messages:
        return {"errors": ["No input message found"]}
        
    language = state.get("language", "English")
    
    last_user_message = ""
    for msg in reversed(messages):
        if msg.type == "human":
            last_user_message = msg.content.strip().lower()
            break
            
    # 1. Strict Greeting Override: Catch pure greetings instantly
    greetings = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening", "greetings", "yo", "hola", "hii", "helo", "namaste"]
    is_pure_greeting = False
    for g in greetings:
        if last_user_message == g or last_user_message.startswith(g + " ") or last_user_message.endswith(" " + g):
            is_pure_greeting = True
            break
            
    if is_pure_greeting:
        greeting_reply = (
            "Good morning!" if "morning" in last_user_message 
            else ("Good afternoon!" if "afternoon" in last_user_message 
                  else ("Good evening!" if "evening" in last_user_message else "Hello!"))
        )
        greeting_reply += " How can I assist you at Sunrise Multispeciality Hospital today?"
        
        return {
            "intent": "GREETING",
            "messages": [AIMessage(content=greeting_reply)],
            "errors": []
        }

    # 2. Clinical Keyword Override: Force BOOK intent for clinical complaints or appointment queries
    booking_keywords = [
        "fever", "fewer", "temp", "cold", "cough", "rash", "itch", "pain", "hurt", "ache",
        "breath", "bleed", "wound", "sick", "ill", "doctor", "appointment", "book", "schedule",
        "consult", "slot", "triage", "physician", "cardiologist", "dermatologist", "pediatrician"
    ]
    is_booking_query = False
    for kw in booking_keywords:
        if kw in last_user_message:
            is_booking_query = True
            break
            
    if is_booking_query:
        return {
            "intent": "BOOK",
            "errors": []
        }

    # 3. Call OpenRouter/Ollama API passing the entire conversation history
    try:
        api_messages = [{"role": "system", "content": INTENT_AGENT_SYSTEM_PROMPT}]
        for msg in messages:
            role = "user" if msg.type == "human" else ("assistant" if msg.type == "ai" else msg.type)
            api_messages.append({"role": role, "content": msg.content})
            
        # Append current user language context to the system query
        api_messages.append({
            "role": "user", 
            "content": f"[System Context - User Language: {language}. Please classify user intent of the thread.]"
        })
            
        response_content = call_openrouter_api(api_messages)
        result_dict = parse_json_markdown(response_content)
        print(f"[DEBUG] Intent processing LLM parsed result: {result_dict}")

        intent_val = str(result_dict.get("intent", "BOOK")).strip().upper()
        if intent_val not in ["BOOK", "CANCEL", "RESCHEDULE", "CHECK_STATUS", "GREETING"]:
            intent_val = "BOOK"

        response_state = {
            "intent": intent_val,
            "errors": []
        }

        greeting_msg = result_dict.get("greeting_message")
        if intent_val == "GREETING" and greeting_msg:
            response_state["messages"] = [AIMessage(content=str(greeting_msg))]

        return response_state
    except Exception as e:
        print(f"[DEBUG] Intent processing failed with error: {e}")
        return {
            "intent": "BOOK",
            "errors": [f"Intent processing warning: {e}"]
        }
