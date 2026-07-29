from typing import Dict, Any, Optional
from langchain_core.messages import AIMessage
from backend.graph.state import HospitalState
from backend.utils.llm import call_openrouter_api, parse_json_markdown
from backend.prompts.intent import INTENT_AGENT_SYSTEM_PROMPT

# ─── Hard-coded off-topic keyword guard ──────────────────────────────────────
# These are non-medical topics that should NEVER enter the booking/triage flow.
OFF_TOPIC_KEYWORDS = [
    # Programming / tech
    "c++", "python", "java", "javascript", "html", "css", "sql", "php", "swift",
    "kotlin", "rust", "golang", "ruby", "typescript", "react", "angular", "vue",
    "machine learning", "deep learning", "neural network", "algorithm", "data structure",
    "api", "github", "git", "docker", "kubernetes", "linux", "windows", "android", "ios",
    "code", "coding", "programming", "software", "debug", "compiler", "runtime",
    "chatgpt", "openai", "gemini", "claude", "llm", "ai model",
    # General knowledge / trivia
    "capital of", "president of", "prime minister", "history of", "formula of",
    "recipe for", "how to cook", "weather", "temperature today", "stock price",
    "cryptocurrency", "bitcoin", "movie", "song", "lyrics", "netflix", "youtube",
    "sports", "cricket", "football", "match score", "ipl", "fifa",
    # School / homework
    "math problem", "solve this equation", "essay", "homework", "assignment",
    "physics", "chemistry", "biology class", "calculus",
    # Misc
    "joke", "tell me a joke", "funny", "meme", "news today", "astrology", "horoscope",
]

# Medical/hospital topics that should ALWAYS be treated as BOOK intent
BOOKING_KEYWORDS = [
    "fever", "fewer", "temperature", "cold", "cough", "rash", "itch", "pain", "hurt",
    "ache", "breath", "bleed", "wound", "sick", "ill", "doctor", "appointment", "book",
    "schedule", "consult", "slot", "triage", "physician", "cardiologist", "dermatologist",
    "pediatrician", "headache", "nausea", "vomit", "dizziness", "swelling", "infection",
    "fracture", "sprain", "allergy", "anxiety", "depression", "diabetes", "blood pressure",
    "heart", "stomach", "back pain", "chest", "eye", "ear", "throat", "skin", "tooth",
    "pregnant", "menstrual", "hospital", "clinic", "medicine", "prescription", "test",
    "scan", "mri", "x-ray", "lab", "report", "emergency", "urgent"
]

# Friendly off-topic reply templates
OFF_TOPIC_REPLIES = [
    "I'm your hospital assistant at Sunrise Multispeciality Hospital, so I can only help with health and medical topics — like booking appointments, describing symptoms, or checking your visit history.\n\nIs there anything health-related I can assist you with today? 😊",
    "That's a bit outside my expertise! I'm specialised in hospital appointments and medical guidance.\n\nIf you have any health concerns or would like to book an appointment, I'm happy to help! 🏥",
    "I'm here to assist with your healthcare needs at Sunrise Hospital — booking appointments, discussing symptoms, or checking appointment details.\n\nIs there a medical concern I can help you with? 💊",
]

_off_topic_reply_index = 0


def _get_off_topic_reply() -> str:
    global _off_topic_reply_index
    reply = OFF_TOPIC_REPLIES[_off_topic_reply_index % len(OFF_TOPIC_REPLIES)]
    _off_topic_reply_index += 1
    return reply


def intent_node(state: HospitalState) -> Dict[str, Any]:
    """Node to classify user intent and handle greetings, off-topic messages, and medical queries."""
    messages = state.get("messages", [])
    if not messages:
        return {"errors": ["No input message found"]}

    language = state.get("language", "English")

    last_user_message = ""
    for msg in reversed(messages):
        if msg.type == "human":
            last_user_message = msg.content.strip()
            break

    last_lower = last_user_message.lower()

    # ── 1. Hard medical keyword override → BOOK immediately ──────────────────
    for kw in BOOKING_KEYWORDS:
        if kw in last_lower:
            return {"intent": "BOOK", "errors": []}

    # ── 2. Hard off-topic keyword guard → reject immediately ─────────────────
    for kw in OFF_TOPIC_KEYWORDS:
        if kw in last_lower:
            return {
                "intent": "OFF_TOPIC",
                "messages": [AIMessage(content=_get_off_topic_reply())],
                "errors": []
            }

    # ── 3. Pure greeting shortcut ─────────────────────────────────────────────
    greetings = [
        "hi", "hello", "hey", "good morning", "good afternoon", "good evening",
        "greetings", "yo", "hola", "hii", "helo", "namaste"
    ]
    is_pure_greeting = any(
        last_lower == g or last_lower.startswith(g + " ") or last_lower.endswith(" " + g)
        for g in greetings
    )

    if is_pure_greeting:
        if "morning" in last_lower:
            greeting_reply = "Good morning!"
        elif "afternoon" in last_lower:
            greeting_reply = "Good afternoon!"
        elif "evening" in last_lower:
            greeting_reply = "Good evening!"
        else:
            greeting_reply = "Hello!"
        greeting_reply += " How can I assist you at Sunrise Multispeciality Hospital today? 🏥"
        return {
            "intent": "GREETING",
            "messages": [AIMessage(content=greeting_reply)],
            "errors": []
        }

    # ── 4. LLM-based intent classification ───────────────────────────────────
    try:
        api_messages = [{"role": "system", "content": INTENT_AGENT_SYSTEM_PROMPT}]
        for msg in messages:
            role = "user" if msg.type == "human" else ("assistant" if msg.type == "ai" else msg.type)
            api_messages.append({"role": role, "content": msg.content})

        api_messages.append({
            "role": "user",
            "content": f"[System Context - User Language: {language}. Classify the intent of the latest message in the thread.]"
        })

        response_content = call_openrouter_api(api_messages)
        result_dict = parse_json_markdown(response_content)
        print(f"[DEBUG] Intent processing LLM parsed result: {result_dict}")

        intent_val = str(result_dict.get("intent", "BOOK")).strip().upper()
        valid_intents = ["BOOK", "CANCEL", "RESCHEDULE", "CHECK_STATUS", "GREETING", "OFF_TOPIC"]
        if intent_val not in valid_intents:
            intent_val = "BOOK"

        response_state: Dict[str, Any] = {
            "intent": intent_val,
            "errors": []
        }

        if intent_val == "GREETING":
            greeting_msg = result_dict.get("greeting_message")
            if greeting_msg:
                response_state["messages"] = [AIMessage(content=str(greeting_msg))]

        elif intent_val == "OFF_TOPIC":
            off_topic_msg = result_dict.get("off_topic_message")
            if off_topic_msg and len(str(off_topic_msg).strip()) > 10:
                # Use LLM-generated message if it's meaningful
                response_state["messages"] = [AIMessage(content=str(off_topic_msg))]
            else:
                # Fall back to our curated reply
                response_state["messages"] = [AIMessage(content=_get_off_topic_reply())]

        return response_state

    except Exception as e:
        print(f"[DEBUG] Intent processing failed with error: {e}")
        return {
            "intent": "BOOK",
            "errors": [f"Intent processing warning: {e}"]
        }
