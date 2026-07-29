import re
import uuid
from typing import Dict, Any
from langchain_core.messages import AIMessage
from backend.graph.state import HospitalState
from backend.database import SessionLocal
from backend.models import DoctorSchedule, Appointment, Doctor, User

def booking_node(state: HospitalState) -> Dict[str, Any]:
    """Node to process slot selection, prevent user scheduling overlaps, and commit appointments."""
    messages = state.get("messages", [])
    errors = list(state.get("errors", []))
    available_slots = state.get("available_slots", [])
    selected_doctor = state.get("selected_doctor")
    user_id = state.get("user_id")
    session_id = state.get("session_id")
    
    if not messages:
        return {"errors": ["No message history found"]}
        
    last_message = messages[-1].content.strip().lower()
    
    db = SessionLocal()
    
    # Check if we are rescheduling (an active confirmed appointment exists in this chat session!)
    existing_appt = None
    if session_id:
        try:
            existing_appt = db.query(Appointment).filter(
                Appointment.conversation_id == uuid.UUID(session_id),
                Appointment.booking_status == "confirmed"
            ).first()
        except Exception as e:
            print(f"[DEBUG] Error checking existing appt in booking node: {e}")
            
    # 1. Parse slot option choice (e.g. "1", "2", "3", "option 1", "option 2")
    option_match = re.search(r"(?:option\s+)?(\d)", last_message)
    selected_option = int(option_match.group(1)) if option_match else None
    
    # If the user has an existing appointment but did not select a slot option, check if they want to keep the current one
    if existing_appt and not selected_option:
        refusal_prompt = (
            "Analyze the patient's latest message in the context of their upcoming appointment. "
            "Determine if they want to keep their existing appointment time, decline rescheduling, "
            "or confirm that their current scheduled time is fine.\n\n"
            f"Patient message: \"{last_message}\"\n\n"
            "Return a JSON object with a single boolean field 'keep_existing': true or false."
        )
        try:
            from backend.utils.llm import call_openrouter_api, parse_json_markdown
            response = call_openrouter_api([
                {"role": "system", "content": "You are a medical receptionist assistant. Return JSON only."},
                {"role": "user", "content": refusal_prompt}
            ])
            res = parse_json_markdown(response)
            if res.get("keep_existing") is True:
                patient_user = db.query(User).filter(User.id == existing_appt.patient_id).first()
                patient_name = patient_user.name if patient_user else "Patient"
                
                db_doc = db.query(Doctor).filter(Doctor.id == existing_appt.doctor_id).first()
                doc_name = db_doc.name if db_doc else "Dr. Rahul Shah"
                
                existing_sched = db.query(DoctorSchedule).filter(DoctorSchedule.id == existing_appt.schedule_id).first()
                original_date = existing_sched.date.strftime('%B %d, %Y') if existing_sched else "N/A"
                original_time = existing_sched.start_time.strftime('%I:%M %p') if existing_sched else "N/A"
                
                confirm_prompt = (
                    f"Format the following message template with the correct variables:\n\n"
                    f"Dear {patient_name},\n\n"
                    f"Your appointment with {doc_name} on {original_date} at {original_time} is still confirmed. "
                    f"We look forward to seeing you then.\n\n"
                    f"Best,\n"
                    f"Sunrise Hospital Reception Team.\n\n"
                    f"Ensure you return this exact formatted text, substituting values correctly. Output only the message text without extra conversational comments."
                )
                confirm_reply = call_openrouter_api([
                    {"role": "system", "content": "You are a warm receptionist at Sunrise Hospital. Return the requested text only."},
                    {"role": "user", "content": confirm_prompt}
                ])
                db.close()
                return {
                    "booking_status": "confirmed",
                    "available_slots": [],
                    "selected_doctor": None,
                    "messages": [AIMessage(content=confirm_reply)],
                    "errors": errors
                }
        except Exception as e:
            print(f"[DEBUG] Error classifying reschedule refusal: {e}")
            
    # If the user did not select an option, route back to triage to handle query/symptoms
    if not selected_option or not available_slots or selected_option < 1 or selected_option > len(available_slots):
        db.close()
        return {
            "booking_status": "info_complete", # Reset status to force re-triage / scheduling evaluation
            "errors": errors
        }
        
    # Get chosen slot details
    chosen_slot_data = available_slots[selected_option - 1]
    slot_id = chosen_slot_data["id"]
    
    try:
        # Fetch slot record
        slot_record = db.query(DoctorSchedule).filter(DoctorSchedule.id == slot_id).first()
        if not slot_record or slot_record.status != "available":
            return {
                "booking_status": "awaiting_slot_selection",
                "messages": [AIMessage(content="I'm sorry, that slot was just booked by another patient. Please select one of the other options.")],
                "errors": errors
            }
            
        patient_uuid = uuid.UUID(user_id)
        session_uuid = uuid.UUID(session_id) if session_id else None
        
        # Check if we are rescheduling (an active confirmed appointment exists in this chat session!)
        existing_appt = None
        if session_uuid:
            existing_appt = db.query(Appointment).filter(
                Appointment.conversation_id == session_uuid,
                Appointment.booking_status == "confirmed"
            ).first()
            
        if existing_appt:
            # 2a. Overlap Prevention for Rescheduling: check for overlap excluding this appointment
            overlapping_appt = db.query(Appointment).join(DoctorSchedule).filter(
                Appointment.patient_id == patient_uuid,
                Appointment.booking_status == "confirmed",
                Appointment.id != existing_appt.id,
                DoctorSchedule.date == slot_record.date,
                DoctorSchedule.start_time == slot_record.start_time
            ).first()
            
            if overlapping_appt:
                db_doc = db.query(Doctor).filter(Doctor.id == overlapping_appt.doctor_id).first()
                doc_name = db_doc.name if db_doc else "another doctor"
                alert_msg = (
                    f"⚠️ SCHEDULE OVERLAP: You already have a confirmed appointment with {doc_name} "
                    f"at this exact time ({slot_record.date.strftime('%B %d, %Y')} at {slot_record.start_time.strftime('%I:%M %p')}).\n\n"
                    f"Please select a different option, or type a different symptom to find other timings."
                )
                return {
                    "booking_status": "awaiting_slot_selection",
                    "messages": [AIMessage(content=alert_msg)],
                    "errors": errors
                }
                
            # 3a. Commit Reschedule
            # Free old slot
            old_slot = db.query(DoctorSchedule).filter(DoctorSchedule.id == existing_appt.schedule_id).first()
            if old_slot:
                old_slot.status = "available"
                
            # Bind new slot
            slot_record.status = "booked"
            existing_appt.schedule_id = slot_record.id
            existing_appt.status = "RESCHEDULED"
            db.commit()
            
            reschedule_msg = (
                f"🔄 Appointment Rescheduled successfully!\n\n"
                f"Your appointment with {selected_doctor['name']} ({selected_doctor['specialization']}) has been moved to "
                f"{slot_record.date.strftime('%A, %B %d, %Y')} at {slot_record.start_time.strftime('%I:%M %p')}.\n\n"
                f"A new confirmation email has been sent to your registered address."
            )
            return {
                "booking_status": "confirmed",
                "available_slots": [],
                "selected_doctor": None,
                "messages": [AIMessage(content=reschedule_msg)],
                "errors": errors
            }
            
        # 2b. Overlap Prevention for New Booking
        overlapping_appt = db.query(Appointment).join(DoctorSchedule).filter(
            Appointment.patient_id == patient_uuid,
            Appointment.booking_status == "confirmed",
            DoctorSchedule.date == slot_record.date,
            DoctorSchedule.start_time == slot_record.start_time
        ).first()
        
        if overlapping_appt:
            db_doc = db.query(Doctor).filter(Doctor.id == overlapping_appt.doctor_id).first()
            doc_name = db_doc.name if db_doc else "another doctor"
            alert_msg = (
                f"⚠️ SCHEDULE OVERLAP: You already have a confirmed appointment with {doc_name} "
                f"at this exact time ({slot_record.date.strftime('%B %d, %Y')} at {slot_record.start_time.strftime('%I:%M %p')}).\n\n"
                f"Please select a different option, or type a different symptom to find other timings."
            )
            return {
                "booking_status": "awaiting_slot_selection",
                "messages": [AIMessage(content=alert_msg)],
                "errors": errors
            }
            
        # 3b. Commit New Booking
        symptom_list = state.get("symptoms", {}).get("symptoms", [])
        new_appointment = Appointment(
            patient_id=patient_uuid,
            doctor_id=slot_record.doctor_id,
            schedule_id=slot_record.id,
            symptoms=str(symptom_list),
            symptom_summary=", ".join(symptom_list),
            booking_status="confirmed",
            status="UPCOMING",
            conversation_id=session_uuid
        )
        db.add(new_appointment)
        
        # Mark slot as booked
        slot_record.status = "booked"
        db.commit()
        
        confirmation_msg = (
            f"🎉 Booking Confirmed!\n\n"
            f"Your appointment with {selected_doctor['name']} ({selected_doctor['specialization']}) is booked for "
            f"{slot_record.date.strftime('%A, %B %d, %Y')} at {slot_record.start_time.strftime('%I:%M %p')}.\n\n"
            f"A confirmation email has been sent to your registered address."
        )
        
        # Clear slot state to reset booking context for the next booking
        return {
            "booking_status": "confirmed",
            "available_slots": [],
            "selected_doctor": None,
            "messages": [AIMessage(content=confirmation_msg)],
            "errors": errors
        }
        
    except Exception as e:
        print(f"[DEBUG] Booking confirmation failed: {e}")
        db.rollback()
        errors.append(f"Booking database confirmation error: {e}")
        return {
            "booking_status": "awaiting_slot_selection",
            "messages": [AIMessage(content="I encountered an issue booking your appointment in the database. Please try selecting the slot again.")],
            "errors": errors
        }
    finally:
        db.close()
