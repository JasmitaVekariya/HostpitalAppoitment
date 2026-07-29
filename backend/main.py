from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.config import settings
from backend.database import engine, Base
# Import all models to ensure they are registered on the declarative Base metadata
from backend.models import User, Department, Doctor, DoctorSchedule, Appointment, Conversation, PatientConversation

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Automatically create database tables if they do not exist
    Base.metadata.create_all(bind=engine)
    
    # Run dynamic schema migrations to add columns to appointments if they are missing
    from sqlalchemy import inspect, text
    try:
        inspector = inspect(engine)
        columns = [col["name"] for col in inspector.get_columns("appointments")]
        
        with engine.begin() as conn:
            if "status" not in columns:
                conn.execute(text("ALTER TABLE appointments ADD COLUMN status VARCHAR(20) DEFAULT 'UPCOMING';"))
            if "doctor_notes" not in columns:
                conn.execute(text("ALTER TABLE appointments ADD COLUMN doctor_notes VARCHAR(500);"))
            if "completed_at" not in columns:
                conn.execute(text("ALTER TABLE appointments ADD COLUMN completed_at TIMESTAMP;"))
            if "symptom_summary" not in columns:
                conn.execute(text("ALTER TABLE appointments ADD COLUMN symptom_summary VARCHAR(500);"))
        print("[DATABASE] Dynamic schema check/migrations applied successfully.")
    except Exception as e:
        print(f"[DATABASE] Schema check warning: {e}")
        
    yield

from backend.routers.auth import router as auth_router
from backend.routers.chat import router as chat_router
from backend.routers.human_review import router as human_review_router

app = FastAPI(
    title="AI Hospital Appointment Orchestrator",
    description="Backend API for managing hospital appointments using LangGraph",
    version="1.0.0",
    lifespan=lifespan
)

# Include Routers
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(human_review_router)

# CORS configuration to allow local frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "app": "AI Hospital Appointment Orchestrator",
        "database_configured": bool(settings.DATABASE_URL)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
