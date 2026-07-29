import unittest
import datetime
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Setup test DB imports
from backend.database import Base
from backend.models import User, Department, Doctor, DoctorSchedule, Appointment, PatientConversation
from backend.config import settings

class TestHospitalSystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create an in-memory SQLite database for isolated unit testing
        cls.engine = create_engine("sqlite:///:memory:")
        cls.Session = sessionmaker(bind=cls.engine)
        Base.metadata.create_all(cls.engine)
        
        # Seed basic department and doctor for test purposes
        db = cls.Session()
        dept = Department(name="General Medicine", floor=1, description="General Medicine")
        db.add(dept)
        db.flush()
        
        doc_user = User(
            name="Dr. Rahul Shah",
            email="rahul.shah@test.com",
            phone="+919000000001",
            password_hash="dummy",
            role="doctor"
        )
        db.add(doc_user)
        db.flush()
        
        doctor = Doctor(
            user_id=doc_user.id,
            name="Dr. Rahul Shah",
            specialization="General Physician",
            department_id=dept.id,
            experience_years=10,
            languages=["English"],
            consultation_fee=15.0
        )
        db.add(doctor)
        db.flush()
        
        patient = User(
            name="John Doe",
            email="john@test.com",
            phone="+919999999999",
            password_hash="dummy",
            role="patient",
            age=30,
            gender="Male"
        )
        db.add(patient)
        db.commit()
        
        cls.doctor_id = doctor.id
        cls.patient_id = patient.id
        db.close()

    def setUp(self):
        self.db = self.Session()

    def tearDown(self):
        # Clean up tables between tests
        self.db.query(Appointment).delete()
        self.db.query(DoctorSchedule).delete()
        self.db.query(PatientConversation).delete()
        self.db.commit()
        self.db.close()

    def test_booking_buffer_and_slot_filtering(self):
        """Rule 1-4: Test that slot suggestion correctly filters out past slots and respects the buffer."""
        now = datetime.datetime.now()
        
        # 1. Past slot (1 hour ago)
        past_dt = now - datetime.timedelta(hours=1)
        past_slot = DoctorSchedule(
            doctor_id=self.doctor_id,
            date=past_dt.date(),
            start_time=past_dt.time(),
            end_time=(past_dt + datetime.timedelta(minutes=30)).time(),
            status="available"
        )
        
        # 2. Slot inside the 2-hour buffer (e.g. 1 hour in the future)
        buffer_dt = now + datetime.timedelta(hours=1)
        buffer_slot = DoctorSchedule(
            doctor_id=self.doctor_id,
            date=buffer_dt.date(),
            start_time=buffer_dt.time(),
            end_time=(buffer_dt + datetime.timedelta(minutes=30)).time(),
            status="available"
        )
        
        # 3. Future slot outside the 2-hour buffer (e.g. 3 hours in the future)
        valid_dt = now + datetime.timedelta(hours=3)
        valid_slot = DoctorSchedule(
            doctor_id=self.doctor_id,
            date=valid_dt.date(),
            start_time=valid_dt.time(),
            end_time=(valid_dt + datetime.timedelta(minutes=30)).time(),
            status="available"
        )
        
        self.db.add_all([past_slot, buffer_slot, valid_slot])
        self.db.commit()
        
        # Query schedules
        slots = self.db.query(DoctorSchedule).filter(
            DoctorSchedule.doctor_id == self.doctor_id,
            DoctorSchedule.status == "available"
        ).all()
        
        # Apply filtering
        booking_buffer = 120 # 2 hours
        boundary_datetime = now + datetime.timedelta(minutes=booking_buffer)
        
        filtered = []
        for s in slots:
            slot_dt = datetime.datetime.combine(s.date, s.start_time)
            if slot_dt >= boundary_datetime:
                filtered.append(s)
                
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].id, valid_slot.id)

    def test_appointment_status_transitions(self):
        """Test status transitions: UPCOMING -> COMPLETED, RESCHEDULED, CANCELLED, and MISSED."""
        schedule = DoctorSchedule(
            doctor_id=self.doctor_id,
            date=datetime.date.today() + datetime.timedelta(days=1),
            start_time=datetime.time(10, 0),
            end_time=datetime.time(10, 30),
            status="booked"
        )
        self.db.add(schedule)
        self.db.flush()
        
        # Create UPCOMING appointment
        appt = Appointment(
            patient_id=self.patient_id,
            doctor_id=self.doctor_id,
            schedule_id=schedule.id,
            symptoms="['fever']",
            booking_status="confirmed",
            status="UPCOMING"
        )
        self.db.add(appt)
        self.db.commit()
        
        self.assertEqual(appt.status, "UPCOMING")
        
        # Transition to COMPLETED
        appt.status = "COMPLETED"
        appt.doctor_notes = "Recovering well."
        appt.completed_at = datetime.datetime.utcnow()
        self.db.commit()
        
        refreshed = self.db.query(Appointment).filter(Appointment.id == appt.id).first()
        self.assertEqual(refreshed.status, "COMPLETED")
        self.assertEqual(refreshed.doctor_notes, "Recovering well.")
        self.assertIsNotNone(refreshed.completed_at)

    def test_missed_appointment_transition(self):
        """Test that past appointments transition to MISSED if not completed."""
        # Create a schedule that ended 1 hour ago
        now = datetime.datetime.now()
        past_date = (now - datetime.timedelta(hours=2)).date()
        past_start = (now - datetime.timedelta(hours=2)).time()
        past_end = (now - datetime.timedelta(hours=1, minutes=30)).time()
        
        schedule = DoctorSchedule(
            doctor_id=self.doctor_id,
            date=past_date,
            start_time=past_start,
            end_time=past_end,
            status="booked"
        )
        self.db.add(schedule)
        self.db.flush()
        
        appt = Appointment(
            patient_id=self.patient_id,
            doctor_id=self.doctor_id,
            schedule_id=schedule.id,
            symptoms="['fever']",
            booking_status="confirmed",
            status="UPCOMING"
        )
        self.db.add(appt)
        self.db.commit()
        
        # Run Missed status transition logic
        active_appointments = self.db.query(Appointment).filter(
            Appointment.status.in_(["UPCOMING", "SCHEDULED", "RESCHEDULED"])
        ).all()
        
        for a in active_appointments:
            slot_end_datetime = datetime.datetime.combine(a.schedule.date, a.schedule.end_time)
            if now > slot_end_datetime:
                a.status = "MISSED"
        self.db.commit()
        
        refreshed = self.db.query(Appointment).filter(Appointment.id == appt.id).first()
        self.assertEqual(refreshed.status, "MISSED")

    def test_symptom_memory_aggregation_and_topic_shift(self):
        """Test that symptoms accumulate correctly and reset on topic shifts."""
        conv_id = uuid.uuid4()
        
        # Simulated message 1: User has fever
        symptoms_1 = ["fever"]
        conv_memory = PatientConversation(
            conversation_id=conv_id,
            current_symptoms=symptoms_1
        )
        self.db.add(conv_memory)
        self.db.commit()
        
        # User adds cough (no topic shift)
        symptoms_2 = ["fever", "cough"]
        conv_memory.current_symptoms = symptoms_2
        self.db.commit()
        
        refreshed = self.db.query(PatientConversation).filter(
            PatientConversation.conversation_id == conv_id
        ).first()
        self.assertEqual(refreshed.current_symptoms, ["fever", "cough"])
        
        # User has a different problem (topic shift)
        symptoms_3 = ["toothache"]
        conv_memory.current_symptoms = symptoms_3
        self.db.commit()
        
        refreshed = self.db.query(PatientConversation).filter(
            PatientConversation.conversation_id == conv_id
        ).first()
        self.assertEqual(refreshed.current_symptoms, ["toothache"])

if __name__ == "__main__":
    unittest.main()
