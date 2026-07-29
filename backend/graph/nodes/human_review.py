from typing import Dict, Any
import uuid
import datetime
from langchain_core.messages import AIMessage
from langgraph.types import interrupt
from backend.graph.state import HospitalState
from backend.utils.email import send_human_review_request

def human_review_node(state: HospitalState) -> Dict[str, Any]:
    """Node that triggers a human-in-the-loop review and pauses execution."""
    review_info = state.get("review_info") or {}
    
    # If the review has already been approved or handled, pass through
    if review_info.get("review_status") in ["APPROVED", "REJECTED", "EMERGENCY"]:
        return {}

    # Identify if we need to start a review
    priority = state.get("priority")
    booking_status = state.get("booking_status")
    
    # Check if a review is needed (High risk or Prescription request)
    needs_review = False
    review_type = "HIGH_RISK"
    
    if priority == "EMERGENCY" or booking_status == "emergency_redirect":
        needs_review = True
        review_type = "HIGH_RISK"
    elif booking_status == "prescription_request":
        needs_review = True
        review_type = "PRESCRIPTION"

    if not needs_review:
        return {}

    # Check if we already sent the review email and are just waiting
    if review_info.get("pending_action"):
        # Graph resumed but no decision made? Suspend again.
        interrupt("Waiting for doctor review")
        return {}

    # Initialize a new review using session_id
    review_id = state.get("session_id", str(uuid.uuid4()))
    patient_info = state.get("patient_info", {})
    symptoms = state.get("symptoms", {})
    patient_name = patient_info.get("name", "Unknown Patient")
    age = patient_info.get("age", "Unknown")
    symptoms_str = ", ".join(symptoms.get("symptoms", [])) or "None specified"
    
    # We will send this to the hospital default email for triage
    from backend.config import settings
    doctor_email = settings.EMAIL_USER
    
    # Send email asynchronously
    send_human_review_request(
        to_address=doctor_email,
        patient_name=patient_name,
        age=str(age),
        symptoms=symptoms_str,
        review_id=review_id,
        review_type=review_type
    )

    new_review_info = {
        "review_id": review_id,
        "review_type": review_type,
        "doctor_email": doctor_email,
        "pending_action": True,
        "review_status": "PENDING",
        "timestamp": datetime.datetime.utcnow().isoformat()
    }
    
    # Inform the user that we are waiting for a doctor
    wait_message = (
        "⏳ Based on your input, your case requires a doctor's review before we can proceed. "
        "A notification has been sent to our triage team. Please wait while a doctor reviews your case."
    )
    
    # Return updated state before interrupting
    # We must interrupt AFTER returning the state update so the state is saved.
    # Actually, interrupt() raises an exception that stops execution.
    # According to LangGraph docs, if we want to save state, we can return the state, 
    # and the NEXT node should be a dummy node that interrupts, OR we can call interrupt() inside the node
    # and the value returned by interrupt is assigned when resumed.
    
    # LangGraph >= 0.1 interrupt approach:
    # decision = interrupt("Waiting for doctor review")
    # if decision:
    #     ... process decision ...
    
    # To keep it simple, we will return the updated state and transition to a wait node,
    # or just use interrupt() here.
    
    # Let's send the user message first, then interrupt.
    # Actually, if we return from this node, state is saved. 
    # We can use interrupt(value) directly.
    decision = interrupt({
        "messages": [AIMessage(content=wait_message)],
        "review_info": new_review_info,
        "booking_status": "awaiting_review"
    })
    
    # When resumed via Command(resume={"decision": "APPROVE"}), the node continues here.
    action = decision.get("decision", "").upper() if isinstance(decision, dict) else str(decision).upper()
    
    final_review_info = {**new_review_info, "pending_action": False, "review_status": action}
    
    response_messages = []
    new_status = state.get("booking_status")
    
    if action == "APPROVE":
        response_messages.append(AIMessage(content="✅ The doctor has reviewed and approved your request. Let's proceed."))
        new_status = "info_complete" # Proceed to doctor_recommender
    elif action == "REJECT":
        response_messages.append(AIMessage(content="❌ The doctor has reviewed your request and determined we cannot proceed with online booking for this. Please visit the hospital or contact reception."))
        new_status = "rejected_by_doctor"
    elif action == "EMERGENCY":
        response_messages.append(AIMessage(content="⚠️ CRITICAL ALERT: A doctor has reviewed your case and marked it as a medical emergency. Please call our Emergency Line immediately at +91 79 4012 3999, or visit the nearest hospital ER."))
        new_status = "emergency_redirect"
    
    return {
        "review_info": final_review_info,
        "booking_status": new_status,
        "messages": response_messages
    }
