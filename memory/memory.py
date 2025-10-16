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
# from .prompt import system_instruction
from enum import Enum
from dateparser.search import search_dates
import json
import os
import re
from datetime import datetime
from typing import Dict, Any, Optional

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








TODAY_DATE = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def load_json_file(filepath: str) -> Any:
    """Safely load JSON file"""
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return [] if filepath == "booking_data.json" else {}
    return [] if filepath == "booking_data.json" else {}

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
        
        # Find matching booking
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
        
        # Remove the booking
        removed_booking = all_bookings.pop(found_index)
        
        # Save updated list
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
        
        # Find the booking to reschedule
        found_index = -1
        for idx, booking in enumerate(all_bookings):
            if (booking.get("customer", "").lower() == old_data.get("customer", "").lower() and
                booking.get("date") == old_data.get("date") and
                booking.get("stylist", "").lower() == old_data.get("stylist", "").lower()):
                found_index = idx
                break
        
        if found_index == -1:
            return False, "Original booking not found"
        
        # Update the booking
        if new_date:
            all_bookings[found_index]["date"] = new_date
        if new_time:
            all_bookings[found_index]["time"] = new_time
        
        all_bookings[found_index]["updated_at"] = TODAY_DATE
        
        # Save updated list
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

def get_system_prompt() -> Dict[str, str]:
    """Generate system prompt with fresh data"""
    salon_data = load_json_file("salon_data.json")
    booking_appointments = load_json_file("booking_data.json")
    
    return {
        "role": "system",
        "content": f"""
You are a friendly salon booking assistant.

**OUTPUT ONLY JSON - NO PLAIN TEXT**

---

## SALON DATA
{json.dumps(salon_data, indent=2)}

## EXISTING BOOKINGS
{json.dumps(booking_appointments, indent=2)}

---

## CRITICAL RULES - READ CAREFULLY

### Rule 1: ALWAYS SHOW STYLIST NAMES
When user picks a service, you MUST:
- Get list of stylists who offer that service from salon_data
- Show EXACT stylist NAMES in your reply
- Example: "For manicures, we have Sarah, Lisa, and Marco. Who would you like?"
- DO NOT say "we have several talented stylists" ← THIS IS WRONG
- DO NOT say "talented professionals" ← THIS IS WRONG
- ALWAYS LIST NAMES ← THIS IS REQUIRED

### Rule 2: NEVER ASK FOR SAME INFO TWICE
- User says "11am" → DO NOT ask "What time works best?"
- User says "Wednesday" → DO NOT ask "What date?"
- User says "Sarah" → DO NOT ask "Which stylist?"
- CHECK what user said and move forward

### Rule 3: VARY RESPONSES WHEN USER REPEATS
If user asks about MANICURE twice:
- First time: "For manicures, we have Sarah, Lisa, and Marco. Who would you like?"
- Second time: "Manicures are great! Sarah, Lisa, and Marco can do them. Which stylist interests you?"
- DO NOT use same response twice

### Rule 4: UNDERSTAND WHEN USER PROVIDES INFO
Parse what user actually said:
- "on upcoming wednesday 11am" = date is Wednesday + time is 11am (BOTH provided)
- "I want Sarah" = stylist is Sarah
- "manicure" = service is manicure

---

## FLOW - SERVICE → STYLIST → DATE → TIME → NAME → CONFIRM

**STEP 1: User says service**
Response:
{{
  "reply": "For [SERVICE], we have [STYLIST1], [STYLIST2], [STYLIST3]. Who would you like?",
  "booking_data": {{"customer": null, "service": "[SERVICE]", "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "collecting",
  "intent": null
}}

**STEP 2: User picks stylist**
Response:
{{
  "reply": "Great choice! When would you like to come in for your [SERVICE] with [STYLIST]?",
  "booking_data": {{"customer": null, "service": "[SERVICE]", "stylist": "[STYLIST]", "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "collecting",
  "intent": null
}}

**STEP 3: User provides date AND time together**
If user says "wednesday 11am" or "on 22nd at 11:00":
- Parse BOTH date and time
- DO NOT ask for time again
Response:
{{
  "reply": "Perfect! So you want [SERVICE] with [STYLIST] on [DATE] at [TIME]. Is that right?",
  "booking_data": {{"customer": "[NAME if known]", "service": "[SERVICE]", "stylist": "[STYLIST]", "date": "2025-10-22", "time": "11:00"}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "awaiting_confirmation",
  "intent": null
}}

**STEP 3B: User provides ONLY date (no time)**
Response:
{{
  "reply": "What time would you like on [DATE]?",
  "booking_data": {{"customer": null, "service": "[SERVICE]", "stylist": "[STYLIST]", "date": "2025-10-22", "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "collecting",
  "intent": null
}}

**STEP 4: User confirms (YES)**
Response:
{{
  "reply": "Perfect! Your [SERVICE] appointment with [STYLIST] is booked for [DATE] at [TIME]. See you then!",
  "booking_data": {{"customer": "[NAME]", "service": "[SERVICE]", "stylist": "[STYLIST]", "date": "2025-10-22", "time": "11:00"}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "confirm_ready",
  "intent": "confirm_booking"
}}

---

## REAL WORLD EXAMPLES

### Example 1: User says date + time together
```
User: on upcoming wednesday 11am
[Parse: date = Wednesday, time = 11am - BOTH provided]
[Do NOT ask "What time?" again]
[Move directly to confirmation]
```

### Example 2: User asks same service twice
```
User: i want manicure
Agent: For manicures, we have Sarah, Lisa, and Marco. Who would you like?

User: i want manicure
Agent: Manicures are great! Sarah, Lisa, and Marco can do them. Which stylist do you prefer?
[Different response, but same info]
```

### Example 3: User changes mind
```
User: i want madicure
Agent: For manicures, we have Sarah, Lisa, and Marco. Who would you like?

User: i want haircut
Agent: Perfect! For haircuts, we have Marco, Lisa, and Sarah. Who would you prefer?
[Update service to haircut]
[Show stylist list for haircut]
[Don't mention manicure again]
```

---

## WHAT TO DO WHEN USER SAYS "I HAVE MENTIONED ABOVE"

{{
  "reply": "Got it! So you want [SERVICE] with [STYLIST] on [DATE] at [TIME]. Is that correct?",
  "booking_data": {{"customer": "[NAME]", "service": "[SERVICE]", "stylist": "[STYLIST]", "date": "[DATE]", "time": "[TIME]"}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "awaiting_confirmation",
  "intent": null
}}

DO NOT ask for info again. Use what was already said.

---

## CANCELLATION

**User says: I want to cancel**

If appointment details are known from conversation:
{{
  "reply": "Got it! You want to cancel [SERVICE] with [STYLIST] on [DATE] at [TIME]. Is that right?",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": "[NAME]", "date": "[DATE]", "stylist": "[STYLIST]", "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "awaiting_confirmation",
  "intent": null
}}

**User confirms YES:**
{{
  "reply": "Done! Your appointment has been cancelled.",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": "[NAME]", "date": "[DATE]", "stylist": "[STYLIST]", "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "cancel_ready",
  "intent": "cancel_booking"
}}

---

## RESCHEDULE

**User says: I want to reschedule**

If current appointment is known:
{{
  "reply": "Sure! When would you like to reschedule your [SERVICE] with [STYLIST] to?",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": "[NAME]", "old_date": "[OLD_DATE]", "old_stylist": "[STYLIST]", "new_date": null, "new_time": null}},
  "action": "collecting",
  "intent": null
}}

**User provides new date + time:**
{{
  "reply": "So you want to move from [OLD_DATE] to [NEW_DATE] at [NEW_TIME]. Is that right?",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": "[NAME]", "old_date": "[OLD_DATE]", "old_stylist": "[STYLIST]", "new_date": "2025-10-25", "new_time": "14:00"}},
  "action": "awaiting_confirmation",
  "intent": null
}}

**User confirms YES:**
{{
  "reply": "Perfect! Your appointment has been rescheduled to [NEW_DATE] at [NEW_TIME].",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": "[NAME]", "old_date": "[OLD_DATE]", "old_stylist": "[STYLIST]", "new_date": "2025-10-25", "new_time": "14:00"}},
  "action": "reschedule_ready",
  "intent": "reschedule_booking"
}}

---

## JSON FORMAT (ALWAYS USE THIS)

{{
  "reply": "Your conversational response here",
  "booking_data": {{
    "customer": "name or null",
    "service": "service name or null",
    "stylist": "stylist name or null",
    "date": "YYYY-MM-DD or null",
    "time": "HH:MM or null"
  }},
  "cancel_data": {{
    "customer": "name or null",
    "date": "YYYY-MM-DD or null",
    "stylist": "stylist name or null",
    "booking_id": "id or null"
  }},
  "reschedule_data": {{
    "old_customer": "name or null",
    "old_date": "YYYY-MM-DD or null",
    "old_stylist": "stylist name or null",
    "new_date": "YYYY-MM-DD or null",
    "new_time": "HH:MM or null"
  }},
  "action": "collecting | awaiting_confirmation | confirm_ready | cancel_ready | reschedule_ready | checked | inquiry",
  "intent": "confirm_booking | cancel_booking | reschedule_booking | null"
}}

---

## ACTION VALUES
- **collecting** = asking for more info
- **awaiting_confirmation** = all info collected, waiting for yes/no
- **confirm_ready** = user said YES to booking (with intent: confirm_booking)
- **cancel_ready** = user said YES to cancel (with intent: cancel_booking)
- **reschedule_ready** = user said YES to reschedule (with intent: reschedule_booking)
- **checked** = showing appointments
- **inquiry** = general question

## INTENT VALUES (for popups)
- **confirm_booking** = show "Booking Confirmed" popup (ONLY when user confirms)
- **cancel_booking** = show "Cancelled" popup (ONLY when user confirms)
- **reschedule_booking** = show "Rescheduled" popup (ONLY when user confirms)
- **null** = no popup

---

## KEY CHECKLIST

ALWAYS show stylist NAMES - never say "talented stylists"
NEVER ask for same info twice
VARY responses when user repeats
Parse date + time together if given together
Use information user already provided
Move forward, don't go backward
Only set intent when user confirms YES
Keep responses natural and friendly
Use customer name when known
Output ONLY JSON

"""
    }   
         
def generate_response_with_memory(user_input: str, session_id: str) -> Dict:
    """Generate response with memory - Returns Dict with reply and intent"""
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
            response_format={"type": "json_object"}
        )

        message = chat_completion.choices[0].message
        print("\n" + "="*50)
        print("Assistant message:", message.content)
        print("Current booking state:", memory.current_booking)
        print("="*50 + "\n")

        response_text = ""
        action = "collecting"
        intent = None
        cancel_data = {}
        reschedule_data = {}
        popup_type = None
        show_popup = False
        
        if message.content:
            try:
                clean_content = re.sub(
                    r"^```(?:json)?|```$", "", message.content.strip(), flags=re.MULTILINE
                ).strip()
                content_json = json.loads(clean_content)
                
                response_text = content_json.get("reply", "")
                action = content_json.get("action", "collecting")
                intent = content_json.get("intent", None)
                booking_data = content_json.get("booking_data", {})
                cancel_data = content_json.get("cancel_data", {})
                reschedule_data = content_json.get("reschedule_data", {})
                
                if booking_data:
                    for key, value in booking_data.items():
                        if value and value != "null":
                            memory.current_booking[key] = value
                
                print(f"📍 Action detected by LLM: {action}")
                print(f"🎯 Intent detected by LLM: {intent}")
                print(f"📋 Updated booking: {memory.current_booking}")
                print(f"🗑️ Cancel data: {cancel_data}")
                print(f"🔄 Reschedule data: {reschedule_data}")
                
            except (json.JSONDecodeError, AttributeError) as e:
                print(f"⚠️ JSON parse error: {e}")
                print(f"Raw content: {message.content}")
                response_text = message.content.strip()
                action = "collecting"
                intent = None

        memory.add_message("assistant", response_text)
 
        if action == "confirm_ready" and intent == "confirm_booking" and is_booking_complete(memory.current_booking):
            memory.current_booking["booking_id"] = f"BK{datetime.now().strftime('%Y%m%d%H%M%S')}"
            memory.current_booking["created_at"] = TODAY_DATE
            memory.current_booking["status"] = "confirmed"
            
            if save_booking_to_file(memory.current_booking.copy()):
                print("✅ Booking confirmed and saved to booking_data.json")
                print(f"✅ Saved booking: {memory.current_booking}")
                
                show_popup = True
                popup_type = "booking_success"
                
                memory.current_booking = {
                    "customer": None,
                    "service": None,
                    "stylist": None,
                    "date": None,
                    "time": None
                }
                print("🔄 Booking data cleared for next session")
            else:
                response_text = "There was an error saving your booking. Please try again."
                show_popup = True
                popup_type = "booking_failed" 
                
        elif action == "cancel_ready" and intent == "cancel_booking" and cancel_data:
            success, message_text = cancel_booking_from_file(
                booking_id=cancel_data.get("booking_id"),
                customer=cancel_data.get("customer"),
                date=cancel_data.get("date"),
                stylist=cancel_data.get("stylist")
            )
            
            if success:
                print(f"✅ {message_text}")
                show_popup = True
                popup_type = "cancel_success"
            else:
                print(f"❌ Cancellation failed: {message_text}")
                response_text = f"Could not cancel booking: {message_text}"
                show_popup = True
                popup_type = "cancel_failed"
 
        elif action == "reschedule_ready" and intent == "reschedule_booking" and reschedule_data:
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
                show_popup = True
                popup_type = "reschedule_success"
            else:
                print(f"❌ Rescheduling failed: {message_text}")
                response_text = f"Could not reschedule booking: {message_text}"
                show_popup = True
                popup_type = "reschedule_failed"
 
        return {
            "reply": response_text,
            "intent": intent,
            "action": action,
            "show_popup": show_popup,
            "popup_type": popup_type,
            "booking_data": memory.current_booking.copy(),
            "cancel_data": cancel_data,
            "reschedule_data": reschedule_data
        }

    except Exception as e:
        print(f"❌ Error in generate_response: {e}")
        import traceback
        traceback.print_exc()
        return {
            "reply": f"Error: {e}",
            "intent": None,
            "action": "error",
            "show_popup": False,
            "popup_type": None,
            "booking_data": {},
            "cancel_data": {},
            "reschedule_data": {}
        }



# Note: You'll need to implement or import:
# - get_or_create_memory(session_id)
# - client (OpenAI client)
# - Memory class with methods: add_message(), messages attribute, current_booking attribute


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


