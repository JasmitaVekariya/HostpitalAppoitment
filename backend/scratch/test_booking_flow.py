import os
import sys
import uuid
import requests
import time
import random

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

BASE_URL = "http://localhost:8000"

def run_booking_test():
    print("=== Start E2E Phase 3 Booking Flow & Triage Test ===")
    
    # 1. Register a test patient with complete details (so receptionist matches immediately)
    print("\n1. Registering test patient...")
    unique_id = str(uuid.uuid4())[:8]
    email = f"jasmita_{unique_id}@example.com"
    phone = f"+91{random.randint(6000000000, 9999999999)}"
    register_payload = {
        "name": "Jasmita Test",
        "email": email,
        "phone": phone,
        "password": "password123",
        "age": 21,
        "gender": "Female",
        "preferred_language": "English"
    }
    
    try:
        reg_resp = requests.post(f"{BASE_URL}/api/auth/register", json=register_payload)
        if reg_resp.status_code != 201:
            print(f"❌ Registration failed: {reg_resp.text}")
            return
        print("✅ Test user registered successfully.")
    except Exception as e:
        print(f"❌ Registration request failed: {e}")
        return

    # 1b. Login to obtain JWT Token
    print("\n1b. Logging in to acquire JWT token...")
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
        print("✅ JWT Token acquired.")
    except Exception as e:
        print(f"❌ Login request failed: {e}")
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # ================= Scenario A: Normal Skin Rash Triage =================
    session_id_a = str(uuid.uuid4())
    print(f"\n2. [Scenario A] Starting skin rash triage session: {session_id_a}")
    payload_a = {
        "session_id": session_id_a,
        "message": "I want to book an appointment. I have red itchy rashes on my skin."
    }
    
    try:
        res_a = requests.post(f"{BASE_URL}/api/chat", json=payload_a, headers=headers)
        if res_a.status_code != 200:
            print(f"❌ Scenario A request failed: {res_a.text}")
            return
            
        data_a = res_a.json()
        print("✅ Scenario A response received.")
        print(f"AI Receptionist Response:\n---\n{data_a['messages'][-1]['content']}\n---")
        print(f"Recommended Department: {data_a.get('department')}")
        print(f"Triage Priority: {data_a.get('priority')}")
        print(f"Available Slots Count: {len(data_a.get('available_slots', []))}")
        print(f"Booking Status: {data_a.get('booking_status')}")
        
        # Assertions
        assert data_a["department"] == "Dermatology", f"Expected department Dermatology, got {data_a['department']}"
        assert data_a["priority"] in ["LOW", "MEDIUM", "HIGH"], "Expected non-emergency priority"
        assert len(data_a["available_slots"]) == 3, f"Expected 3 slots, got {len(data_a['available_slots'])}"
        assert data_a["booking_status"] == "awaiting_slot_selection", f"Expected awaiting_slot_selection, got {data_a['booking_status']}"
        
        print("🎉 Scenario A Assertions Passed Successfully!")
        
        # 2b. Book Option 1
        print("\nWaiting 15 seconds to clear the rate-limit window...")
        time.sleep(15)
        print("\n2b. Booking Option 1...")
        payload_book = {
            "session_id": session_id_a,
            "message": "1"
        }
        res_book = requests.post(f"{BASE_URL}/api/chat", json=payload_book, headers=headers)
        if res_book.status_code != 200:
            print(f"❌ Booking request failed: {res_book.text}")
            return
            
        data_book = res_book.json()
        print("✅ Booking response received.")
        print(f"AI Receptionist Response:\n---\n{data_book['messages'][-1]['content']}\n---")
        print(f"Booking Status: {data_book.get('booking_status')}")
        
        assert data_book["booking_status"] == "confirmed", f"Expected confirmed, got {data_book['booking_status']}"
        assert "Booking Confirmed" in data_book["messages"][-1]["content"]
        print("🎉 Slot booking verified successfully!")
        
    except Exception as e:
        print(f"❌ Scenario A assertion failed: {e}")
        return

    # Wait to bypass OpenRouter rate limits
    print("\nWaiting 15 seconds to clear the rate-limit window...")
    time.sleep(15)

    # ================= Scenario B: Emergency Chest Pain Triage =================
    session_id_b = str(uuid.uuid4())
    print(f"\n3. [Scenario B] Starting emergency chest pain triage session: {session_id_b}")
    payload_b = {
        "session_id": session_id_b,
        "message": "Help me, I have severe chest pain and I cannot breathe."
    }
    
    try:
        res_b = requests.post(f"{BASE_URL}/api/chat", json=payload_b, headers=headers)
        if res_b.status_code != 200:
            print(f"❌ Scenario B request failed: {res_b.text}")
            return
            
        data_b = res_b.json()
        print("✅ Scenario B response received.")
        print(f"AI Receptionist Response:\n---\n{data_b['messages'][-1]['content']}\n---")
        print(f"Recommended Department: {data_b.get('department')}")
        print(f"Triage Priority: {data_b.get('priority')}")
        print(f"Available Slots Count: {len(data_b.get('available_slots', []))}")
        print(f"Booking Status: {data_b.get('booking_status')}")
        
        # Assertions
        assert data_b["priority"] == "EMERGENCY", f"Expected priority EMERGENCY, got {data_b['priority']}"
        assert data_b["booking_status"] == "emergency_redirect", f"Expected emergency_redirect, got {data_b['booking_status']}"
        assert len(data_b.get("available_slots", [])) == 0, "Expected 0 slots (booking bypassed)"
        assert "Emergency Line" in data_b["messages"][-1]["content"] or "nearest hospital" in data_b["messages"][-1]["content"]
        
        print("🎉 Scenario B Assertions Passed Successfully!")
        
    except Exception as e:
        print(f"❌ Scenario B assertion failed: {e}")
        return

    print("\n🏆 === All Phase 3 Booking Flow Triage Tests Passed! ===")

if __name__ == "__main__":
    run_booking_test()
