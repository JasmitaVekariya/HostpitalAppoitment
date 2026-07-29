from typing import Dict, Any, List
from backend.graph.state import HospitalState
from backend.database import SessionLocal
from backend.models import Department, Doctor

def doctor_recommender_node(state: HospitalState) -> Dict[str, Any]:
    """Node to find and rank doctor candidates matching the recommended department and user language."""
    department_name = state.get("department", "General Medicine")
    patient_lang = state.get("language", "English")
    errors = list(state.get("errors", []))
    
    db = SessionLocal()
    candidates = []
    
    try:
        # Find matching department (case-insensitive)
        dept = db.query(Department).filter(Department.name.ilike(department_name)).first()
        if not dept:
            # Fallback to General Medicine
            dept = db.query(Department).filter(Department.name.ilike("General Medicine")).first()
            
        if dept:
            # Query all doctors in that department
            doctors = db.query(Doctor).filter(Doctor.department_id == dept.id).all()
            
            # Python-based language filtering to maintain DB-independent JSON compatibility
            language_matches = []
            for doc in doctors:
                doc_langs = [str(lang).strip().lower() for lang in doc.languages]
                if patient_lang.strip().lower() in doc_langs:
                    language_matches.append(doc)
                    
            # Fallback to all doctors in the department if no language-specific doctors are available
            if not language_matches:
                language_matches = doctors
                
            # Rank doctors: experience_years (descending), then consultation_fee (ascending)
            sorted_docs = sorted(
                language_matches,
                key=lambda d: (-d.experience_years, d.consultation_fee)
            )
            
            # Serialize for state persistence
            for doc in sorted_docs:
                candidates.append({
                    "id": doc.id,
                    "name": doc.name,
                    "specialization": doc.specialization,
                    "consultation_fee": float(doc.consultation_fee),
                    "experience_years": doc.experience_years,
                    "languages": doc.languages
                })
        else:
            errors.append("Hospital department lookup failed.")
            
    except Exception as e:
        print(f"[DEBUG] Doctor recommendation query failed: {e}")
        errors.append(f"Doctor recommendation warning: {e}")
    finally:
        db.close()
        
    # Edge case: No candidates found
    if not candidates:
        errors.append("No doctors available in the recommended department.")
        
    return {
        "doctor_candidates": candidates,
        "errors": errors
    }
