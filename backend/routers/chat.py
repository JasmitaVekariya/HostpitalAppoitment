import uuid
import datetime
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import User, Conversation, Appointment
from backend.schemas.chat import ChatRequest, ChatResponse
from backend.utils.auth_deps import get_current_user
from backend.graph.workflow import app as graph_app
from langchain_core.messages import HumanMessage, AIMessage
from backend.utils.email import (
    send_booking_confirmation,
    send_reschedule_confirmation,
    send_cancellation_notice,
    send_completion_summary,
)

def update_missed_appointments(db: Session):
    """Automatically transition appointments to MISSED if their time has passed and they are not COMPLETED/CANCELLED."""
    now = datetime.datetime.now()
    from backend.models import DoctorSchedule
    
    # Query all appointments in active statuses (UPCOMING, SCHEDULED, RESCHEDULED)
    active_appointments = db.query(Appointment).filter(
        Appointment.status.in_(["UPCOMING", "SCHEDULED", "RESCHEDULED"])
    ).all()
    
    updated = False
    for appt in active_appointments:
        if appt.schedule:
            # Combine schedule date and end_time to get slot end datetime
            slot_end_datetime = datetime.datetime.combine(appt.schedule.date, appt.schedule.end_time)
            if now > slot_end_datetime:
                appt.status = "MISSED"
                updated = True
    if updated:
        db.commit()

router = APIRouter(prefix="/api", tags=["Chat"])

@router.post("/chat", response_model=ChatResponse)
def handle_chat_message(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Secure conversational endpoint that drives the LangGraph multi-agent appointment workflow."""
    update_missed_appointments(db)
    session_id = payload.session_id
    message_content = payload.message

    # Validate that session_id is a valid UUID
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session_id must be a valid UUID string"
        )

    # Validate that the session belongs to the logged-in user (avoid cross-tenant access)
    conversation = db.query(Conversation).filter(
        Conversation.id == session_uuid,
        Conversation.user_id == current_user.id
    ).first()

    if not conversation:
        # Create a new conversation audit record in DB
        conversation = Conversation(
            id=session_uuid,
            user_id=current_user.id,
            messages=[],
            current_state={}
        )
        db.add(conversation)
        db.flush()

    # Configure graph execution context with the session ID as thread_id
    config = {"configurable": {"thread_id": str(session_uuid)}}
    
    # Sync database conversation state into the in-memory graph checkpointer
    if conversation and conversation.current_state:
        state_to_update = {}
        for k, v in conversation.current_state.items():
            if k != "messages":
                state_to_update[k] = v
                
        # If the checkpointer thread history is empty, restore messages from database
        try:
            current_graph_state = graph_app.get_state(config)
            if not current_graph_state.values.get("messages"):
                messages_to_restore = []
                for msg in (conversation.messages or []):
                    role = msg.get("role")
                    content = msg.get("content")
                    if role == "user":
                        messages_to_restore.append(HumanMessage(content=content))
                    elif role == "assistant":
                        messages_to_restore.append(AIMessage(content=content))
                state_to_update["messages"] = messages_to_restore
                
            graph_app.update_state(config, state_to_update)
        except Exception as e:
            print(f"[DEBUG] Failed to restore checkpointer state: {e}")

    inputs = {
        "messages": [HumanMessage(content=message_content)],
        "user_id": str(current_user.id),
        "session_id": str(session_uuid)
    }

    try:
        # Run the compiled LangGraph workflow
        final_state = graph_app.invoke(inputs, config)
        
        # Check if we need to redirect due to a department mismatch (different symptom type!)
        new_dept = final_state.get("department")
        if conversation and new_dept:
            existing_appt = db.query(Appointment).filter(
                Appointment.conversation_id == session_uuid,
                Appointment.booking_status == "confirmed"
            ).first()
            if existing_appt:
                from backend.models import Doctor, Department
                doc = db.query(Doctor).filter(Doctor.id == existing_appt.doctor_id).first()
                if doc:
                    dept = db.query(Department).filter(Department.id == doc.department_id).first()
                    if dept and dept.name != new_dept:
                        # Redirect to a fresh conversation session ID!
                        new_session_uuid = uuid.uuid4()
                        
                        # Create the new conversation record in DB
                        new_conversation = Conversation(
                            id=new_session_uuid,
                            user_id=current_user.id,
                            messages=[],
                            current_state={}
                        )
                        db.add(new_conversation)
                        db.flush()
                        
                        # Run a fresh graph execution under the new session
                        new_config = {"configurable": {"thread_id": str(new_session_uuid)}}
                        new_inputs = {
                            "messages": [HumanMessage(content=message_content)],
                            "user_id": str(current_user.id),
                            "session_id": str(new_session_uuid)
                        }
                        final_state = graph_app.invoke(new_inputs, new_config)
                        session_uuid = new_session_uuid
                        conversation = new_conversation
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LangGraph execution error: {e}"
        )

    # Serialize message history for database audit and client response
    serialized_messages = []
    for msg in final_state.get("messages", []):
        if msg.type == "human":
            role = "user"
        elif msg.type == "ai":
            role = "assistant"
        else:
            role = msg.type
        serialized_messages.append({"role": role, "content": msg.content})

    # Save state snapshots to database
    conversation.messages = serialized_messages
    conversation.current_state = {
        "patient_info": final_state.get("patient_info", {}),
        "booking_status": final_state.get("booking_status"),
        "intent": final_state.get("intent"),
        "language": final_state.get("language"),
        "department": final_state.get("department"),
        "priority": final_state.get("priority"),
        "doctor_candidates": final_state.get("doctor_candidates", []),
        "selected_doctor": final_state.get("selected_doctor"),
        "available_slots": final_state.get("available_slots", []),
        "topic_shifted": final_state.get("topic_shifted", False)
    }
    db.commit()

    return {
        "session_id": str(session_uuid),
        "messages": serialized_messages,
        "patient_info": final_state.get("patient_info", {}),
        "booking_status": final_state.get("booking_status"),
        "department": final_state.get("department"),
        "priority": final_state.get("priority"),
        "doctor_candidates": final_state.get("doctor_candidates", []),
        "selected_doctor": final_state.get("selected_doctor"),
        "available_slots": final_state.get("available_slots", []),
        "topic_shifted": final_state.get("topic_shifted", False)
    }

@router.post("/chat/new")
def start_new_chat_session(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Start a fresh chat session by creating an empty Conversation in the database."""
    import uuid
    from backend.models import Conversation
    
    session_uuid = uuid.uuid4()
    conversation = Conversation(
        id=session_uuid,
        user_id=current_user.id,
        messages=[],
        current_state={}
    )
    db.add(conversation)
    db.commit()
    
    return {
        "session_id": str(session_uuid),
        "messages": [],
        "booking_status": "awaiting_info",
        "status": "PENDING"
    }

@router.get("/appointments")
def get_user_appointments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve all appointments and active conversations for the authenticated patient."""
    update_missed_appointments(db)
    from backend.models import Doctor, DoctorSchedule, Conversation, PatientConversation
    
    # 1. Fetch all appointments
    appointments = db.query(Appointment).filter(
        Appointment.patient_id == current_user.id
    ).order_by(Appointment.created_at.desc()).all()
    
    linked_conv_ids = {appt.conversation_id for appt in appointments if appt.conversation_id}
    
    result = []
    for appt in appointments:
        doc = db.query(Doctor).filter(Doctor.id == appt.doctor_id).first()
        sched = db.query(DoctorSchedule).filter(DoctorSchedule.id == appt.schedule_id).first()
        result.append({
            "id": str(appt.id),
            "doctor_name": doc.name if doc else "Unknown Doctor",
            "specialization": doc.specialization if doc else "General",
            "date": sched.date.strftime("%Y-%m-%d") if sched else "N/A",
            "start_time": sched.start_time.strftime("%I:%M %p") if sched else "N/A",
            "booking_status": appt.booking_status,
            "status": appt.status or "UPCOMING",
            "doctor_notes": appt.doctor_notes,
            "completed_at": appt.completed_at.isoformat() if appt.completed_at else None,
            "symptoms": appt.symptoms,
            "symptom_summary": appt.symptom_summary,
            "conversation_id": str(appt.conversation_id) if appt.conversation_id else None,
            "created_at": appt.created_at.isoformat(),
            "is_booked": True
        })
        
    # 2. Fetch all conversations that are not linked to any booked appointment
    conversations = db.query(Conversation).filter(
        Conversation.user_id == current_user.id
    ).order_by(Conversation.updated_at.desc()).all()
    
    for conv in conversations:
        if conv.id not in linked_conv_ids:
            # Query extracted symptoms from PatientConversation memory table
            pat_conv = db.query(PatientConversation).filter(
                PatientConversation.conversation_id == conv.id
            ).first()
            symptom_list = pat_conv.current_symptoms if pat_conv else []
            symptoms_str = str(symptom_list)
            symptom_summary = ", ".join(symptom_list)
            
            result.append({
                "id": f"conv_{str(conv.id)}",
                "doctor_name": "AI Triage Assistant",
                "specialization": "Hospital Reception",
                "date": "N/A",
                "start_time": "N/A",
                "booking_status": "pending",
                "status": "PENDING",
                "doctor_notes": None,
                "completed_at": None,
                "symptoms": symptoms_str,
                "symptom_summary": symptom_summary,
                "conversation_id": str(conv.id),
                "created_at": conv.updated_at.isoformat(),
                "is_booked": False
            })
            
    # Sort merged result by created_at/activity desc
    result.sort(key=lambda x: x["created_at"], reverse=True)
    return result

@router.get("/chat/{session_id}")
def get_chat_history(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve the message history and current state for a chat session."""
    import uuid
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session UUID")
        
    conversation = db.query(Conversation).filter(
        Conversation.id == session_uuid,
        Conversation.user_id == current_user.id
    ).first()
    
    if not conversation:
        return {
            "messages": [],
            "patient_info": {},
            "booking_status": "awaiting_info"
        }
        
    state = conversation.current_state or {}
    return {
        "messages": conversation.messages,
        "patient_info": state.get("patient_info", {}),
        "booking_status": state.get("booking_status", "awaiting_info"),
        "department": state.get("department"),
        "priority": state.get("priority"),
        "selected_doctor": state.get("selected_doctor"),
        "available_slots": state.get("available_slots", [])
    }

@router.post("/appointments/{appointment_id}/cancel")
def cancel_appointment(
    appointment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Cancel an appointment and restore schedule slot availability."""
    import uuid
    from backend.models import Appointment, DoctorSchedule
    try:
        appt_uuid = uuid.UUID(appointment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid appointment UUID")
        
    appt = db.query(Appointment).filter(
        Appointment.id == appt_uuid,
        Appointment.patient_id == current_user.id
    ).first()
    
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
        
    if appt.booking_status == "cancelled":
        return {"status": "already_cancelled"}
        
    appt.booking_status = "cancelled"
    appt.status = "CANCELLED"
    
    # Restore slot status to available
    sched = db.query(DoctorSchedule).filter(DoctorSchedule.id == appt.schedule_id).first()
    if sched:
        sched.status = "available"
        
    db.commit()

    # Send cancellation email notification (non-blocking)
    try:
        from backend.models import Doctor
        doc = db.query(Doctor).filter(Doctor.id == appt.doctor_id).first()
        if sched:
            send_cancellation_notice(
                patient_email=current_user.email,
                patient_name=current_user.name,
                doctor_name=doc.name if doc else "Your Doctor",
                appointment_date=sched.date,
                appointment_time=sched.start_time,
            )
    except Exception as email_err:
        print(f"[EMAIL] Cancel notification error: {email_err}")

    return {"status": "success", "message": "Appointment cancelled successfully"}

class RescheduleRequest(BaseModel):
    new_schedule_id: int

@router.post("/appointments/{appointment_id}/reschedule")
def reschedule_appointment(
    appointment_id: str,
    payload: RescheduleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Reschedule an existing appointment to a new available slot."""
    import uuid
    from backend.models import Appointment, DoctorSchedule
    try:
        appt_uuid = uuid.UUID(appointment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid appointment UUID")
        
    appt = db.query(Appointment).filter(
        Appointment.id == appt_uuid,
        Appointment.patient_id == current_user.id
    ).first()
    
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
        
    # Get new slot
    new_sched = db.query(DoctorSchedule).filter(
        DoctorSchedule.id == payload.new_schedule_id,
        DoctorSchedule.status == "available"
    ).first()
    
    if not new_sched:
        raise HTTPException(status_code=400, detail="Requested slot is not available")
        
    # Free old slot
    old_sched = db.query(DoctorSchedule).filter(DoctorSchedule.id == appt.schedule_id).first()
    if old_sched:
        old_sched.status = "available"
        
    # Book new slot
    new_sched.status = "booked"
    appt.schedule_id = new_sched.id
    appt.status = "RESCHEDULED"
    
    db.commit()

    # Send reschedule email notification (non-blocking)
    try:
        from backend.models import Doctor
        doc = db.query(Doctor).filter(Doctor.id == appt.doctor_id).first()
        send_reschedule_confirmation(
            patient_email=current_user.email,
            patient_name=current_user.name,
            doctor_name=doc.name if doc else "Your Doctor",
            specialization=doc.specialization if doc else "",
            new_date=new_sched.date,
            new_time=new_sched.start_time,
            old_date=old_sched.date if old_sched else None,
            old_time=old_sched.start_time if old_sched else None,
        )
    except Exception as email_err:
        print(f"[EMAIL] Reschedule notification error: {email_err}")

    return {"status": "success", "message": "Appointment rescheduled successfully"}

class CompleteAppointmentRequest(BaseModel):
    doctor_notes: Optional[str] = None

@router.post("/appointments/{appointment_id}/complete")
def complete_appointment(
    appointment_id: str,
    payload: CompleteAppointmentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark an appointment as completed and record doctor notes and timestamp."""
    import uuid
    from backend.models import Appointment
    
    if current_user.role != "doctor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted to doctors only."
        )
        
    try:
        appt_uuid = uuid.UUID(appointment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid appointment UUID")
        
    appt = db.query(Appointment).filter(Appointment.id == appt_uuid).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
        
    appt.status = "COMPLETED"
    appt.completed_at = datetime.datetime.utcnow()
    appt.doctor_notes = payload.doctor_notes
    
    db.commit()

    # Send completion summary email (non-blocking)
    try:
        from backend.models import DoctorSchedule
        patient = db.query(User).filter(User.id == appt.patient_id).first()
        sched = db.query(DoctorSchedule).filter(DoctorSchedule.id == appt.schedule_id).first()
        if patient and sched:
            send_completion_summary(
                patient_email=patient.email,
                patient_name=patient.name,
                doctor_name=current_user.name,
                appointment_date=sched.date,
                doctor_notes=payload.doctor_notes,
            )
    except Exception as email_err:
        print(f"[EMAIL] Completion notification error: {email_err}")

    return {"status": "success", "message": "Appointment marked as completed successfully."}

@router.get("/doctor/appointments")
def get_doctor_appointments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve all appointments booked with the logged-in doctor, including patient names, symptoms, and schedule slots."""
    update_missed_appointments(db)
    from backend.models import Doctor, DoctorSchedule, User
    
    # Verify current user is a doctor
    if current_user.role != "doctor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted to doctors only."
        )
        
    doc = db.query(Doctor).filter(Doctor.user_id == current_user.id).first()
    if not doc:
        raise HTTPException(
            status_code=404,
            detail="Doctor profile not found."
        )
        
    appointments = db.query(Appointment).filter(
        Appointment.doctor_id == doc.id
    ).order_by(Appointment.created_at.desc()).all()
    
    result = []
    for appt in appointments:
        patient = db.query(User).filter(User.id == appt.patient_id).first()
        sched = db.query(DoctorSchedule).filter(DoctorSchedule.id == appt.schedule_id).first()
        
        result.append({
            "id": str(appt.id),
            "patient_name": patient.name if patient else "Unknown Patient",
            "patient_email": patient.email if patient else "N/A",
            "patient_phone": patient.phone if patient else "N/A",
            "patient_age": patient.age if patient else "N/A",
            "patient_gender": patient.gender if patient else "N/A",
            "symptoms": appt.symptoms or "No symptoms provided",
            "symptom_summary": appt.symptom_summary,
            "date": sched.date.strftime("%Y-%m-%d") if sched else "N/A",
            "start_time": sched.start_time.strftime("%I:%M %p") if sched else "N/A",
            "booking_status": appt.booking_status,
            "status": appt.status or "UPCOMING",
            "doctor_notes": appt.doctor_notes,
            "completed_at": appt.completed_at.isoformat() if appt.completed_at else None,
            "conversation_id": str(appt.conversation_id) if appt.conversation_id else None,
            "created_at": appt.created_at.isoformat()
        })
    return result
