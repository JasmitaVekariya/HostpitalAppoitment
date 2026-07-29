from typing import Dict, Any, List
from langchain_core.messages import AIMessage
from backend.graph.state import HospitalState
from backend.utils.llm import call_openrouter_api

# Valid age range
AGE_MIN = 0
AGE_MAX = 120


def _invalid_age(age) -> bool:
    """Returns True if age is present but out of acceptable range."""
    if age is None:
        return False
    try:
        a = int(age)
        return a < AGE_MIN or a > AGE_MAX
    except (TypeError, ValueError):
        return True


def missing_info_node(state: HospitalState) -> Dict[str, Any]:
    """Node to check for missing or invalid profile details (name, age, gender) and request them."""
    patient_info = state.get("patient_info", {})
    errors = list(state.get("errors", []))

    missing_fields: List[str] = []
    validation_issues: List[str] = []

    # ── Mandatory fields ──────────────────────────────────────────────────────
    if not patient_info.get("name"):
        missing_fields.append("your full name")

    age = patient_info.get("age")
    if age is None:
        missing_fields.append("your age")
    elif _invalid_age(age):
        # Age is present but invalid — special message
        validation_issues.append(f"invalid_age:{age}")

    # ── Optional but useful field ─────────────────────────────────────────────
    gender = patient_info.get("gender")
    if not gender or str(gender).strip() in ["", "None", "null", "Unknown"]:
        missing_fields.append("your gender (Male / Female / Other — this helps us recommend the right specialist)")

    # ── Handle invalid age first ──────────────────────────────────────────────
    if validation_issues:
        bad_age = str(age)
        prompt = (
            f"The patient entered an age of '{bad_age}', which is not a valid human age. "
            f"Please ask them politely to provide a correct age between 0 and 120 years. "
            f"Keep the tone friendly and short (1 sentence)."
        )
        try:
            response_content = call_openrouter_api([
                {"role": "system", "content": "You are a helpful medical receptionist at Sunrise Multispeciality Hospital."},
                {"role": "user", "content": prompt}
            ])
            ai_message = AIMessage(content=response_content)
        except Exception as e:
            ai_message = AIMessage(
                content=f"The age '{bad_age}' doesn't look right — could you please provide your correct age in years?"
            )
            errors.append(f"Age validation prompt warning: {e}")

        return {
            "messages": [ai_message],
            "booking_status": "awaiting_info",
            "errors": errors
        }

    # ── If all fields are present and valid → proceed ─────────────────────────
    if not missing_fields:
        current_status = state.get("booking_status")
        if current_status in ["awaiting_slot_selection", "emergency_redirect"]:
            return {}  # Preserve the existing scheduling status
        return {
            "booking_status": "info_complete"
        }

    # ── Request only the missing fields ───────────────────────────────────────
    fields_str = " and ".join(missing_fields)

    prompt = (
        f"The patient is trying to book an appointment but has not provided the following details: {fields_str}. "
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
        ai_message = AIMessage(content=f"To proceed with scheduling, could you please tell me {fields_str}?")
        errors.append(f"Missing info prompt generation warning: {e}")

    return {
        "messages": [ai_message],
        "booking_status": "awaiting_info",
        "errors": errors
    }
