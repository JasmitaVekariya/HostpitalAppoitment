import requests
import json

base_url = "http://127.0.0.1:8000/api"

# 1. Get new chat
resp = requests.post(f"{base_url}/chat/new", json={"patient_id": "86ac612b-c3b1-4525-b581-fcbfb40231d6"})
session_id = resp.json().get("session_id")
print("Session ID:", session_id)

# 2. Send message
payload = {
    "session_id": session_id,
    "patient_id": "86ac612b-c3b1-4525-b581-fcbfb40231d6",
    "message": "I have a rash on my face for two weeks. I want to meet a skin consultant"
}
resp2 = requests.post(f"{base_url}/chat", json=payload)
print(resp2.status_code)
print(resp2.text)
