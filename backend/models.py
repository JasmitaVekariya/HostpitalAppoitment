import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Numeric, Date, Time, DateTime, ForeignKey, JSON, Uuid
from sqlalchemy.orm import relationship
from backend.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    phone = Column(String(20), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="patient")  # patient, doctor, admin
    age = Column(Integer, nullable=True)
    gender = Column(String(20), nullable=True)
    preferred_language = Column(String(50), default="English")

    appointments = relationship("Appointment", back_populates="patient", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    doctor_profile = relationship("Doctor", back_populates="user", uselist=False)

class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    floor = Column(Integer, nullable=False)
    description = Column(String(255), nullable=True)

    doctors = relationship("Doctor", back_populates="department")

class Doctor(Base):
    __tablename__ = "doctors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    name = Column(String(100), nullable=False)
    specialization = Column(String(100), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    experience_years = Column(Integer, nullable=False)
    languages = Column(JSON, nullable=False)  # e.g., ["English", "Hindi"]
    consultation_fee = Column(Numeric(10, 2), nullable=False)

    user = relationship("User", back_populates="doctor_profile")
    department = relationship("Department", back_populates="doctors")
    schedules = relationship("DoctorSchedule", back_populates="doctor", cascade="all, delete-orphan")
    appointments = relationship("Appointment", back_populates="doctor", cascade="all, delete-orphan")

class DoctorSchedule(Base):
    __tablename__ = "doctor_schedules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    status = Column(String(20), default="available")  # available, booked, holiday

    doctor = relationship("Doctor", back_populates="schedules")
    appointment = relationship("Appointment", back_populates="schedule", uselist=False)

class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    schedule_id = Column(Integer, ForeignKey("doctor_schedules.id"), nullable=False)
    symptoms = Column(String(500), nullable=True)
    booking_status = Column(String(20), default="confirmed")  # pending, confirmed, cancelled
    status = Column(String(20), default="UPCOMING")  # SCHEDULED, UPCOMING, COMPLETED, MISSED, CANCELLED, RESCHEDULED
    doctor_notes = Column(String(500), nullable=True)
    completed_at = Column(DateTime, nullable=True)
    symptom_summary = Column(String(500), nullable=True)
    conversation_id = Column(Uuid(as_uuid=True), ForeignKey("conversations.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("User", back_populates="appointments")
    doctor = relationship("Doctor", back_populates="appointments")
    schedule = relationship("DoctorSchedule", back_populates="appointment")

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    messages = Column(JSON, default=list)  # list of message dicts
    current_state = Column(JSON, default=dict)  # LangGraph state representation
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="conversations")

class PatientConversation(Base):
    __tablename__ = "patient_conversations"

    conversation_id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    current_symptoms = Column(JSON, default=list)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
