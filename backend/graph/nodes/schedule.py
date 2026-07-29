import datetime
import uuid
from typing import Dict, Any, List
from langchain_core.messages import AIMessage
from backend.graph.state import HospitalState
from backend.database import SessionLocal
from backend.models import DoctorSchedule, Appointment, Doctor
from backend.config import settings

def schedule_node(state: HospitalState) -> Dict[str, Any]:
    """Node to find, optimize, and present the top 3 available slots for the recommended doctor candidate."""
    candidates = state.get("doctor_candidates", [])
    errors = list(state.get("errors", []))
    session_id = state.get("session_id")
    
    # If rescheduling an existing appointment in this chat session, force candidates strictly to that doctor
    if session_id and candidates:
        db = SessionLocal()
        try:
            existing_appt = db.query(Appointment).filter(
                Appointment.conversation_id == uuid.UUID(session_id),
                Appointment.booking_status == "confirmed"
            ).first()
            if existing_appt:
                db_doc = db.query(Doctor).filter(Doctor.id == existing_appt.doctor_id).first()
                if db_doc:
                    candidates = [{
                        "id": db_doc.id,
                        "name": db_doc.name,
                        "specialization": db_doc.specialization,
                        "experience_years": db_doc.experience_years,
                        "consultation_fee": float(db_doc.consultation_fee)
                    }]
        except Exception as e:
            print(f"[DEBUG] Failed to resolve reschedule doctor candidate: {e}")
        finally:
            db.close()
            
    if not candidates:
        return {
            "booking_status": "no_doctors_available",
            "messages": [AIMessage(content="I'm sorry, we couldn't find any available doctors matching your request at this time.")],
            "errors": errors
        }
        
    # Detect if user is asking for alternative/other slots
    user_msgs = [m.content.lower() for m in state.get("messages", []) if m.type == "human"]
    last_user_msg = user_msgs[-1] if user_msgs else ""
    
    is_asking_alternative = False
    alternative_keywords = ["other slot", "alternative", "different time", "next slot", "more slot", "any other", "another slot", "change time", "else"]
    for kw in alternative_keywords:
        if kw in last_user_msg:
            is_asking_alternative = True
            break

    db = SessionLocal()
    selected_doctor = state.get("selected_doctor")
    available_slots = []
    today = datetime.date.today()
    max_days = today + datetime.timedelta(days=30)
    
    # Configure pagination pivot
    prev_slots = state.get("available_slots", [])
    last_date = today
    last_time = datetime.time(0, 0)
    if is_asking_alternative and prev_slots:
        try:
            last_slot = prev_slots[-1]
            last_date = datetime.datetime.strptime(last_slot["date"], "%Y-%m-%d").date()
            last_time = datetime.datetime.strptime(last_slot["start_time"], "%I:%M %p").time()
        except Exception as e:
            print(f"[DEBUG] Error parsing previous slots for alternative search: {e}")

    try:
        # If we already have a selected doctor, prioritize them for alternative slots
        doctors_to_check = [selected_doctor] if (selected_doctor and is_asking_alternative) else candidates
        
        for doc in doctors_to_check:
            doc_id = doc["id"]
            
            # Query slots chronologically after the pivot (paging forward)
            query = db.query(DoctorSchedule).filter(
                DoctorSchedule.doctor_id == doc_id,
                DoctorSchedule.status == "available"
            )
            
            if is_asking_alternative and prev_slots:
                query = query.filter(
                    (DoctorSchedule.date > last_date) |
                    ((DoctorSchedule.date == last_date) & (DoctorSchedule.start_time > last_time))
                )
            else:
                query = query.filter(DoctorSchedule.date >= today)
                
            slots = query.filter(DoctorSchedule.date <= max_days).order_by(
                DoctorSchedule.date, DoctorSchedule.start_time
            ).all()
            
            # Filter past slots and apply booking buffer (Rule 1, 2, 3, 4)
            now = datetime.datetime.now()
            booking_buffer = getattr(settings, "BOOKING_BUFFER_MINUTES", 120)
            boundary_datetime = now + datetime.timedelta(minutes=booking_buffer)
            
            filtered_slots = []
            for s in slots:
                slot_datetime = datetime.datetime.combine(s.date, s.start_time)
                if slot_datetime >= boundary_datetime:
                    filtered_slots.append(s)
            
            # Select top 3 filtered slots
            slots_to_suggest = filtered_slots[:3]
            
            if slots_to_suggest:
                selected_doctor = doc
                for s in slots_to_suggest:
                    available_slots.append({
                        "id": s.id,
                        "date": s.date.isoformat(),
                        "day": s.date.strftime("%A"),
                        "start_time": s.start_time.strftime("%I:%M %p"),
                        "end_time": s.end_time.strftime("%I:%M %p")
                    })
                break
                
    except Exception as e:
        print(f"[DEBUG] Slot optimization query failed: {e}")
        errors.append(f"Slot optimization warning: {e}")
    finally:
        db.close()
        
    if not selected_doctor or not available_slots:
        return {
            "booking_status": "no_slots_available",
            "messages": [AIMessage(content=f"All doctors in the department are currently fully booked for the next 30 days.")],
            "errors": errors
        }
        
    # Generate friendly response presenting the slots
    slots_text = "\n".join([
        f"{idx + 1}. {datetime.datetime.strptime(s['date'], '%Y-%m-%d').strftime('%A, %B %d, %Y')} at {s['start_time']}"
        for idx, s in enumerate(available_slots)
    ])
    
    # Extract symptoms list for empathetic response
    symptom_list = state.get("symptoms", {}).get("symptoms", [])
    symptoms_str = ", ".join(symptom_list) if symptom_list else "general health symptoms"
    
    schedule_prompt = (
        f"You are a warm, empathetic medical receptionist at Sunrise Multispeciality Hospital.\n"
        f"Your task is to draft a natural, conversational response to the patient recommending {selected_doctor['name']} "
        f"({selected_doctor['specialization']}) and presenting the available slots below.\n\n"
        f"Doctor Details:\n"
        f"- Name: {selected_doctor['name']}\n"
        f"- Specialization: {selected_doctor['specialization']}\n"
        f"- Consultation Fee: ${selected_doctor['consultation_fee']:.2f}\n\n"
        f"Symptoms: {symptoms_str}\n\n"
        f"Available Slots:\n{slots_text}\n\n"
        f"Draft a concise but warm message presenting this recommendation and these slots. "
        f"Acknowledge the symptoms empatheticially. Avoid robotic phrases like 'Your symptom has been noted.' "
        f"Clearly instruct the patient to reply with the slot number (1, 2, or 3) they prefer to confirm their booking."
    )
    
    try:
        from backend.utils.llm import call_openrouter_api
        api_messages = []
        # Include conversation history for context
        for msg in state.get("messages", []):
            role = "user" if msg.type == "human" else ("assistant" if msg.type == "ai" else msg.type)
            api_messages.append({"role": role, "content": msg.content})
            
        api_messages.append({"role": "system", "content": schedule_prompt})
        ai_response = call_openrouter_api(api_messages)
    except Exception as e:
        print(f"[DEBUG] Failed to generate LLM schedule response: {e}")
        ai_response = (
            f"Based on your symptoms ({symptoms_str}), I recommend booking an appointment with {selected_doctor['name']} "
            f"({selected_doctor['specialization']}). The consultation fee is ${selected_doctor['consultation_fee']:.2f}.\n\n"
            f"Here are the earliest available slots:\n{slots_text}\n\n"
            f"Please reply with the slot number (1, 2, or 3) you prefer to confirm your booking."
        )
    
    return {
        "selected_doctor": selected_doctor,
        "available_slots": available_slots,
        "booking_status": "awaiting_slot_selection",
        "messages": [AIMessage(content=ai_response)],
        "errors": errors
    }
