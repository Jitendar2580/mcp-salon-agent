
from typing import Any, List, Optional, Tuple
from dotenv import load_dotenv
from memory.prompt import get_system_prompt
from tools import tools 
import os
import re
import json
import dateparser
from datetime import datetime
from openai import OpenAI
# from .prompt import system_instruction
from enum import Enum
from dateparser.search import search_dates
import json
import os
import re
from datetime import datetime
from typing import Dict, Any

from utils.util import load_json_file

load_dotenv()

# API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
)

 
salon_appointments = {}
conversation_memory = {}


class ConversationMemory:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.messages = []
        self.bookings = []
        self.current_booking = {
            "customer": None,
            "date": None,
            "time": None,
            "service": None,
            "stylist": None
        } 
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
            key_norm = str(key).strip().lower()
 
            if key_norm in ("name", "customer_name", "full_name"):
                key_norm = "customer"
 
            if isinstance(value, str):
                value = value.strip()
 
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

TODAY_DATE = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def save_booking_to_file(booking_data: Dict[str, Any]) -> bool:
    """Save confirmed booking to booking_data.json"""
    try:
        all_bookings = load_json_file("booking_data.json")
        if not isinstance(all_bookings, list):
            all_bookings = [all_bookings] if all_bookings else []
        
        all_bookings.append(booking_data)
        
        with open("booking_data.json", "w", encoding="utf-8") as f:
            json.dump(all_bookings, f, ensure_ascii=False, indent=4)
        
        return True
    except Exception as e:
        print(f"Error saving booking: {e}")
        return False

def cancel_booking_from_file(booking_id: str = None, customer: str = None, date: str = None, stylist: str = None) -> tuple[bool, str]:
    """Cancel a booking from booking_data.json"""
    try:
        all_bookings = load_json_file("booking_data.json")
        if not isinstance(all_bookings, list):
            all_bookings = []
         
        found_index = -1
        found_booking = None
        
        for idx, booking in enumerate(all_bookings):
            match = True
            if booking_id and booking.get("booking_id") != booking_id:
                match = False
            if customer and booking.get("customer", "").lower() != customer.lower():
                match = False
            if date and booking.get("date") != date:
                match = False
            if stylist and booking.get("stylist", "").lower() != stylist.lower():
                match = False
            
            if match:
                found_index = idx
                found_booking = booking
                break
        
        if found_index == -1:
            return False, "Booking not found"
         
        removed_booking = all_bookings.pop(found_index)
         
        with open("booking_data.json", "w", encoding="utf-8") as f:
            json.dump(all_bookings, f, ensure_ascii=False, indent=4)
        
        return True, f"Cancelled: {removed_booking.get('service')} with {removed_booking.get('stylist')} on {removed_booking.get('date')} at {removed_booking.get('time')}"
    
    except Exception as e:
        print(f"Error cancelling booking: {e}")
        return False, str(e)

def reschedule_booking_in_file(old_data: Dict[str, Any], new_date: str = None, new_time: str = None) -> tuple[bool, str]:
    """Reschedule a booking in booking_data.json"""
    try:
        all_bookings = load_json_file("booking_data.json")
        if not isinstance(all_bookings, list):
            all_bookings = []
         
        found_index = -1
        for idx, booking in enumerate(all_bookings):
            if (booking.get("customer", "").lower() == old_data.get("customer", "").lower() and
                booking.get("date") == old_data.get("date") and
                booking.get("stylist", "").lower() == old_data.get("stylist", "").lower()):
                found_index = idx
                break
        
        if found_index == -1:
            return False, "Original booking not found"
         
        if new_date:
            all_bookings[found_index]["date"] = new_date
        if new_time:
            all_bookings[found_index]["time"] = new_time
        
        all_bookings[found_index]["updated_at"] = TODAY_DATE
         
        with open("booking_data.json", "w", encoding="utf-8") as f:
            json.dump(all_bookings, f, ensure_ascii=False, indent=4)
        
        updated = all_bookings[found_index]
        return True, f"Rescheduled to {updated.get('date')} at {updated.get('time')}"
    
    except Exception as e:
        print(f"Error rescheduling booking: {e}")
        return False, str(e)

def is_booking_complete(booking: Dict[str, Any]) -> bool:
    """Check if all required booking fields are filled"""
    required_fields = ["customer", "service", "stylist", "date", "time"]
    return all(booking.get(field) and booking.get(field) != "null" for field in required_fields)

 
def generate_response_with_memory(user_input: str, session_id: str) -> str:
    memory = get_or_create_memory(session_id)

    if user_input.strip():
        memory.add_message("user", user_input)

    
    recent_messages = [
        {
            "role": msg["role"],
            "content": msg["content"],
            **({"name": msg["name"]} if msg["role"] == "function" and "name" in msg else {})
        }
        for msg in memory.messages[-20:]
    ]
     
    system_instruction = get_system_prompt()
    messages = [system_instruction] + recent_messages

    try:
        chat_completion = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.3,
            response_format={"type": "json_object"}  # Force JSON mode
        )

        message = chat_completion.choices[0].message
        print("\n" + "="*50)
        print("Assistant message:", message.content)
        print("Current booking state:", memory.current_booking)
        print("="*50 + "\n")

        # Parse response
        response_text = ""
        action = "collecting"
        cancel_data = {}
        reschedule_data = {}
        
        if message.content:
            try: 
                clean_content = re.sub(
                    r"^```(?:json)?|```$", "", message.content.strip(), flags=re.MULTILINE
                ).strip()
                content_json = json.loads(clean_content)
                
                response_text = content_json.get("reply", "")
                action = content_json.get("action", "collecting")
                booking_data = content_json.get("booking_data", {})
                cancel_data = content_json.get("cancel_data", {})
                reschedule_data = content_json.get("reschedule_data", {})
                 
                if booking_data:
                    for key, value in booking_data.items():
                        if value and value != "null":
                            memory.current_booking[key] = value
                
                print(f"📍 Action detected by LLM: {action}")
                print(f"📋 Updated booking: {memory.current_booking}")
                print(f"🗑️ Cancel data: {cancel_data}")
                print(f"🔄 Reschedule data: {reschedule_data}")
                
            except (json.JSONDecodeError, AttributeError) as e:
                print(f"⚠️ JSON parse error: {e}")
                print(f"Raw content: {message.content}")
                response_text = message.content.strip()
                action = "collecting"
 
        memory.add_message("assistant", response_text)
 
        if action == "confirm_ready" and is_booking_complete(memory.current_booking):
            memory.current_booking["booking_id"] = f"BK{datetime.now().strftime('%Y%m%d%H%M%S')}"
            memory.current_booking["created_at"] = TODAY_DATE
            memory.current_booking["status"] = "confirmed"
             
            if save_booking_to_file(memory.current_booking.copy()):
                print("✅ Booking confirmed and saved to booking_data.json")
                print(f"✅ Saved booking: {memory.current_booking}")
                 
                memory.current_booking = {
                    "customer": None,
                    "service": None,
                    "stylist": None,
                    "date": None,
                    "time": None
                }
                print("🔄 Booking data cleared for next session")
            else:
                return "⚠️ There was an error saving your booking. Please try again."
 
        elif action == "cancel_ready" and cancel_data:
            success, message_text = cancel_booking_from_file(
                booking_id=cancel_data.get("booking_id"),
                customer=cancel_data.get("customer"),
                date=cancel_data.get("date"),
                stylist=cancel_data.get("stylist")
            )
            
            if success:
                print(f"✅ {message_text}")
            else:
                print(f"❌ Cancellation failed: {message_text}")
                return f"⚠️ Could not cancel booking: {message_text}"
 
        elif action == "reschedule_ready" and reschedule_data:
            old_data = {
                "customer": reschedule_data.get("old_customer"),
                "date": reschedule_data.get("old_date"),
                "stylist": reschedule_data.get("old_stylist")
            }
            
            success, message_text = reschedule_booking_in_file(
                old_data=old_data,
                new_date=reschedule_data.get("new_date"),
                new_time=reschedule_data.get("new_time")
            )
            
            if success:
                print(f"✅ {message_text}")
            else:
                print(f"❌ Rescheduling failed: {message_text}")
                return f"⚠️ Could not reschedule booking: {message_text}"

        return response_text

    except Exception as e:
        print(f"❌ Error in generate_response: {e}")
        import traceback
        traceback.print_exc()
        return f"⚠️ Error: {e}"


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


