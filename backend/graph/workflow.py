from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from backend.graph.state import HospitalState
from backend.graph.nodes.input import input_node
from backend.graph.nodes.intent import intent_node
from backend.graph.nodes.patient_info import patient_info_node
from backend.graph.nodes.missing_info import missing_info_node
from backend.graph.nodes.symptom import symptom_node
from backend.graph.nodes.medical_decision import medical_decision_node
from backend.graph.nodes.emergency import emergency_node
from backend.graph.nodes.doctor_recommender import doctor_recommender_node
from backend.graph.nodes.schedule import schedule_node
from backend.graph.nodes.booking import booking_node
from backend.graph.nodes.human_review import human_review_node
from backend.graph.nodes.finalize_booking import finalize_booking_node

def route_intent(state: HospitalState) -> str:
    """Decide next node based on classified user intent."""
    intent = state.get("intent")
    status = state.get("booking_status")

    # OFF_TOPIC: reply is already attached to messages by intent_node — exit immediately
    if intent == "OFF_TOPIC":
        return END

    if (
        intent == "BOOK" or
        status in [
            "awaiting_slot_selection", "awaiting_symptoms",
            "emergency_redirect", "no_slots_available", "no_doctors_available"
        ]
    ):
        return "patient_info"

    # GREETING or unrecognised intents — reply already in messages, exit to user
    return END

def route_missing_info(state: HospitalState) -> str:
    """Decide next node based on completeness of patient info."""
    status = state.get("booking_status")

    # ── Topic shift detected → re-run full medical decision pipeline ──────────
    # When the patient changes their medical topic entirely (e.g. was discussing
    # fever, now asks about toothache), force a fresh triage cycle even if a
    # slot selection was already in progress.
    if state.get("topic_shifted"):
        return "symptom"

    if status in [
        "info_complete", "awaiting_symptoms", "emergency_redirect",
        "no_slots_available", "no_doctors_available"
    ]:
        session_id = state.get("session_id")
        if session_id and status == "info_complete":
            import uuid
            from backend.database import SessionLocal
            from backend.models import Appointment

            # Check if the user is explicitly requesting a reschedule or slot choice
            is_rescheduling_query = False
            messages = state.get("messages", [])
            if messages:
                last_msg = messages[-1].content.strip().lower()
                import re
                if (
                    "reschedule" in last_msg or
                    "change" in last_msg or
                    "modify" in last_msg or
                    "timing" in last_msg or
                    "slot" in last_msg or
                    re.search(r"^\d+$", last_msg) or
                    re.search(r"option\s+\d+", last_msg)
                ):
                    is_rescheduling_query = True

            db = SessionLocal()
            try:
                existing_appt = db.query(Appointment).filter(
                    Appointment.conversation_id == uuid.UUID(session_id),
                    Appointment.booking_status == "confirmed"
                ).first()
                if existing_appt and is_rescheduling_query:
                    return "schedule"
            except Exception as e:
                print(f"[DEBUG] Error checking reschedule routing: {e}")
            finally:
                db.close()
        return "symptom"

    elif status == "awaiting_slot_selection":
        # If the patient expresses a date preference (e.g. "give me after 3 Aug",
        # "any slot on Friday"), re-run the schedule_node with the new preference.
        # Only route to booking when a slot number or confirmable date+time is given.
        messages = state.get("messages", [])
        if messages:
            import re
            last_msg = messages[-1].content.strip().lower()
            available_slots = state.get("available_slots", [])

            # Numeric option or confirmed natural language match → go to booking
            has_numeric = bool(re.search(r"\b[123]\b", last_msg))

            # Natural language slot match check (mirrors booking_node logic)
            natural_match = False
            if not has_numeric and available_slots:
                import datetime as _dt
                for slot in available_slots:
                    try:
                        slot_date_obj = _dt.datetime.strptime(slot["date"], "%Y-%m-%d").date()
                        day_variants = [
                            slot_date_obj.strftime("%-d"),
                            slot_date_obj.strftime("%b").lower(),
                            slot_date_obj.strftime("%B").lower(),
                            slot_date_obj.strftime("%A").lower(),
                        ]
                        time_str = slot["start_time"].lower()
                        time_variants = [
                            time_str.replace(" ", ""),
                            time_str.split(":")[0].lstrip("0"),
                        ]
                        date_hit = any(v in last_msg for v in day_variants if v)
                        time_hit = any(v in last_msg for v in time_variants if v)
                        if (date_hit and time_hit) or (date_hit and len(available_slots) == 1):
                            natural_match = True
                            break
                    except Exception:
                        pass

            if has_numeric or natural_match:
                return "booking"

            # Date preference expressed → re-run schedule with new date filter
            date_keywords = [
                "after", "before", "on ", "from ", "morning", "afternoon", "evening",
                "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
                "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
                "next week", "tomorrow", "prefer", "want", "give me", "any slot", "other slot",
                "alternative", "different", "another", "more"
            ]
            if any(kw in last_msg for kw in date_keywords):
                return "schedule"

        return "booking"

    return END

def route_booking(state: HospitalState) -> str:
    """Decide next step based on booking attempt results."""
    status = state.get("booking_status")
    if status == "info_complete":
        # If the user typed a date/time preference instead of a slot number,
        # skip triage and go directly to schedule for a filtered re-query
        import re
        messages = state.get("messages", [])
        date_keywords = [
            "after", "before", "on ", "from ", "morning", "afternoon", "evening",
            "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
            "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
            "next week", "tomorrow", "give me", "any slot", "other slot",
            "alternative", "different", "another", "more"
        ]
        if messages:
            last_msg = messages[-1].content.strip().lower()
            has_numeric = bool(re.search(r"\b[123]\b", last_msg))
            if not has_numeric and any(kw in last_msg for kw in date_keywords):
                return "schedule"
        return "symptom"
    if status == "awaiting_slot_selection":
        return "schedule"
    if status == "appointment_approval_required":
        return "human_review"
    return END

def route_emergency(state: HospitalState) -> str:
    """Decide next step based on triage priority override and HITL."""
    status = state.get("booking_status")
    priority = state.get("priority")
    
    # Route to human review if HITL case triggered
    if status == "emergency_redirect" or priority == "EMERGENCY" or status == "prescription_request":
        return "human_review"
        
    if status == "awaiting_symptoms":
        return END
    return "doctor_recommender"

def route_human_review(state: HospitalState) -> str:
    """Decide next step after human review decision."""
    status = state.get("booking_status")
    if status == "info_complete":
        return "doctor_recommender"
    if status == "appointment_approved":
        return "finalize_booking"
    return END

# Initialize the workflow graph
workflow = StateGraph(HospitalState)

# Add all execution nodes
workflow.add_node("input", input_node)
workflow.add_node("intent", intent_node)
workflow.add_node("patient_info", patient_info_node)
workflow.add_node("missing_info", missing_info_node)
workflow.add_node("symptom", symptom_node)
workflow.add_node("medical_decision", medical_decision_node)
workflow.add_node("emergency", emergency_node)
workflow.add_node("human_review", human_review_node)
workflow.add_node("doctor_recommender", doctor_recommender_node)
workflow.add_node("schedule", schedule_node)
workflow.add_node("booking", booking_node)
workflow.add_node("finalize_booking", finalize_booking_node)

# Configure transitions and edges
workflow.add_edge(START, "input")
workflow.add_edge("input", "intent")

# Conditional routing from Intent Agent
workflow.add_conditional_edges(
    "intent",
    route_intent,
    {
        "patient_info": "patient_info",
        END: END
    }
)

workflow.add_edge("patient_info", "missing_info")

# Conditional routing from Missing Info Checker
workflow.add_conditional_edges(
    "missing_info",
    route_missing_info,
    {
        "symptom": "symptom",
        "booking": "booking",
        "schedule": "schedule",
        END: END
    }
)

workflow.add_edge("schedule", "booking")

# Conditional routing from Booking Confirmation Node
workflow.add_conditional_edges(
    "booking",
    route_booking,
    {
        "symptom": "symptom",
        "schedule": "schedule",
        "human_review": "human_review",
        END: END
    }
)

# Sequential connections for Symptom Triage Flow
workflow.add_edge("symptom", "medical_decision")
workflow.add_edge("medical_decision", "emergency")

# Conditional routing from Emergency Triage Checker
workflow.add_conditional_edges(
    "emergency",
    route_emergency,
    {
        "human_review": "human_review",
        "doctor_recommender": "doctor_recommender",
        END: END
    }
)

workflow.add_conditional_edges(
    "human_review",
    route_human_review,
    {
        "doctor_recommender": "doctor_recommender",
        "finalize_booking": "finalize_booking",
        END: END
    }
)

# finalize_booking naturally goes to END
workflow.add_edge("finalize_booking", END)

# doctor recommender -> schedule optimizer -> END
workflow.add_edge("doctor_recommender", "schedule")
workflow.add_edge("schedule", END)

# Setup state checkpointer memory saver
memory = MemorySaver()

# Compile the final graph execution app
app = workflow.compile(checkpointer=memory)
