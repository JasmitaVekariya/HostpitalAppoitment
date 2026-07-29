from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class ChatRequest(BaseModel):
    session_id: str
    message: str

class MessageDict(BaseModel):
    role: str
    content: str

class ChatResponse(BaseModel):
    session_id: str
    messages: List[MessageDict]
    patient_info: Dict[str, Any]
    booking_status: Optional[str]
    department: Optional[str] = None
    priority: Optional[str] = None
    doctor_candidates: Optional[List[Dict[str, Any]]] = None
    selected_doctor: Optional[Dict[str, Any]] = None
    available_slots: Optional[List[Dict[str, Any]]] = None
