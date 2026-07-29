from typing import Dict, Any
import uuid
from langchain_core.messages import AIMessage
from backend.graph.state import HospitalState
from backend.database import SessionLocal
from backend.models import DoctorSchedule, Appointment, Doctor, User
from backend.utils.email import send_booking_confirmation, send_reschedule_confirmation

def finalize_booking_node(state: HospitalState) -> Dict[str, Any]:
    """Node to finalize the database insertion and email after doctor approval."""
    errors = list(state.get("errors", []))
    selected_doctor = state.get("selected_doctor")
    user_id = state.get("user_id")
    session_id = state.get("session_id")
    selected_slot = state.get("selected_slot", {})
    
    if not selected_slot:
        errors.append("Finalize Booking: No selected_slot found in state.")
        return {"errors": errors, "booking_status": "error"}
        
    db = SessionLocal()
    
    try:
        slot_id = selected_slot.get("id")
        slot_record = db.query(DoctorSchedule).filter(DoctorSchedule.id == slot_id).first()
        
        if not slot_record:
            return {"errors": errors + ["Finalize Booking: Slot record not found."]}
            
        patient_uuid = uuid.UUID(user_id)
        session_uuid = uuid.UUID(session_id) if session_id else None
        
        # Check if rescheduling
        existing_appt = None
        if session_uuid:
            existing_appt = db.query(Appointment).filter(
                Appointment.conversation_id == session_uuid,
                Appointment.booking_status == "confirmed"
            ).first()
            
        if existing_appt:
            # Complete Reschedule
            old_slot = db.query(DoctorSchedule).filter(DoctorSchedule.id == existing_appt.schedule_id).first()
            old_date = old_slot.date if old_slot else None
            old_time = old_slot.start_time if old_slot else None
            
            if old_slot:
                old_slot.status = "available"
                
            slot_record.status = "booked"
            existing_appt.schedule_id = slot_record.id
            existing_appt.status = "RESCHEDULED"
            db.commit()
            
            # Send Email
            try:
                patient_user = db.query(User).filter(User.id == existing_appt.patient_id).first()
                if patient_user:
                    send_reschedule_confirmation(
                        patient_email=patient_user.email,
                        patient_name=patient_user.name,
                        doctor_name=selected_doctor["name"] if selected_doctor else "Your Doctor",
                        specialization=selected_doctor.get("specialization", "") if selected_doctor else "",
                        new_date=slot_record.date,
                        new_time=slot_record.start_time,
                        old_date=old_date,
                        old_time=old_time,
                    )
            except Exception as email_err:
                print(f"[EMAIL] Finalize reschedule notification error: {email_err}")
                
            reschedule_msg = (
                f"🔄 Appointment Rescheduled successfully!\n\n"
                f"Your appointment with {selected_doctor['name']} ({selected_doctor['specialization']}) has been officially moved to "
                f"{slot_record.date.strftime('%A, %B %d, %Y')} at {slot_record.start_time.strftime('%I:%M %p')}.\n\n"
                f"A new confirmation email has been sent to your registered address."
            )
            
            return {
                "booking_status": "confirmed",
                "available_slots": [],
                "selected_doctor": None,
                "selected_slot": None,
                "messages": [AIMessage(content=reschedule_msg)],
                "errors": errors
            }
        else:
            # Complete New Booking
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
            slot_record.status = "booked"
            db.commit()
            
            # Send Email
            try:
                patient_user = db.query(User).filter(User.id == patient_uuid).first()
                doc_record = db.query(Doctor).filter(Doctor.id == slot_record.doctor_id).first()
                if patient_user and doc_record:
                    from backend.models import Department
                    dept = db.query(Department).filter(Department.id == doc_record.department_id).first()
                    send_booking_confirmation(
                        patient_email=patient_user.email,
                        patient_name=patient_user.name,
                        doctor_name=doc_record.name,
                        specialization=doc_record.specialization,
                        department=dept.name if dept else "",
                        appointment_date=slot_record.date,
                        appointment_time=slot_record.start_time,
                        symptoms=", ".join(symptom_list) if symptom_list else "",
                        floor=str(dept.floor) if dept else None,
                    )
            except Exception as email_err:
                print(f"[EMAIL] Finalize booking notification error: {email_err}")
                
            confirmation_msg = (
                f"🎉 Booking Confirmed!\n\n"
                f"Your appointment with {selected_doctor['name']} ({selected_doctor['specialization']}) is booked for "
                f"{slot_record.date.strftime('%A, %B %d, %Y')} at {slot_record.start_time.strftime('%I:%M %p')}.\n\n"
                f"A confirmation email has been sent to your registered address."
            )
            
            return {
                "booking_status": "confirmed",
                "available_slots": [],
                "selected_doctor": None,
                "selected_slot": None,
                "messages": [AIMessage(content=confirmation_msg)],
                "errors": errors
            }
            
    except Exception as e:
        print(f"[DEBUG] Finalize booking failed: {e}")
        db.rollback()
        errors.append(f"Finalize booking DB error: {e}")
        return {
            "booking_status": "awaiting_slot_selection",
            "messages": [AIMessage(content="There was an error saving your appointment after doctor approval.")],
            "errors": errors
        }
    finally:
        db.close()
