from typing import Annotated, Sequence, TypedDict, Optional, List, Dict, Any
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

class PatientInfo(TypedDict, total=False):
    name: Optional[str]
    age: Optional[int]
    gender: Optional[str]
    phone: Optional[str]

class SymptomInfo(TypedDict, total=False):
    symptoms: Optional[List[str]]
    duration: Optional[str]
    severity: Optional[str]
    body_part: Optional[str]

class ReviewInfo(TypedDict, total=False):
    review_id: Optional[str]
    review_type: Optional[str] # "HIGH_RISK", "PRESCRIPTION", "MEDICAL_REPORT"
    doctor_email: Optional[str]
    pending_action: Optional[bool]
    review_status: Optional[str] # "PENDING", "APPROVED", "REJECTED", "EMERGENCY"
    doctor_comments: Optional[str]
    timestamp: Optional[str]

class HospitalState(TypedDict):
    # Shared message thread (using add_messages reducer to append new incoming messages)
    messages: Annotated[Sequence[BaseMessage], add_messages]
    
    # Session user reference
    user_id: Optional[str]
    session_id: Optional[str]

    # HITL Review Data
    review_info: Optional[ReviewInfo]
    
    # Inferred conversation language (English, Hindi, Gujarati)
    language: Optional[str]
    
    # Inferred customer intent (BOOK, RESCHEDULE, CANCEL, CHECK_STATUS)
    intent: Optional[str]
    
    # Extracted profile and health data
    patient_info: PatientInfo
    symptoms: SymptomInfo
    
    # Triage and doctor selection data
    department: Optional[str]
    priority: Optional[str]  # LOW, MEDIUM, HIGH, EMERGENCY
    doctor_candidates: List[Dict[str, Any]]
    selected_doctor: Optional[Dict[str, Any]]
    
    # Availability and slot booking details
    available_slots: List[Dict[str, Any]]
    selected_slot: Optional[Dict[str, Any]]
    booking_status: Optional[str]
    topic_shifted: Optional[bool]

    # Patient's expressed date/time scheduling preference (ISO date string & HH:MM time string)
    preferred_date: Optional[str]
    preferred_time: Optional[str]

    # Global tracking arrays
    errors: List[str]
