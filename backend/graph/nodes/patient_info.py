from typing import Dict, Any
from backend.graph.state import HospitalState
from backend.database import SessionLocal
from backend.models import User

def patient_info_node(state: HospitalState) -> Dict[str, Any]:
    """Node to fetch patient profile details directly from the database and prevent LLM modification."""
    user_id = state.get("user_id")
    patient_data = {
        "name": "",
        "age": None,
        "gender": "",
        "phone": ""
    }
    errors = list(state.get("errors", []))

    if user_id:
        db = SessionLocal()
        try:
            # Query the authenticated user details directly from the database
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                patient_data["name"] = user.name
                patient_data["age"] = user.age
                patient_data["gender"] = user.gender
                patient_data["phone"] = user.phone
        except Exception as e:
            errors.append(f"Profile retrieval error: {e}")
        finally:
            db.close()

    return {
        "patient_info": patient_data,
        "errors": errors
    }
