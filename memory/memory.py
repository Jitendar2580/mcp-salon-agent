
from typing import Any, List, Optional, Tuple
from dotenv import load_dotenv
from tools import tools
from typing import Dict
import os
import re
import json
import dateparser
from datetime import datetime
from openai import OpenAI
from .prompt import system_instruction
from enum import Enum
from dateparser.search import search_dates

load_dotenv()

# API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),  # Make sure to set your API key
)


# In-memory storage for appointments and conversations
salon_appointments = {}
conversation_memory = {}


class ConversationMemory:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.messages = []
        self.bookings = []  # Each booking is a dict with name, date, time, service, stylist
        self.current_booking = {
            "customer": None,
            "date": None,
            "time": None,
            "service": None,
            "stylist": None
        }
        # greeting, collecting, confirming, completed
        self.conversation_state = "greeting"

    def add_message(self, role: str, content: str, name: str = None):
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        if name:
            message["name"] = name
        self.messages.append(message)

    def update_info(self, key: str, value):
        """
        Normalize incoming keys and update current_booking safely.
        Accepts 'name', 'customer_name', 'Name' etc and maps to 'customer'.
        """
        try:
            # Normalize key to lowercase string
            key_norm = str(key).strip().lower()

            # Map common synonyms to our internal keys
            if key_norm in ("name", "customer_name", "full_name"):
                key_norm = "customer"

            # If value is a simple string, clean it
            if isinstance(value, str):
                value = value.strip()

            # If value is a list/dict, keep original behavior
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        for sub_key, sub_value in item.items():
                            self.update_info(sub_key, sub_value)
                return

            if key_norm in self.current_booking:
                self.current_booking[key_norm] = value
                print(f"📌 memory.update_info: {key_norm} = {value}")
            else:
                # If an unknown key arrives, log it so you can add mappings later
                print(
                    f"⚠️ memory.update_info: Unknown key '{key}' -> skipped (value={value})")
        except Exception as e:
            print(f"⚠️ update_info error: {e}")

    def get_missing_info(self) -> List[str]:
        return [key for key, value in self.current_booking.items() if value is None]

    def is_current_booking_complete(self) -> bool:
        return all(value is not None for value in self.current_booking.values())

    def finalize_current_booking(self):
        if self.is_current_booking_complete():
            self.bookings.append(self.current_booking.copy())
            self.current_booking = {
                "customer": None,
                "date": None,
                "time": None,
                "service": None,
                "stylist": None
            }
            return True
        return False

    def get_all_bookings(self) -> List[Dict[str, str]]:
        return self.bookings


def get_or_create_memory(session_id: str) -> ConversationMemory:
    """Get existing conversation memory or create new one"""
    if session_id not in conversation_memory:
        conversation_memory[session_id] = ConversationMemory(session_id)
    return conversation_memory[session_id]


def get_conversation_summary(session_id: str) -> Dict:
    """Get conversation summary for debugging/monitoring"""
    if session_id in conversation_memory:
        memory = conversation_memory[session_id]
        return {
            "session_id": session_id,
            "state": memory.conversation_state,
            "collected_info": memory.current_booking,
            "message_count": len(memory.messages),
            "is_complete": memory.is_complete()
        }
    return {"error": "Session not found"}


def clear_conversation(session_id: str) -> bool:
    """Clear conversation memory for a session"""
    if session_id in conversation_memory:
        del conversation_memory[session_id]
        return True
    return False


def generate_response_with_memory(user_input: str, session_id: str, reform_tool_output=False) -> str:
    memory = get_or_create_memory(session_id)

    if user_input.strip():
        memory.add_message("user", user_input)

    openai_tools = [
        {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": tool_info["description"],
                "parameters": tool_info["parameters"]
            }
        }
        for tool_name, tool_info in tools.items()
    ]
    # Take last 20 messages
    recent_messages = [
        {
            "role": msg["role"],
            "content": msg["content"],
            **({"name": msg["name"]} if msg["role"] == "function" and "name" in msg else {})
        }
        for msg in memory.messages[-20:]
    ]
    messages = [system_instruction] + recent_messages

    try:
        chat_completion = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.3,
            tools=openai_tools,
            tool_choice="auto"
        )

        message = chat_completion.choices[0].message
        print("messagemessagemessage------------------", message)
        print("Before updating booking:", memory.current_booking)

        # Extract reply text & booking_data
        response = ""

        content_json = None
        if message.content:
            try:
                clean_content = re.sub(
                    r"^```(?:json)?|```$", "", message.content.strip(), flags=re.MULTILINE).strip()
                content_json = json.loads(clean_content)
                booking_data = content_json.get("booking_data")
                if booking_data:
                    for k, v in booking_data.items():
                        if v is not None:
                            memory.current_booking[k] = v
                response = content_json.get("reply", "")
            except (json.JSONDecodeError, AttributeError):
                response = message.content.strip()

        if message.tool_calls:
            print("🚨 Tool call was requested🚨", message.tool_calls)
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)
                raw_result = tools[tool_name]["function"](**tool_args)

                memory.add_message("function", str(raw_result), name=tool_name)

                if not reform_tool_output:
                    reform_prompt = (
                        f"The tool returned this result:\n{raw_result}\n\n"
                        "Please convert it into a clear, user-friendly reply for the user."
                    )
                    memory.add_message("user", reform_prompt)
                    return generate_response_with_memory("", session_id, reform_tool_output=True)

                else:
                    for msg in reversed(memory.messages):
                        if msg["role"] == "assistant":
                            return msg["content"]
                    return str(raw_result)

        if content_json and "reply" in content_json and not reform_tool_output:
            memory.add_message("function", json.dumps(
                content_json), name="tool_output")
            return generate_response_with_memory("", session_id, reform_tool_output=True)

        memory.add_message("assistant", response)
        return response

    except Exception as e:
        return f"⚠️ LLM error: {e}"


def handle_tool_call(tool_name: str, arguments: Dict[str, str]) -> str:
    tool = tools.get(tool_name)
    if not tool:
        return f"⚠️ Tool '{tool_name}' is not defined."

    required_args = tool["parameters"].get("required", [])
    missing_args = [arg for arg in required_args if arg not in arguments]

    if missing_args:
        return f"⚠️ Missing required argument(s) for tool '{tool_name}': {', '.join(missing_args)}"

    try:
        func = tool["function"]
        accepted_args = tool["parameters"]["properties"].keys()
        filtered_args = {k: v for k,
                         v in arguments.items() if k in accepted_args}

        result = func(**filtered_args)
        return result
    except Exception as e:
        return f"❌ Error calling tool '{tool_name}': {str(e)}"


