import unittest
import datetime
import uuid
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Setup test DB imports
from backend.database import Base
from backend.models import User, Department, Doctor, DoctorSchedule, Appointment, Conversation, PatientConversation
from backend.config import settings

class TestPatientConversations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create isolated in-memory SQLite database
        cls.engine = create_engine("sqlite:///:memory:")
        cls.Session = sessionmaker(bind=cls.engine)
        Base.metadata.create_all(cls.engine)
        
        db = cls.Session()
        # Seed user
        cls.user = User(
            name="Alice Smith",
            email="alice@test.com",
            phone="+919876543210",
            password_hash="hashed",
            role="patient"
        )
        db.add(cls.user)
        db.flush()
        
        # Seed department and doctor
        dept = Department(name="Cardiology", floor=2, description="Heart Care")
        db.add(dept)
        db.flush()
        
        cls.doctor = Doctor(
            user_id=None,
            name="Dr. Priya Sharma",
            specialization="Cardiologist",
            department_id=dept.id,
            experience_years=15,
            languages=["English"],
            consultation_fee=30.0
        )
        db.add(cls.doctor)
        db.flush()
        
        cls.schedule = DoctorSchedule(
            doctor_id=cls.doctor.id,
            date=datetime.date.today() + datetime.timedelta(days=2),
            start_time=datetime.time(14, 0),
            end_time=datetime.time(14, 30),
            status="available"
        )
        db.add(cls.schedule)
        db.commit()
        
        cls.user_id = cls.user.id
        cls.doctor_id = cls.doctor.id
        cls.schedule_id = cls.schedule.id
        db.close()

    def setUp(self):
        self.db = self.Session()

    def tearDown(self):
        self.db.query(Appointment).delete()
        self.db.query(Conversation).delete()
        self.db.query(PatientConversation).delete()
        self.db.commit()
        self.db.close()

    def test_start_new_chat_session(self):
        """Test starting a fresh chat session creates a Conversation in database."""
        session_uuid = uuid.uuid4()
        conversation = Conversation(
            id=session_uuid,
            user_id=self.user_id,
            messages=[],
            current_state={}
        )
        self.db.add(conversation)
        self.db.commit()
        
        db_conv = self.db.query(Conversation).filter(Conversation.id == session_uuid).first()
        self.assertIsNotNone(db_conv)
        self.assertEqual(db_conv.user_id, self.user_id)
        self.assertEqual(db_conv.messages, [])

    def test_unified_retrieval_appointments_and_unbooked_chats(self):
        """Test merging booked appointments and unbooked conversations in get_user_appointments logic."""
        # 1. Booked appointment conversation
        booked_conv_id = uuid.uuid4()
        booked_conv = Conversation(
            id=booked_conv_id,
            user_id=self.user_id,
            messages=[{"role": "user", "content": "I have chest pain."}],
            current_state={}
        )
        self.db.add(booked_conv)
        self.db.flush()
        
        appt = Appointment(
            patient_id=self.user_id,
            doctor_id=self.doctor_id,
            schedule_id=self.schedule_id,
            symptoms="['chest pain']",
            symptom_summary="chest pain",
            booking_status="confirmed",
            status="UPCOMING",
            conversation_id=booked_conv_id,
            created_at=datetime.datetime.utcnow()
        )
        self.db.add(appt)
        
        # 2. Unbooked conversation (triage in progress)
        unbooked_conv_id = uuid.uuid4()
        unbooked_conv = Conversation(
            id=unbooked_conv_id,
            user_id=self.user_id,
            messages=[{"role": "user", "content": "I feel dizzy."}],
            current_state={},
            updated_at=datetime.datetime.utcnow()
        )
        self.db.add(unbooked_conv)
        self.db.flush()
        
        pat_conv = PatientConversation(
            conversation_id=unbooked_conv_id,
            current_symptoms=["dizzy"],
            last_updated=datetime.datetime.utcnow()
        )
        self.db.add(pat_conv)
        self.db.commit()

        # Execute merging logic (mirroring the get_user_appointments router implementation)
        appointments = self.db.query(Appointment).filter(
            Appointment.patient_id == self.user_id
        ).all()
        
        linked_conv_ids = {a.conversation_id for a in appointments if a.conversation_id}
        self.assertIn(booked_conv_id, linked_conv_ids)
        self.assertNotIn(unbooked_conv_id, linked_conv_ids)
        
        result = []
        for a in appointments:
            result.append({
                "id": str(a.id),
                "doctor_name": "Dr. Priya Sharma",
                "specialization": "Cardiologist",
                "booking_status": a.booking_status,
                "status": a.status,
                "conversation_id": str(a.conversation_id),
                "is_booked": True
            })
            
        conversations = self.db.query(Conversation).filter(
            Conversation.user_id == self.user_id
        ).all()
        
        for conv in conversations:
            if conv.id not in linked_conv_ids:
                pc = self.db.query(PatientConversation).filter(
                    PatientConversation.conversation_id == conv.id
                ).first()
                symptom_list = pc.current_symptoms if pc else []
                result.append({
                    "id": f"conv_{str(conv.id)}",
                    "doctor_name": "AI Triage Assistant",
                    "specialization": "Hospital Reception",
                    "booking_status": "pending",
                    "status": "PENDING",
                    "conversation_id": str(conv.id),
                    "symptoms": str(symptom_list),
                    "is_booked": False
                })
                
        self.assertEqual(len(result), 2)
        
        # Verify one is booked, one is pending
        booked = [r for r in result if r["is_booked"]]
        pending = [r for r in result if not r["is_booked"]]
        
        self.assertEqual(len(booked), 1)
        self.assertEqual(booked[0]["conversation_id"], str(booked_conv_id))
        self.assertEqual(booked[0]["status"], "UPCOMING")
        
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["conversation_id"], str(unbooked_conv_id))
        self.assertEqual(pending[0]["status"], "PENDING")
        self.assertEqual(pending[0]["symptoms"], "['dizzy']")

    @patch("backend.graph.nodes.booking.SessionLocal")
    @patch("backend.utils.llm.call_openrouter_api")
    def test_reschedule_refusal_keeps_appointment(self, mock_call, mock_session):
        """Test that refusing to reschedule transitions booking_status to confirmed and clears slot state."""
        # Setup mock behavior
        mock_session.return_value = self.db
        
        # Calculate expected original date & time strings
        appt_date = datetime.date.today() + datetime.timedelta(days=2)
        appt_date_str = appt_date.strftime('%B %d, %Y')
        
        mock_call.side_effect = lambda messages: (
            '{"keep_existing": true}' if any("keep_existing" in m.get("content", "") for m in messages)
            else f"Dear Alice Smith, Your appointment with Dr. Priya Sharma on {appt_date_str} at 02:00 PM is still confirmed. We look forward to seeing you then. Best, Sunrise Hospital Reception Team."
        )

        # 1. Create a confirmed appointment
        session_uuid = uuid.uuid4()
        conv = Conversation(
            id=session_uuid,
            user_id=self.user_id,
            messages=[],
            current_state={}
        )
        self.db.add(conv)
        self.db.flush()
        
        appt = Appointment(
            patient_id=self.user_id,
            doctor_id=self.doctor_id,
            schedule_id=self.schedule_id,
            symptoms="['fever']",
            symptom_summary="fever",
            booking_status="confirmed",
            status="UPCOMING",
            conversation_id=session_uuid
        )
        self.db.add(appt)
        self.db.commit()

        # 2. Invoke booking_node logic with a refusal message and mock slot states
        from langchain_core.messages import HumanMessage
        
        state = {
            "messages": [HumanMessage(content="do not need to reschedule this already selected time is okay")],
            "session_id": str(session_uuid),
            "user_id": str(self.user_id),
            "available_slots": [{"id": 1, "date": "2026-07-30", "start_time": "10:00 AM"}],
            "selected_doctor": {"name": "Dr. Rahul Shah"},
            "errors": []
        }
        
        # Call booking_node
        from backend.graph.nodes.booking import booking_node
        res = booking_node(state)
        
        # Should transition status to confirmed and wipe slots
        self.assertEqual(res["booking_status"], "confirmed")
        self.assertEqual(res["available_slots"], [])
        self.assertIsNone(res["selected_doctor"])
        self.assertTrue(len(res["messages"]) > 0)
        
        reply_content = res["messages"][0].content
        self.assertIn("Alice Smith", reply_content)
        self.assertIn("Dr. Priya Sharma", reply_content)
        self.assertIn(appt_date_str, reply_content)
        self.assertIn("02:00 PM", reply_content)
        self.assertIn("Sunrise Hospital Reception Team", reply_content)

    def test_emergency_redirect_routes_to_symptom_triage(self):
        """Test that emergency_redirect and lockout states correctly route back to symptom triage on new message."""
        from backend.graph.workflow import route_intent, route_missing_info
        
        # 1. Test route_intent with emergency_redirect
        state_intent = {
            "intent": "BOOK",
            "booking_status": "emergency_redirect"
        }
        self.assertEqual(route_intent(state_intent), "patient_info")
        
        # 2. Test route_missing_info with emergency_redirect
        state_missing = {
            "booking_status": "emergency_redirect"
        }
        self.assertEqual(route_missing_info(state_missing), "symptom")

if __name__ == "__main__":
    unittest.main()
