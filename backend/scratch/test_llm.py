import os
import sys

# Add project root to sys.path so we can import backend packages
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.utils.llm import get_llm
from langchain_core.messages import HumanMessage

def test_llm():
    print("Initializing LLM...")
    llm = get_llm()
    print(f"Targeting Model: {llm.model_name}")
    print("Sending test request to OpenRouter...")
    try:
        response = llm.invoke([
            HumanMessage(content="Hello! Please reply in exactly three words.")
        ])
        print("\n=== Success! ===")
        print(f"LLM Response: {response.content}")
        print("================")
    except Exception as e:
        print(f"\n❌ LLM Call Failed: {e}")

if __name__ == "__main__":
    test_llm()
