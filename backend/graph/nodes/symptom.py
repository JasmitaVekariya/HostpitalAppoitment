import datetime
import uuid
from typing import Dict, Any, List
from langchain_core.messages import AIMessage
from backend.graph.state import HospitalState, SymptomInfo
from backend.utils.llm import call_openrouter_api, parse_json_markdown
from backend.database import SessionLocal
from backend.models import PatientConversation

SYMPTOM_AGENT_SYSTEM_PROMPT = """You are the Symptom Extraction and Aggregation Agent for Sunrise Multispeciality Hospital.
Your task is to analyze the patient's latest message in the context of the conversation and their existing list of accumulated symptoms, and output an updated, aggregated, and normalized list of symptoms.

Rules:
1. Accumulate symptoms: If the patient mentions new symptoms, add them to the existing list of symptoms.
2. Detect topic shift: If the patient starts discussing a completely different medical issue (e.g. they were discussing fever/cold, but now they are talking about a toothache or back pain), discard the previous symptoms and start a new list. Set "topic_shifted" to true.
3. Normalize wording: Normalize symptoms to simple, medical-standard lower-case terms. Examples:
   - "High fever", "burning body", or "running temperature" -> "fever"
   - "Running nose" or "stuffy nose" -> "runny nose"
   - "Throat hurts" or "pain in throat" -> "sore throat"
   - "Aching head" -> "headache"
4. Avoid duplicates: Ensure the symptom list contains only unique, normalized symptoms.
5. Extract duration, severity, and body part if mentioned in the new message or keep the existing ones if still relevant.

Existing symptoms: {existing_symptoms}

Return your response strictly as a JSON object with the following fields:
{{
  "symptoms": ["symptom1", "symptom2"],
  "duration": "duration_str" | null,
  "severity": "mild" | "moderate" | "severe",
  "body_part": "body_part_str" | null,
  "topic_shifted": true | false
}}

Do not include any conversational text, explanations, or text outside the JSON block.
"""

def symptom_node(state: HospitalState) -> Dict[str, Any]:
    """Node to extract, aggregate, and normalize symptoms and complaints from the conversation history."""
    messages = state.get("messages", [])
    errors = list(state.get("errors", []))
    session_id = state.get("session_id")
    
    # 1. Retrieve previous symptoms from PatientConversation table
    existing_symptoms = []
    db = SessionLocal()
    session_uuid = None
    patient_conv = None
    if session_id:
        try:
            session_uuid = uuid.UUID(session_id)
            patient_conv = db.query(PatientConversation).filter(
                PatientConversation.conversation_id == session_uuid
            ).first()
            if patient_conv and patient_conv.current_symptoms:
                existing_symptoms = patient_conv.current_symptoms
        except Exception as e:
            print(f"[DEBUG] Error reading PatientConversation: {e}")
            errors.append(f"Conversation memory load warning: {e}")

    # Build prompt dynamically with existing symptoms
    prompt_str = SYMPTOM_AGENT_SYSTEM_PROMPT.format(existing_symptoms=str(existing_symptoms))
    
    symptom_data = {
        "symptoms": existing_symptoms,
        "duration": None,
        "severity": "moderate",
        "body_part": None
    }
    
    # 2. Call LLM to extract & aggregate
    try:
        # Construct context message list for LLM call
        api_messages = [{"role": "system", "content": prompt_str}]
        for msg in messages:
            role = "user" if msg.type == "human" else ("assistant" if msg.type == "ai" else msg.type)
            api_messages.append({"role": role, "content": msg.content})
            
        response_content = call_openrouter_api(api_messages)
        result_dict = parse_json_markdown(response_content)
        print(f"[DEBUG] Symptom extraction LLM parsed result: {result_dict}")
        
        extracted_symptoms = result_dict.get("symptoms", [])
        extracted_duration = result_dict.get("duration")
        extracted_severity = result_dict.get("severity", "moderate")
        extracted_body_part = result_dict.get("body_part")
        
        # Determine updated symptoms list
        updated_symptoms = []
        if isinstance(extracted_symptoms, list):
            updated_symptoms = [str(s).strip().lower() for s in extracted_symptoms]
        elif extracted_symptoms:
            updated_symptoms = [str(extracted_symptoms).strip().lower()]
            
        symptom_data["symptoms"] = updated_symptoms
        if extracted_duration:
            symptom_data["duration"] = str(extracted_duration).strip()
        if extracted_severity:
            symptom_data["severity"] = str(extracted_severity).strip().lower()
        if extracted_body_part:
            symptom_data["body_part"] = str(extracted_body_part).strip()
            
    except Exception as e:
        print(f"[DEBUG] Symptom extraction failed with error: {e}")
        errors.append(f"Symptom extraction warning: {e}")
        # Keep existing list as fallback
        if "symptoms" not in symptom_data:
            symptom_data["symptoms"] = existing_symptoms

    # 3. Save the aggregated symptoms list to database
    if session_uuid:
        try:
            if not patient_conv:
                patient_conv = PatientConversation(
                    conversation_id=session_uuid,
                    current_symptoms=symptom_data["symptoms"]
                )
                db.add(patient_conv)
            else:
                patient_conv.current_symptoms = symptom_data["symptoms"]
                patient_conv.last_updated = datetime.datetime.utcnow()
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"[DEBUG] Failed to save PatientConversation: {e}")
            errors.append(f"Conversation memory save warning: {e}")
        finally:
            db.close()
    else:
        db.close()

    # 4. Check if we have symptoms. If empty, ask the patient empathetically.
    if not symptom_data["symptoms"]:
        # Generate empathetic symptom request message via LLM
        prompt = (
            "The patient wants to book an appointment but has not described any symptoms or health concerns yet. "
            "Write a warm, caring, and professional response asking them to describe what symptoms they are experiencing "
            "so that we can recommend the appropriate medical department and doctor. Keep it short (1-2 sentences)."
        )
        try:
            response_content = call_openrouter_api([
                {"role": "system", "content": "You are a warm, professional medical assistant at Sunrise Multispeciality Hospital."},
                {"role": "user", "content": prompt}
            ])
            ai_message = AIMessage(content=response_content)
        except Exception as e:
            ai_message = AIMessage(content="Could you please describe the symptoms or health concerns you're experiencing today so I can guide you to the right specialist?")
            errors.append(f"Empathetic symptom request prompt warning: {e}")
            
        return {
            "symptoms": symptom_data,
            "booking_status": "awaiting_symptoms",
            "messages": [ai_message],
            "errors": errors
        }
        
    return {
        "symptoms": symptom_data,
        "booking_status": "info_complete",
        "errors": errors
    }
