import os
import sys
import uuid
import ssl
from datetime import datetime, date, time, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session

# Add the project root to sys.path so we can import backend modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.database import SessionLocal, Base, engine
from backend.models import User, Department, Doctor, DoctorSchedule
from backend.utils.security import hash_password

DEPARTMENTS = [
    {"name": "General Medicine", "floor": 1, "description": "Fever, cold, infections, general illness"},
    {"name": "Cardiology", "floor": 2, "description": "Heart-related diseases"},
    {"name": "Orthopedics", "floor": 2, "description": "Bones, joints, fractures"},
    {"name": "Neurology", "floor": 3, "description": "Brain and nervous system"},
    {"name": "Pediatrics", "floor": 3, "description": "Child healthcare"},
    {"name": "Dermatology", "floor": 4, "description": "Skin, hair, nails"},
    {"name": "ENT", "floor": 4, "description": "Ear, Nose & Throat"},
    {"name": "Gynecology", "floor": 5, "description": "Women’s healthcare"},
    {"name": "Ophthalmology", "floor": 5, "description": "Eye care"},
    {"name": "Dentistry", "floor": 0, "description": "Dental care"}  # 'Ground' represented as floor 0
]

DOCTORS = [
    {
        "name": "Dr. Rahul Shah",
        "department": "General Medicine",
        "specialization": "General Physician",
        "experience": 12,
        "languages": ["English", "Hindi", "Gujarati"],
        "fee": Decimal("15.00"),
        "working_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        "start_time": time(9, 0),
        "end_time": time(16, 0),
        "email": "rahul.shah@sunrisehospital.com",
        "phone": "+919000000001",
        "gender": "Male",
        "age": 42
    },
    {
        "name": "Dr. Priya Mehta",
        "department": "Cardiology",
        "specialization": "Cardiologist",
        "experience": 15,
        "languages": ["English", "Hindi"],
        "fee": Decimal("30.00"),
        "working_days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
        "start_time": time(10, 0),
        "end_time": time(17, 0),
        "email": "priya.mehta@sunrisehospital.com",
        "phone": "+919000000002",
        "gender": "Female",
        "age": 45
    },
    {
        "name": "Dr. Amit Patel",
        "department": "Orthopedics",
        "specialization": "Orthopedic Surgeon",
        "experience": 10,
        "languages": ["English", "Gujarati"],
        "fee": Decimal("20.00"),
        "working_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        "start_time": time(9, 0),
        "end_time": time(15, 0),
        "email": "amit.patel@sunrisehospital.com",
        "phone": "+919000000003",
        "gender": "Male",
        "age": 39
    },
    {
        "name": "Dr. Neha Desai",
        "department": "Pediatrics",
        "specialization": "Pediatrician",
        "experience": 9,
        "languages": ["English", "Hindi", "Gujarati"],
        "fee": Decimal("18.00"),
        "working_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        "start_time": time(10, 0),
        "end_time": time(18, 0),
        "email": "neha.desai@sunrisehospital.com",
        "phone": "+919000000004",
        "gender": "Female",
        "age": 37
    },
    {
        "name": "Dr. Kunal Joshi",
        "department": "Neurology",
        "specialization": "Neurologist",
        "experience": 14,
        "languages": ["English", "Hindi"],
        "fee": Decimal("35.00"),
        "working_days": ["Tue", "Wed", "Thu", "Fri", "Sat"],
        "start_time": time(11, 0),
        "end_time": time(17, 0),
        "email": "kunal.joshi@sunrisehospital.com",
        "phone": "+919000000005",
        "gender": "Male",
        "age": 44
    },
    {
        "name": "Dr. Riya Shah",
        "department": "Dermatology",
        "specialization": "Dermatologist",
        "experience": 8,
        "languages": ["English", "Gujarati"],
        "fee": Decimal("18.00"),
        "working_days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
        "start_time": time(9, 0),
        "end_time": time(14, 0),
        "email": "riya.shah@sunrisehospital.com",
        "phone": "+919000000006",
        "gender": "Female",
        "age": 35
    },
    {
        "name": "Dr. Harsh Trivedi",
        "department": "ENT",
        "specialization": "ENT Specialist",
        "experience": 11,
        "languages": ["English", "Hindi"],
        "fee": Decimal("18.00"),
        "working_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        "start_time": time(13, 0),
        "end_time": time(19, 0),
        "email": "harsh.trivedi@sunrisehospital.com",
        "phone": "+919000000007",
        "gender": "Male",
        "age": 40
    },
    {
        "name": "Dr. Anjali Patel",
        "department": "Gynecology",
        "specialization": "Gynecologist",
        "experience": 13,
        "languages": ["English", "Hindi", "Gujarati"],
        "fee": Decimal("25.00"),
        "working_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        "start_time": time(10, 0),
        "end_time": time(16, 0),
        "email": "anjali.patel@sunrisehospital.com",
        "phone": "+919000000008",
        "gender": "Female",
        "age": 41
    },
    {
        "name": "Dr. Vivek Modi",
        "department": "Ophthalmology",
        "specialization": "Ophthalmologist",
        "experience": 9,
        "languages": ["English", "Hindi"],
        "fee": Decimal("18.00"),
        "working_days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
        "start_time": time(9, 0),
        "end_time": time(13, 0),
        "email": "vivek.modi@sunrisehospital.com",
        "phone": "+919000000009",
        "gender": "Male",
        "age": 36
    },
    {
        "name": "Dr. Chirag Bhatt",
        "department": "Dentistry",
        "specialization": "Dentist",
        "experience": 10,
        "languages": ["English", "Gujarati"],
        "fee": Decimal("15.00"),
        "working_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        "start_time": time(9, 0),
        "end_time": time(18, 0),
        "email": "chirag.bhatt@sunrisehospital.com",
        "phone": "+919000000010",
        "gender": "Male",
        "age": 38
    }
]

# Fixed 2026 public holidays in India/hospital policies
HOLIDAYS = [
    (1, 26),  # Republic Day (Jan 26)
    (3, 3),   # Holi (Mar 3, 2026)
    (8, 15),  # Independence Day (Aug 15)
    (10, 2),  # Gandhi Jayanti (Oct 2)
    (11, 8),  # Diwali Day 1 (Nov 8, 2026)
    (11, 9),  # Diwali Day 2 (Nov 9, 2026)
    (12, 25)  # Christmas (Dec 25)
]

def is_hospital_holiday(check_date: date) -> bool:
    return (check_date.month, check_date.day) in HOLIDAYS

def generate_slots(start_time: time, limit: int = 10) -> list:
    """Generates sequential 30-min slots with a 5-min buffer starting at start_time."""
    slots = []
    current_dt = datetime.combine(date.today(), start_time)
    for _ in range(limit):
        end_dt = current_dt + timedelta(minutes=30)
        slots.append((current_dt.time(), end_dt.time()))
        current_dt = end_dt + timedelta(minutes=5)
    return slots

def seed_db():
    # Make sure tables exist
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()
    
    try:
        print("Seeding database...")
        
        # 1. Seed Departments
        dept_map = {}
        for d_data in DEPARTMENTS:
            dept = db.query(Department).filter(Department.name == d_data["name"]).first()
            if not dept:
                dept = Department(
                    name=d_data["name"],
                    floor=d_data["floor"],
                    description=d_data["description"]
                )
                db.add(dept)
                db.flush()
            dept_map[d_data["name"]] = dept.id
            
        print(f"Departments seeded. Total: {len(dept_map)}")
        
        # Create a default Admin account if it doesn't exist
        admin_email = "admin@sunrisehospital.com"
        admin = db.query(User).filter(User.email == admin_email).first()
        if not admin:
            admin = User(
                name="Hospital Admin",
                email=admin_email,
                phone="+917940123456",
                password_hash=hash_password("admin123"),
                role="admin",
                age=40,
                gender="Male",
                preferred_language="English"
            )
            db.add(admin)
            db.flush()
            print("Admin account seeded (admin@sunrisehospital.com / admin123)")

        # 2. Seed Doctors, User accounts for doctors, and Doctor Schedules
        start_date = date.today() + timedelta(days=1)  # start scheduling from tomorrow
        date_range = [start_date + timedelta(days=x) for x in range(30)]
        
        for doc_data in DOCTORS:
            # Check if doctor user exists
            user = db.query(User).filter(User.email == doc_data["email"]).first()
            if not user:
                user = User(
                    name=doc_data["name"],
                    email=doc_data["email"],
                    phone=doc_data["phone"],
                    password_hash=hash_password("doctor123"),
                    role="doctor",
                    age=doc_data["age"],
                    gender=doc_data["gender"],
                    preferred_language="English"
                )
                db.add(user)
                db.flush()
                
            # Check if doctor profile exists
            doctor = db.query(Doctor).filter(Doctor.user_id == user.id).first()
            if not doctor:
                doctor = Doctor(
                    user_id=user.id,
                    name=doc_data["name"],
                    specialization=doc_data["specialization"],
                    department_id=dept_map[doc_data["department"]],
                    experience_years=doc_data["experience"],
                    languages=doc_data["languages"],
                    consultation_fee=doc_data["fee"]
                )
                db.add(doctor)
                db.flush()
            
            # Generate schedules for this doctor (30 days window)
            schedule_count = 0
            for current_date in date_range:
                # Skip if it is not a working day
                day_name = current_date.strftime("%a")
                if day_name not in doc_data["working_days"]:
                    continue
                # Skip if it is a public holiday
                if is_hospital_holiday(current_date):
                    continue
                
                # Check if schedule for this date already exists
                existing_schedule = db.query(DoctorSchedule).filter(
                    DoctorSchedule.doctor_id == doctor.id,
                    DoctorSchedule.date == current_date
                ).first()
                
                if not existing_schedule:
                    # Generate 10 slots for this day
                    slots = generate_slots(doc_data["start_time"], limit=10)
                    for start, end in slots:
                        sched = DoctorSchedule(
                            doctor_id=doctor.id,
                            date=current_date,
                            start_time=start,
                            end_time=end,
                            status="available"
                        )
                        db.add(sched)
                        schedule_count += 1
            
            print(f"Doctor profile seeded for {doc_data['name']}. Seeded {schedule_count} availability slots.")
        
        db.commit()
        print("Database seeding completed successfully!")
        
    except Exception as e:
        db.rollback()
        print(f"Error during seeding: {e}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    from backend.models import Department
    seed_db()
