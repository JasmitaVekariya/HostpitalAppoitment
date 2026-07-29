from typing import Dict, Any
from langchain_core.messages import AIMessage
from backend.graph.state import HospitalState

def emergency_node(state: HospitalState) -> Dict[str, Any]:
    """Node to detect emergency cases and redirect patients immediately, bypassing scheduling."""
    priority = state.get("priority", "LOW")
    errors = list(state.get("errors", []))
    
    if priority == "EMERGENCY":
        emergency_msg = (
            "⚠️ CRITICAL ALERT: Based on your symptoms, this may be a medical emergency. "
            "For your safety, online appointment booking has been suspended. "
            "Please call our Emergency Line immediately at +91 79 4012 3999, "
            "or visit the nearest hospital Emergency Room (ER)."
        )
        return {
            "booking_status": "emergency_redirect",
            "messages": [AIMessage(content=emergency_msg)],
            "errors": errors
        }
        
    # If not emergency, pass through and maintain status
    return {
        "booking_status": "info_complete",
        "errors": errors
    }
