import datetime
import uuid
from typing import Dict, Any, List, Optional, Tuple
from langchain_core.messages import AIMessage
from backend.graph.state import HospitalState
from backend.database import SessionLocal
from backend.models import DoctorSchedule, Appointment, Doctor
from backend.config import settings
from backend.utils.llm import call_openrouter_api, parse_json_markdown


# ─────────────────────────────────────────────────────────────────
# LLM-based date/time preference extractor
# ─────────────────────────────────────────────────────────────────

DATE_EXTRACT_PROMPT = """You are a date/time parser for a hospital booking assistant.
Today's date is {today} ({weekday}).

Analyze the patient's message and extract any scheduling preference they express.

Rules:
- "after 3 Aug" / "from August 3" → preferred_date = "2026-08-03", is_after = true
- "on Aug 5" / "August 5th" → preferred_date = "2026-08-05", is_after = false
- "next Friday" / "this Saturday" → compute the actual calendar date
- "morning" → preferred_time = "09:00"
- "afternoon" → preferred_time = "14:00"
- "evening" → preferred_time = "17:00"
- "10 AM" / "10:00" → preferred_time = "10:00"
- No date expressed → preferred_date = null
- No time expressed → preferred_time = null
- is_after = true means they want slots AFTER that date (exclusive), false means ON that date

Return ONLY a JSON object with these exact fields:
{{
  "preferred_date": "YYYY-MM-DD" | null,
  "preferred_time": "HH:MM" | null,
  "is_after": true | false
}}
"""


def extract_date_preference(
    message: str, today: datetime.date
) -> Tuple[Optional[datetime.date], Optional[datetime.time], bool]:
    """Use LLM to extract a date/time preference from the user message.
    Returns (preferred_date, preferred_time, is_after).
    """
    prompt = DATE_EXTRACT_PROMPT.format(
        today=today.strftime("%Y-%m-%d"),
        weekday=today.strftime("%A")
    )
    try:
        response = call_openrouter_api([
            {"role": "system", "content": prompt},
            {"role": "user", "content": message}
        ])
        result = parse_json_markdown(response)
        print(f"[DEBUG] Date preference extracted: {result}")

        pref_date = None
        pref_time = None
        is_after = bool(result.get("is_after", False))

        raw_date = result.get("preferred_date")
        if raw_date:
            try:
                pref_date = datetime.datetime.strptime(raw_date, "%Y-%m-%d").date()
            except ValueError:
                pass

        raw_time = result.get("preferred_time")
        if raw_time:
            try:
                pref_time = datetime.datetime.strptime(raw_time, "%H:%M").time()
            except ValueError:
                pass

        return pref_date, pref_time, is_after

    except Exception as e:
        print(f"[DEBUG] Date extraction failed: {e}")
        return None, None, False


# ─────────────────────────────────────────────────────────────────
# Keywords that signal the user is expressing a date/time preference
# ─────────────────────────────────────────────────────────────────

DATE_PREFERENCE_KEYWORDS = [
    "after", "before", "on ", "from ", "morning", "afternoon", "evening",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
    "next week", "this week", "tomorrow", "day after", "am", "pm",
    "give me", "prefer", "want", "need", "book on", "schedule on", "earliest after"
]

ALTERNATIVE_KEYWORDS = [
    "other slot", "alternative", "different time", "next slot", "more slot",
    "any other", "another slot", "change time", "else", "show more", "other options"
]


def _has_date_preference(message: str) -> bool:
    msg_lower = message.lower()
    return any(kw in msg_lower for kw in DATE_PREFERENCE_KEYWORDS)


def _is_asking_alternative(message: str) -> bool:
    msg_lower = message.lower()
    return any(kw in msg_lower for kw in ALTERNATIVE_KEYWORDS)


# ─────────────────────────────────────────────────────────────────
# Main schedule node
# ─────────────────────────────────────────────────────────────────

def schedule_node(state: HospitalState) -> Dict[str, Any]:
    """Node to find, optimize, and present available slots for the recommended doctor.
    
    Supports:
    - Natural language date/time preferences ("after 3 Aug", "Friday morning", "10 AM on Aug 5")
    - Direct exact slot matching when a specific date+time is given
    - Pagination to next slots when user asks for alternatives
    - Falls back to earliest 3 slots when no preference is expressed
    """
    candidates = state.get("doctor_candidates", [])
    errors = list(state.get("errors", []))
    session_id = state.get("session_id")
    today = datetime.date.today()

    # ── If rescheduling an existing appointment, force candidates to that doctor ──
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

    # ── Parse the last user message ──
    user_messages = [m for m in state.get("messages", []) if m.type == "human"]
    last_user_msg = user_messages[-1].content.strip() if user_messages else ""
    last_user_lower = last_user_msg.lower()

    is_alternative = _is_asking_alternative(last_user_lower)
    has_preference = _has_date_preference(last_user_lower)

    # ── Extract date/time preference via LLM when user expresses one ──
    pref_date: Optional[datetime.date] = None
    pref_time: Optional[datetime.time] = None
    is_after = False

    # Restore from previous state if user didn't change preference this turn
    prev_pref_date = state.get("preferred_date")
    prev_pref_time = state.get("preferred_time")

    if has_preference and not is_alternative:
        pref_date, pref_time, is_after = extract_date_preference(last_user_msg, today)
    elif is_alternative:
        # Keep existing preference for pagination
        if prev_pref_date:
            try:
                pref_date = datetime.datetime.strptime(prev_pref_date, "%Y-%m-%d").date()
            except ValueError:
                pass
        if prev_pref_time:
            try:
                pref_time = datetime.datetime.strptime(prev_pref_time, "%H:%M").time()
            except ValueError:
                pass

    # ── Pagination anchor for "alternatives" requests ──
    prev_slots = state.get("available_slots", [])
    pagination_date = today
    pagination_time = datetime.time(0, 0)
    if is_alternative and prev_slots:
        try:
            last_slot = prev_slots[-1]
            pagination_date = datetime.datetime.strptime(last_slot["date"], "%Y-%m-%d").date()
            pagination_time = datetime.datetime.strptime(last_slot["start_time"], "%I:%M %p").time()
        except Exception as e:
            print(f"[DEBUG] Error parsing previous slots for pagination: {e}")

    # ── Query the database ──
    db = SessionLocal()
    selected_doctor = state.get("selected_doctor")
    available_slots = []
    max_days = today + datetime.timedelta(days=60)
    now = datetime.datetime.now()
    booking_buffer = getattr(settings, "BOOKING_BUFFER_MINUTES", 120)
    boundary_datetime = now + datetime.timedelta(minutes=booking_buffer)
    exact_match_slot = None  # for specific date+time requests

    try:
        doctors_to_check = [selected_doctor] if (selected_doctor and is_alternative) else candidates

        for doc in doctors_to_check:
            doc_id = doc["id"]

            query = db.query(DoctorSchedule).filter(
                DoctorSchedule.doctor_id == doc_id,
                DoctorSchedule.status == "available",
                DoctorSchedule.date <= max_days
            )

            # ── Apply date filter based on preference ──
            if is_alternative:
                # Paginate past previously shown slots
                query = query.filter(
                    (DoctorSchedule.date > pagination_date) |
                    ((DoctorSchedule.date == pagination_date) & (DoctorSchedule.start_time > pagination_time))
                )
            elif pref_date and is_after:
                # "after Aug 3" — slots strictly after that date
                query = query.filter(DoctorSchedule.date > pref_date)
            elif pref_date and pref_time:
                # Specific date + time — attempt exact match first
                query = query.filter(DoctorSchedule.date == pref_date)
            elif pref_date:
                # "on Aug 5" — only that date
                query = query.filter(DoctorSchedule.date == pref_date)
            elif pref_time:
                # Only a time preference — filter by time of day on any future date
                query = query.filter(
                    DoctorSchedule.date >= today,
                    DoctorSchedule.start_time >= pref_time
                )
            else:
                # No preference — earliest available
                query = query.filter(DoctorSchedule.date >= today)

            slots = query.order_by(
                DoctorSchedule.date, DoctorSchedule.start_time
            ).all()

            # Apply booking buffer
            filtered_slots = [
                s for s in slots
                if datetime.datetime.combine(s.date, s.start_time) >= boundary_datetime
            ]

            # ── Check for exact date+time match ──
            if pref_date and pref_time and not is_after and filtered_slots:
                for s in filtered_slots:
                    if s.date == pref_date and s.start_time.hour == pref_time.hour and s.start_time.minute == pref_time.minute:
                        exact_match_slot = s
                        selected_doctor = doc
                        break

            # Pick top 3 for display
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

            # If user asked for a specific date but it has no available slots,
            # check if that date has any slots at all (booked) to give better message
            elif pref_date and not is_after:
                booked_on_date = db.query(DoctorSchedule).filter(
                    DoctorSchedule.doctor_id == doc_id,
                    DoctorSchedule.date == pref_date
                ).count()
                if booked_on_date > 0:
                    # Slots exist but all booked — show next available from that date
                    fallback = db.query(DoctorSchedule).filter(
                        DoctorSchedule.doctor_id == doc_id,
                        DoctorSchedule.status == "available",
                        DoctorSchedule.date > pref_date,
                        DoctorSchedule.date <= max_days
                    ).order_by(DoctorSchedule.date, DoctorSchedule.start_time).all()

                    fallback_filtered = [
                        s for s in fallback
                        if datetime.datetime.combine(s.date, s.start_time) >= boundary_datetime
                    ]
                    if fallback_filtered[:3]:
                        selected_doctor = doc
                        for s in fallback_filtered[:3]:
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

    # ── Handle exact date+time match (direct booking offer) ──
    if exact_match_slot:
        date_str = exact_match_slot.date.strftime("%A, %B %d, %Y")
        time_str = exact_match_slot.start_time.strftime("%I:%M %p")
        exact_slot_data = {
            "id": exact_match_slot.id,
            "date": exact_match_slot.date.isoformat(),
            "day": exact_match_slot.date.strftime("%A"),
            "start_time": exact_match_slot.start_time.strftime("%I:%M %p"),
            "end_time": exact_match_slot.end_time.strftime("%I:%M %p")
        }
        direct_msg = (
            f"✅ Great news! The slot you requested is available:\n\n"
            f"**{date_str} at {time_str}** with {selected_doctor['name']} ({selected_doctor['specialization']})\n\n"
            f"Reply **1** to confirm this appointment."
        )
        return {
            "selected_doctor": selected_doctor,
            "available_slots": [exact_slot_data],
            "booking_status": "awaiting_slot_selection",
            "preferred_date": pref_date.isoformat() if pref_date else state.get("preferred_date"),
            "preferred_time": pref_time.strftime("%H:%M") if pref_time else state.get("preferred_time"),
            "messages": [AIMessage(content=direct_msg)],
            "errors": errors
        }

    # ── No slots found at all ──
    if not selected_doctor or not available_slots:
        if pref_date:
            date_label = pref_date.strftime("%B %d, %Y")
            no_slot_msg = (
                f"I'm sorry, there are no available slots "
                f"{'after' if is_after else 'on'} {date_label} within the next 60 days. "
                f"Would you like me to show you the earliest available appointments instead?"
            )
        else:
            no_slot_msg = "All doctors in the department are currently fully booked for the next 60 days."
        return {
            "booking_status": "no_slots_available",
            "messages": [AIMessage(content=no_slot_msg)],
            "preferred_date": pref_date.isoformat() if pref_date else None,
            "preferred_time": pref_time.strftime("%H:%M") if pref_time else None,
            "errors": errors
        }

    # ── Build slot list text ──
    slots_text = "\n".join([
        f"{idx + 1}. {datetime.datetime.strptime(s['date'], '%Y-%m-%d').strftime('%A, %B %d, %Y')} at {s['start_time']}"
        for idx, s in enumerate(available_slots)
    ])

    symptom_list = state.get("symptoms", {}).get("symptoms", [])
    symptoms_str = ", ".join(symptom_list) if symptom_list else "general health concerns"

    # ── Build the preference context string for the LLM ──
    preference_note = ""
    if pref_date and is_after:
        preference_note = f"The patient requested slots after {pref_date.strftime('%B %d, %Y')}. "
    elif pref_date and pref_time:
        preference_note = f"The patient requested {pref_date.strftime('%B %d')} at {pref_time.strftime('%I:%M %p')} — this is the closest available option. "
    elif pref_date:
        preference_note = f"The patient requested slots on {pref_date.strftime('%B %d, %Y')}. "
    elif pref_time:
        preference_note = f"The patient prefers {pref_time.strftime('%I:%M %p')} time slots. "
    elif is_alternative:
        preference_note = "The patient asked for alternative slots beyond what was previously shown. "

    schedule_prompt = (
        f"You are a warm, empathetic medical receptionist at Sunrise Multispeciality Hospital.\n"
        f"Your task is to draft a natural, conversational response recommending {selected_doctor['name']} "
        f"({selected_doctor['specialization']}) and presenting the available appointment slots below.\n\n"
        f"Doctor: {selected_doctor['name']} ({selected_doctor['specialization']})\n"
        f"Consultation Fee: ₹{selected_doctor['consultation_fee']:.0f}\n"
        f"Symptoms: {symptoms_str}\n"
        f"{preference_note}\n"
        f"Available Slots:\n{slots_text}\n\n"
        f"Write a concise, warm message presenting these slots. "
        f"If a date preference was requested, acknowledge it. "
        f"Clearly instruct the patient to reply with the slot number (1, 2, or 3) to confirm their booking. "
        f"Do not use robotic phrases. Keep it under 6 sentences."
    )

    try:
        api_messages = []
        for msg in state.get("messages", []):
            role = "user" if msg.type == "human" else ("assistant" if msg.type == "ai" else msg.type)
            api_messages.append({"role": role, "content": msg.content})
        api_messages.append({"role": "system", "content": schedule_prompt})
        ai_response = call_openrouter_api(api_messages)
    except Exception as e:
        print(f"[DEBUG] Failed to generate LLM schedule response: {e}")
        ai_response = (
            f"Based on your symptoms ({symptoms_str}), I recommend {selected_doctor['name']} "
            f"({selected_doctor['specialization']}).\n\n"
            f"Here are the available slots{' from your requested date' if pref_date else ''}:\n{slots_text}\n\n"
            f"Please reply with the slot number (1, 2, or 3) to confirm your booking."
        )

    return {
        "selected_doctor": selected_doctor,
        "available_slots": available_slots,
        "booking_status": "awaiting_slot_selection",
        "preferred_date": pref_date.isoformat() if pref_date else state.get("preferred_date"),
        "preferred_time": pref_time.strftime("%H:%M") if pref_time else state.get("preferred_time"),
        "messages": [AIMessage(content=ai_response)],
        "errors": errors
    }
