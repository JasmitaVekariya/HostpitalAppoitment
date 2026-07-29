import os
import sys
import uuid
import requests

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

BASE_URL = "http://localhost:8000"

def run_integration_test():
    print("=== Start E2E Chat & Checkpointer Integration Test ===")
    
    # 1. Register a unique test patient and nullify name/age for testing
    import random
    print("\n1. Registering a clean test patient...")
    unique_id = str(uuid.uuid4())[:8]
    email = f"test_{unique_id}@example.com"
    phone = f"+91{random.randint(6000000000, 9999999999)}"
    register_payload = {
        "name": "Temp Name",
        "email": email,
        "phone": phone,
        "password": "password123",
        "age": 30,
        "gender": "Male",
        "preferred_language": "English"
    }
    
    try:
        reg_resp = requests.post(f"{BASE_URL}/api/auth/register", json=register_payload)
        if reg_resp.status_code != 201:
            print(f"❌ Registration failed: {reg_resp.text}")
            return
            
        # Nullify name and age directly in the database
        from backend.database import SessionLocal
        from backend.models import User as DBUser
        db_session = SessionLocal()
        try:
            db_user = db_session.query(DBUser).filter(DBUser.email == email).first()
            if db_user:
                db_user.age = None
                db_session.commit()
                print("✅ Test user registered & DB profile reset (age=None).")
        finally:
            db_session.close()
            
    except Exception as e:
        print(f"❌ Registration setup failed: {e}")
        return

    # 1b. Login to get JWT Token
    print("\n1b. Logging in as test patient...")
    login_payload = {
        "email": email,
        "password": "password123"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/auth/login", json=login_payload)
        if response.status_code != 200:
            print(f"❌ Login failed: {response.text}")
            return
        
        token = response.json()["access_token"]
        print("✅ Login successful! JWT Token acquired.")
    except Exception as e:
        print(f"❌ Failed to reach backend auth api: {e}")
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # 2. Start Chat Session
    session_id = str(uuid.uuid4())
    print(f"\n2. Starting new chat session with ID: {session_id}")
    
    # Send message 1: Provide Name and Intent
    chat_payload_1 = {
        "session_id": session_id,
        "message": "Hello, I want to book an appointment. My name is John."
    }
    print(f"Sending Msg 1: '{chat_payload_1['message']}'")
    
    try:
        res1 = requests.post(f"{BASE_URL}/api/chat", json=chat_payload_1, headers=headers)
        if res1.status_code != 200:
            print(f"❌ Chat API Error: {res1.text}")
            return
            
        data1 = res1.json()
        print("✅ Message 1 response received.")
        print(f"AI response: {data1['messages'][-1]['content']}")
        print(f"Extracted Patient Info State: {data1['patient_info']}")
        print(f"Booking Status: {data1['booking_status']}")
        
        # Verify name is extracted
        if data1['patient_info'].get('name') != 'John':
            print("❌ Error: Name 'John' was not extracted!")
            return
            
    except Exception as e:
        print(f"❌ Request 1 failed: {e}")
        return

    # Wait for rate limit window to clear on OpenRouter free tier
    import time
    print("Waiting 15 seconds to clear the rate-limit window...")
    time.sleep(15)

    # Send message 2: Provide Age to satisfy loop
    chat_payload_2 = {
        "session_id": session_id,
        "message": "I am 35 years old."
    }
    print(f"\nSending Msg 2: '{chat_payload_2['message']}'")
    
    try:
        res2 = requests.post(f"{BASE_URL}/api/chat", json=chat_payload_2, headers=headers)
        if res2.status_code != 200:
            print(f"❌ Chat API Error: {res2.text}")
            return
            
        data2 = res2.json()
        print("✅ Message 2 response received.")
        print(f"AI response: {data2['messages'][-1]['content']}")
        print(f"Extracted Patient Info State: {data2['patient_info']}")
        print(f"Booking Status: {data2['booking_status']}")
        
        # Verify checkpointer combined the state (Name + Age)
        if data2['patient_info'].get('name') != 'John' or data2['patient_info'].get('age') != 35:
            print("❌ Checkpointer State Merge Failed: State did not persist between calls!")
            return
            
        print("\n✅ Checkpointer State Persisted successfully: Name=John, Age=35 both preserved.")
        
    except Exception as e:
        print(f"❌ Request 2 failed: {e}")
        return

    # 3. Check DB audit directly
    print("\n3. Verifying database session logs...")
    from backend.database import SessionLocal
    from backend.models import Conversation
    
    db = SessionLocal()
    try:
        conversation = db.query(Conversation).filter(Conversation.id == uuid.UUID(session_id)).first()
        if not conversation:
            print("❌ Error: Conversation record not found in database!")
            return
            
        print("✅ Conversation audit log located in database.")
        print(f"Saved DB State Profile: {conversation.current_state}")
        print(f"Total Saved Messages in DB: {len(conversation.messages)}")
        
        if len(conversation.messages) < 3:  # [User1, AI1, User2]
            print("❌ Error: Message history list in DB is incomplete!")
            return
            
        print("\n🎉 === All Integration Tests Passed Successfully! ===")
    finally:
        db.close()

if __name__ == "__main__":
    run_integration_test()
