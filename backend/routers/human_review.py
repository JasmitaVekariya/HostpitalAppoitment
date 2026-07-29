from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import uuid
from backend.database import get_db
from backend.models import Conversation
from backend.graph.workflow import app as graph_app
from langgraph.types import Command

router = APIRouter(prefix="/api", tags=["Human Review"])

@router.get("/human-review/{review_id}/{decision}")
def submit_human_review(review_id: str, decision: str, db: Session = Depends(get_db)):
    """
    Endpoint for doctors to click from their email.
    Resumes the LangGraph workflow that was interrupted.
    """
    try:
        session_uuid = uuid.UUID(review_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid review ID format.")
        
    conversation = db.query(Conversation).filter(Conversation.id == session_uuid).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Review session not found.")
        
    valid_decisions = ["APPROVE", "REJECT", "EMERGENCY"]
    if decision.upper() not in valid_decisions:
        raise HTTPException(status_code=400, detail=f"Invalid decision. Must be one of {valid_decisions}")
        
    # Configure graph execution context with the session ID as thread_id
    config = {"configurable": {"thread_id": str(session_uuid)}}
    
    try:
        # Resume the graph from interrupt with the doctor's decision
        graph_app.invoke(Command(resume={"decision": decision.upper()}), config)
        
        # After resuming, we should update the conversation state in the DB
        # just like in chat.py
        current_graph_state = graph_app.get_state(config)
        final_state = current_graph_state.values
        
        serialized_messages = []
        for msg in final_state.get("messages", []):
            role = msg.type
            if msg.type == "human":
                role = "user"
            elif msg.type == "ai":
                role = "assistant"
            serialized_messages.append({"role": role, "content": msg.content})

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
            "topic_shifted": final_state.get("topic_shifted", False),
            "review_info": final_state.get("review_info", {})
        }
        db.commit()
        
    except Exception as e:
        print(f"[ERROR] Failed to resume graph: {e}")
        return HTMLResponse(
            content=f"""
            <html><body style="font-family:sans-serif; text-align:center; padding-top:50px;">
                <h1 style="color:#ef4444;">Error processing review</h1>
                <p>Could not resume the patient session. Error: {str(e)}</p>
            </body></html>
            """,
            status_code=500
        )
        
    return HTMLResponse(
        content=f"""
        <html><body style="font-family:sans-serif; text-align:center; padding-top:50px; background:#f0fdf4;">
            <h1 style="color:#16a34a;">Review Submitted Successfully</h1>
            <p>You selected: <strong>{decision.upper()}</strong>.</p>
            <p>The patient has been notified and the automated session has resumed.</p>
        </body></html>
        """
    )
