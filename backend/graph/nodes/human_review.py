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
    elif booking_status == "appointment_approval_required":
        needs_review = True
        review_type = "APPOINTMENT_APPROVAL"

    if not needs_review:
        return {}

    # Check if we already sent the review email and are just waiting
    if review_info.get("pending_action"):
        decision = interrupt("Waiting for doctor review")
        action = decision.get("decision", "").upper() if isinstance(decision, dict) else str(decision).upper()
        
        final_review_info = {**review_info, "pending_action": False, "review_status": action}
        
        response_messages = []
        new_status = state.get("booking_status")
        
        if action == "APPROVE":
            if review_info.get("review_type") == "APPOINTMENT_APPROVAL":
                response_messages.append(AIMessage(content="✅ The doctor has approved your appointment slot."))
                new_status = "appointment_approved"
            else:
                response_messages.append(AIMessage(content="✅ The doctor has reviewed and approved your request. Let's proceed."))
                new_status = "info_complete" # Proceed to doctor_recommender
        elif action == "REJECT":
            if review_info.get("review_type") == "APPOINTMENT_APPROVAL":
                response_messages.append(AIMessage(content="❌ The doctor is unable to confirm this specific slot. Please select a different time or doctor."))
                new_status = "awaiting_slot_selection"
            else:
                response_messages.append(AIMessage(content="❌ The doctor has reviewed your request and determined we cannot proceed with online booking for this. Please visit the hospital or contact reception."))
                new_status = "rejected_by_doctor"
        elif action == "EMERGENCY":
            response_messages.append(AIMessage(content="⚠️ CRITICAL ALERT: A doctor has reviewed your case and marked it as a medical emergency. Please call our Emergency Line immediately at +91 79 4012 3999, or visit the nearest hospital ER."))
            new_status = "emergency_redirect"
        
        if review_info.get("review_type") == "APPOINTMENT_APPROVAL":
            from backend.database import SessionLocal
            from backend.models import Appointment
            import uuid
            
            db = SessionLocal()
            try:
                session_uuid = uuid.UUID(state.get("session_id")) if state.get("session_id") else None
                if session_uuid:
                    pending_appt = db.query(Appointment).filter(
                        Appointment.conversation_id == session_uuid,
                        Appointment.status == "PENDING"
                    ).first()
                    
                    if pending_appt:
                        if action in ["REJECT", "EMERGENCY"]:
                            pending_appt.status = "CANCELLED"
                            db.commit()
            except Exception as e:
                print(f"[DEBUG] Error updating pending appointment status on human review: {e}")
            finally:
                db.close()
                
        return {
            "review_info": final_review_info,
            "booking_status": new_status,
            "messages": response_messages
        }

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
    
    details = ""
    if review_type == "APPOINTMENT_APPROVAL":
        selected_slot = state.get("selected_slot", {})
        if selected_slot:
            details = f"Requested Slot: {selected_slot.get('date', 'Unknown Date')} at {selected_slot.get('start_time', 'Unknown Time')}"

    # Send email asynchronously
    send_human_review_request(
        to_address=doctor_email,
        patient_name=patient_name,
        age=str(age),
        symptoms=symptoms_str,
        review_id=review_id,
        review_type=review_type,
        details=details
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
    wait_message = "⏳ you will notify when doctor accept this req"
    
    # Return state update. This routes back to human_review which then triggers the interrupt.
    return {
        "messages": [AIMessage(content=wait_message)],
        "review_info": new_review_info,
        "booking_status": "awaiting_review"
    }
