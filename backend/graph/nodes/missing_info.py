from typing import Dict, Any, List
from langchain_core.messages import AIMessage
from backend.graph.state import HospitalState
from backend.utils.llm import call_openrouter_api

def missing_info_node(state: HospitalState) -> Dict[str, Any]:
    """Node to check for missing profile details (name, age) and request them."""
    patient_info = state.get("patient_info", {})
    errors = list(state.get("errors", []))
    
    missing_fields = []
    if not patient_info.get("name"):
        missing_fields.append("your full name")
    if patient_info.get("age") is None:
        missing_fields.append("your age")
        
    # If no mandatory fields are missing, set status to complete
    if not missing_fields:
        current_status = state.get("booking_status")
        if current_status in ["awaiting_slot_selection", "emergency_redirect"]:
            return {} # Preserve the existing scheduling status
        return {
            "booking_status": "info_complete"
        }
        
    # Build list of missing fields to request from the user
    fields_str = " and ".join(missing_fields)
    
    prompt = (
        f"The patient is trying to book an appointment but has not provided the following required details: {fields_str}. "
        f"Ask the patient to provide these details in a friendly, single-sentence response. "
        f"Keep the language simple and polite."
    )
    
    try:
        response_content = call_openrouter_api([
            {"role": "system", "content": "You are a helpful medical receptionist at Sunrise Multispeciality Hospital."},
            {"role": "user", "content": prompt}
        ])
        ai_message = AIMessage(content=response_content)
    except Exception as e:
        # Fallback query message if API fails
        ai_message = AIMessage(content=f"To proceed with scheduling, could you please tell me {fields_str}?")
        errors.append(f"Missing info prompt generation warning: {e}")

    return {
        "messages": [ai_message],
        "booking_status": "awaiting_info",
        "errors": errors
    }
