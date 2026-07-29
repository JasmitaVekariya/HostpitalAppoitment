from typing import Dict, Any
from backend.graph.state import HospitalState
from backend.utils.llm import call_openrouter_api, parse_json_markdown
from backend.prompts.medical_decision import MEDICAL_DECISION_AGENT_SYSTEM_PROMPT

SUPPORTED_DEPARTMENTS = [
    "General Medicine", "Cardiology", "Orthopedics", "Neurology", 
    "Pediatrics", "Dermatology", "ENT", "Gynecology", "Ophthalmology", "Dentistry"
]

SUPPORTED_PRIORITIES = ["LOW", "MEDIUM", "HIGH", "EMERGENCY"]

def medical_decision_node(state: HospitalState) -> Dict[str, Any]:
    """Node to classify department and prioritize patient care based on symptoms."""
    symptoms = state.get("symptoms", {})
    patient_info = state.get("patient_info", {})
    errors = list(state.get("errors", []))
    
    age = patient_info.get("age")
    gender = patient_info.get("gender")
    
    # Construct prompt inputs
    user_context = (
        f"Patient Profile:\n"
        f"- Age: {age if age is not None else 'Unknown'}\n"
        f"- Gender: {gender if gender else 'Unknown'}\n\n"
        f"Extracted Symptoms:\n"
        f"- Symptoms: {symptoms.get('symptoms', [])}\n"
        f"- Duration: {symptoms.get('duration', 'Unknown')}\n"
        f"- Severity: {symptoms.get('severity', 'Unknown')}\n"
        f"- Body Part: {symptoms.get('body_part', 'Unknown')}"
    )
    
    # Call OpenRouter API
    try:
        response_content = call_openrouter_api([
            {"role": "system", "content": MEDICAL_DECISION_AGENT_SYSTEM_PROMPT},
            {"role": "user", "content": user_context}
        ])
        
        result_dict = parse_json_markdown(response_content)
        print(f"[DEBUG] Medical decision triage LLM parsed result: {result_dict}")
        
        recommended_dept = str(result_dict.get("department", "General Medicine")).strip()
        priority_val = str(result_dict.get("priority", "LOW")).strip().upper()
        
        # Code-level Safety Guardrail: Force EMERGENCY priority for critical clinical keywords
        user_context_lower = user_context.lower()
        emergency_triggers = [
            "chest pain", "cannot breathe", "can't breathe", "shortness of breath",
            "slurred speech", "facial drooping", "heavy bleeding", "massive bleeding",
            "unconscious", "heart attack", "stroke"
        ]
        for trigger in emergency_triggers:
            if trigger in user_context_lower:
                priority_val = "EMERGENCY"
                break
        
        # Guardrail: Normalize department matching with robust prefix and synonym matching
        matched_dept = "General Medicine"
        rec_dept_lower = recommended_dept.lower()
        if "cardio" in rec_dept_lower or "heart" in rec_dept_lower:
            matched_dept = "Cardiology"
        elif "ortho" in rec_dept_lower or "bone" in rec_dept_lower or "joint" in rec_dept_lower or "fracture" in rec_dept_lower or "back pain" in rec_dept_lower or "neck pain" in rec_dept_lower:
            matched_dept = "Orthopedics"
        elif "neuro" in rec_dept_lower or "brain" in rec_dept_lower or "nerve" in rec_dept_lower:
            matched_dept = "Neurology"
        elif "pedia" in rec_dept_lower or "child" in rec_dept_lower or "infant" in rec_dept_lower:
            matched_dept = "Pediatrics"
        elif "derma" in rec_dept_lower or "skin" in rec_dept_lower or "rash" in rec_dept_lower:
            matched_dept = "Dermatology"
        elif "ent" in rec_dept_lower or "ear" in rec_dept_lower or "nose" in rec_dept_lower or "throat" in rec_dept_lower:
            matched_dept = "ENT"
        elif "gyn" in rec_dept_lower or "women" in rec_dept_lower or "preg" in rec_dept_lower:
            matched_dept = "Gynecology"
        elif "ophthal" in rec_dept_lower or "eye" in rec_dept_lower or "vision" in rec_dept_lower:
            matched_dept = "Ophthalmology"
        elif "dent" in rec_dept_lower or "tooth" in rec_dept_lower or "teeth" in rec_dept_lower or "gum" in rec_dept_lower:
            matched_dept = "Dentistry"
        else:
            for dept in SUPPORTED_DEPARTMENTS:
                if dept.lower() in rec_dept_lower or rec_dept_lower in dept.lower():
                    matched_dept = dept
                    break
                
        # Guardrail: Force Pediatrics if age < 18 and a general department was assigned
        if age is not None and age < 18 and matched_dept == "General Medicine":
            matched_dept = "Pediatrics"
            
        # Guardrail: Force Gynecology validation
        if matched_dept == "Gynecology" and gender != "Female":
            # Demote to General Medicine if gender is Male/Other
            matched_dept = "General Medicine"
            
        if priority_val not in SUPPORTED_PRIORITIES:
            priority_val = "LOW"
            
        # Detect prescription requests for HITL
        prescription_triggers = [
            "antibiotic", "steroid", "prescribe", "prescription", "medicine for"
        ]
        booking_status = state.get("booking_status")
        for trigger in prescription_triggers:
            if trigger in user_context_lower:
                booking_status = "prescription_request"
                break
            
        return {
            "department": matched_dept,
            "priority": priority_val,
            "booking_status": booking_status,
            "errors": errors
        }
        
    except Exception as e:
        print(f"[DEBUG] Medical decision triage failed with error: {e}")
        errors.append(f"Medical decision triage warning: {e}")
        
        # Fallback defaults
        fallback_dept = "General Medicine"
        if age is not None and age < 18:
            fallback_dept = "Pediatrics"
            
        return {
            "department": fallback_dept,
            "priority": "LOW",
            "errors": errors
        }
