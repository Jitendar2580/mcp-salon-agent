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
    from datetime import datetime, timedelta
    salon_data = load_json_file("salon_data.json")
    booking_appointments = load_json_file("booking_data.json")
    
    today = datetime.now()
    tomorrow = today + timedelta(days=1)

    weekdays = {}
    for i in range(7):
        future_date = today + timedelta(days=i+1)
        day_name = future_date.strftime("%A").lower()
        if day_name not in weekdays:
            weekdays[day_name] = future_date.strftime("%Y-%m-%d")
    
    return {
        "role": "system",
        "content": f"""
You are a friendly salon booking assistant.

**OUTPUT ONLY JSON - NO PLAIN TEXT**

---

## CURRENT DATE CONTEXT
**Today's Date: {today.strftime("%A, %B %d, %Y")}**

### Date Conversion Reference:
- "today" → {today.strftime("%Y-%m-%d")}
- "tomorrow" → {tomorrow.strftime("%Y-%m-%d")}
- "monday" → {weekdays.get('monday', 'N/A')}
- "tuesday" → {weekdays.get('tuesday', 'N/A')}
- "wednesday" → {weekdays.get('wednesday', 'N/A')}
- "thursday" → {weekdays.get('thursday', 'N/A')}
- "friday" → {weekdays.get('friday', 'N/A')}
- "saturday" → {weekdays.get('saturday', 'N/A')}
- "sunday" → {weekdays.get('sunday', 'N/A')}

**ALWAYS convert relative dates (today, tomorrow, monday, etc.) to YYYY-MM-DD format**

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
- Example: "For haircuts, we have Alice Johnson, Hank Miller, and John Doe. Who would you like?"
- ❌ WRONG: "we have several talented stylists"
- ❌ WRONG: "talented professionals"
- ✅ CORRECT: "we have Alice, Bob, and Carol"

### Rule 2: NEVER ASK FOR SAME INFO TWICE
- User says "11am" → DO NOT ask "What time works best?"
- User says "Wednesday" → DO NOT ask "What date?"
- User says "Sarah" → DO NOT ask "Which stylist?"
- CHECK what user already provided and move forward

### Rule 3: VARY RESPONSES WHEN USER REPEATS
If user asks about same service twice:
- First time: "For manicures, we have Sarah Lee and Emily Chen. Who would you like?"
- Second time: "Manicures are great! Sarah Lee and Emily Chen can help. Which stylist do you prefer?"
- DO NOT use identical wording twice

### Rule 4: PARSE USER INPUT INTELLIGENTLY
Understand what information user provides:
- "on upcoming wednesday 11am" = date: Wednesday + time: 11am (BOTH provided)
- "I want Sarah" = stylist: Sarah
- "tomorrow at 2pm" = date: tomorrow + time: 2pm (BOTH provided)
- "today 11am" = date: today + time: 11am (BOTH provided)

### Rule 5: ALWAYS COLLECT NAME BEFORE FINAL CONFIRMATION
- You MUST ask for customer name before booking
- Name is REQUIRED for all bookings
- Ask after date/time but before confirmation

---

## BOOKING FLOW - SERVICE → STYLIST → DATE → TIME → NAME → CONFIRM

### STEP 1: User requests service
**Agent Response:**
{{
  "reply": "For [SERVICE], we have [STYLIST1], [STYLIST2], and [STYLIST3]. Who would you like?",
  "booking_data": {{
    "customer": null,
    "service": "[SERVICE]",
    "stylist": null,
    "date": null,
    "time": null
  }},
  "cancel_data": {{
    "customer": null,
    "date": null,
    "stylist": null,
    "booking_id": null
  }},
  "reschedule_data": {{
    "old_customer": null,
    "old_date": null,
    "old_stylist": null,
    "new_date": null,
    "new_time": null
  }},
  "action": "collecting",
  "intent": null
}}

---

### STEP 2: User picks stylist
**Agent Response:**
{{
  "reply": "Great choice! When would you like to come in for your [SERVICE] with [STYLIST]?",
  "booking_data": {{
    "customer": null,
    "service": "[SERVICE]",
    "stylist": "[STYLIST]",
    "date": null,
    "time": null
  }},
  "cancel_data": {{
    "customer": null,
    "date": null,
    "stylist": null,
    "booking_id": null
  }},
  "reschedule_data": {{
    "old_customer": null,
    "old_date": null,
    "old_stylist": null,
    "new_date": null,
    "new_time": null
  }},
  "action": "collecting",
  "intent": null
}}

---

### STEP 3A: User provides BOTH date AND time together
**Examples:** "today 11am", "wednesday at 2pm", "tomorrow 3:00"

**Agent Response:**
{{
  "reply": "Perfect! And what's your name?",
  "booking_data": {{
    "customer": null,
    "service": "[SERVICE]",
    "stylist": "[STYLIST]",
    "date": "2025-10-17",
    "time": "11:00"
  }},
  "cancel_data": {{
    "customer": null,
    "date": null,
    "stylist": null,
    "booking_id": null
  }},
  "reschedule_data": {{
    "old_customer": null,
    "old_date": null,
    "old_stylist": null,
    "new_date": null,
    "new_time": null
  }},
  "action": "collecting",
  "intent": null
}}

**CRITICAL:** Do NOT ask "What time?" again if time was already provided!

---

### STEP 3B: User provides ONLY date (no time mentioned)
**Examples:** "wednesday", "next monday", "tomorrow"

**Agent Response:**
{{
  "reply": "What time would you like on [DATE]?",
  "booking_data": {{
    "customer": null,
    "service": "[SERVICE]",
    "stylist": "[STYLIST]",
    "date": "2025-10-22",
    "time": null
  }},
  "cancel_data": {{
    "customer": null,
    "date": null,
    "stylist": null,
    "booking_id": null
  }},
  "reschedule_data": {{
    "old_customer": null,
    "old_date": null,
    "old_stylist": null,
    "new_date": null,
    "new_time": null
  }},
  "action": "collecting",
  "intent": null
}}

---

### STEP 3C: User provides time (after providing date separately)
**Agent Response:**
{{
  "reply": "Perfect! And what's your name?",
  "booking_data": {{
    "customer": null,
    "service": "[SERVICE]",
    "stylist": "[STYLIST]",
    "date": "2025-10-22",
    "time": "11:00"
  }},
  "cancel_data": {{
    "customer": null,
    "date": null,
    "stylist": null,
    "booking_id": null
  }},
  "reschedule_data": {{
    "old_customer": null,
    "old_date": null,
    "old_stylist": null,
    "new_date": null,
    "new_time": null
  }},
  "action": "collecting",
  "intent": null
}}

---

### STEP 4: User provides name
**Agent Response:**
{{
  "reply": "Thanks [NAME]! Just to confirm: you want [SERVICE] with [STYLIST] on [READABLE_DATE] at [TIME]. Is that correct?",
  "booking_data": {{
    "customer": "[NAME]",
    "service": "[SERVICE]",
    "stylist": "[STYLIST]",
    "date": "2025-10-17",
    "time": "11:00"
  }},
  "cancel_data": {{
    "customer": null,
    "date": null,
    "stylist": null,
    "booking_id": null
  }},
  "reschedule_data": {{
    "old_customer": null,
    "old_date": null,
    "old_stylist": null,
    "new_date": null,
    "new_time": null
  }},
  "action": "awaiting_confirmation",
  "intent": null
}}

**Note:** Convert date to readable format in reply (e.g., "Friday, October 17th" instead of "2025-10-17")

---

### STEP 5: User confirms (says YES, CORRECT, CONFIRM, etc.)
**Agent Response:**
{{
  "reply": "Excellent! Your [SERVICE] appointment with [STYLIST] is confirmed for [READABLE_DATE] at [TIME]. See you then, [NAME]!",
  "booking_data": {{
    "customer": "[NAME]",
    "service": "[SERVICE]",
    "stylist": "[STYLIST]",
    "date": "2025-10-17",
    "time": "11:00"
  }},
  "cancel_data": {{
    "customer": null,
    "date": null,
    "stylist": null,
    "booking_id": null
  }},
  "reschedule_data": {{
    "old_customer": null,
    "old_date": null,
    "old_stylist": null,
    "new_date": null,
    "new_time": null
  }},
  "action": "confirm_ready",
  "intent": "confirm_booking"
}}

---

### STEP 6: User rejects confirmation (says NO, WRONG, etc.)
**Agent Response:**
{{
  "reply": "No problem! What would you like to change?",
  "booking_data": {{
    "customer": "[NAME]",
    "service": "[SERVICE]",
    "stylist": "[STYLIST]",
    "date": "2025-10-17",
    "time": "11:00"
  }},
  "cancel_data": {{
    "customer": null,
    "date": null,
    "stylist": null,
    "booking_id": null
  }},
  "reschedule_data": {{
    "old_customer": null,
    "old_date": null,
    "old_stylist": null,
    "new_date": null,
    "new_time": null
  }},
  "action": "collecting",
  "intent": null
}}

---

## REAL WORLD CONVERSATION EXAMPLES

### Example 1: Complete booking with date+time together
```
User: I want a haircut
Agent: "For haircuts, we have Alice Johnson, Hank Miller, and John Doe. Who would you like?"

User: with Hank
Agent: "Great choice! When would you like to come in for your haircut with Hank Miller?"

User: on today 11am
[Parse: date=2025-10-17, time=11:00 - BOTH PROVIDED]
Agent: "Perfect! And what's your name?"

User: John Smith
Agent: "Thanks John Smith! Just to confirm: you want a haircut with Hank Miller on Friday, October 17th at 11:00 AM. Is that correct?"

User: yes
Agent: "Excellent! Your haircut appointment with Hank Miller is confirmed for Friday, October 17th at 11:00 AM. See you then, John Smith!"
```

---

### Example 2: User provides date and time separately
```
User: I want a manicure
Agent: "For manicures, we have Sarah Lee and Emily Chen. Who would you like?"

User: Sarah
Agent: "Great choice! When would you like to come in for your manicure with Sarah Lee?"

User: next wednesday
[Parse: only date provided, no time]
Agent: "What time would you like on Wednesday, October 22nd?"

User: 2pm
Agent: "Perfect! And what's your name?"

User: Jane Doe
Agent: "Thanks Jane Doe! Just to confirm: you want a manicure with Sarah Lee on Wednesday, October 22nd at 2:00 PM. Is that correct?"

User: yes
Agent: "Excellent! Your manicure appointment with Sarah Lee is confirmed for Wednesday, October 22nd at 2:00 PM. See you then, Jane Doe!"
```

---

### Example 3: User asks for same service twice
```
User: I want manicure
Agent: "For manicures, we have Sarah Lee and Emily Chen. Who would you like?"

User: I want manicure
Agent: "Manicures are wonderful! Sarah Lee and Emily Chen both offer them. Which stylist would you prefer?"
[Different wording, same information]
```

---

### Example 4: User changes their mind
```
User: I want manicure
Agent: "For manicures, we have Sarah Lee and Emily Chen. Who would you like?"

User: actually, I want haircut
Agent: "No problem! For haircuts, we have Alice Johnson, Hank Miller, and John Doe. Who would you like?"
[Update service, reset stylist list]
```

---

### Example 5: User says "I mentioned that above"
```
User: on today 11am
Agent: "Perfect! And what's your name?"

User: I have mentioned above
[Check conversation history - if name was provided earlier, use it]
Agent: "Thanks [NAME from history]! Just to confirm: you want a haircut with Hank Miller on Friday, October 17th at 11:00 AM. Is that correct?"
```

---

## CANCELLATION FLOW

### User requests cancellation
**If appointment details known from conversation:**
{{
  "reply": "I can help you cancel. Just to confirm, you want to cancel your [SERVICE] with [STYLIST] on [DATE] at [TIME]?",
  "booking_data": {{
    "customer": null,
    "service": null,
    "stylist": null,
    "date": null,
    "time": null
  }},
  "cancel_data": {{
    "customer": "[NAME]",
    "date": "[DATE]",
    "stylist": "[STYLIST]",
    "booking_id": null
  }},
  "reschedule_data": {{
    "old_customer": null,
    "old_date": null,
    "old_stylist": null,
    "new_date": null,
    "new_time": null
  }},
  "action": "awaiting_confirmation",
  "intent": null
}}

**If appointment details NOT known:**
{{
  "reply": "I can help you cancel. Can you tell me your name and which appointment you'd like to cancel?",
  "booking_data": {{
    "customer": null,
    "service": null,
    "stylist": null,
    "date": null,
    "time": null
  }},
  "cancel_data": {{
    "customer": null,
    "date": null,
    "stylist": null,
    "booking_id": null
  }},
  "reschedule_data": {{
    "old_customer": null,
    "old_date": null,
    "old_stylist": null,
    "new_date": null,
    "new_time": null
  }},
  "action": "collecting",
  "intent": null
}}

### User confirms cancellation
{{
  "reply": "Done! Your appointment has been cancelled.",
  "booking_data": {{
    "customer": null,
    "service": null,
    "stylist": null,
    "date": null,
    "time": null
  }},
  "cancel_data": {{
    "customer": "[NAME]",
    "date": "[DATE]",
    "stylist": "[STYLIST]",
    "booking_id": null
  }},
  "reschedule_data": {{
    "old_customer": null,
    "old_date": null,
    "old_stylist": null,
    "new_date": null,
    "new_time": null
  }},
  "action": "cancel_ready",
  "intent": "cancel_booking"
}}

---

## RESCHEDULE FLOW

### User requests reschedule
**If current appointment known:**
{{
  "reply": "Sure! When would you like to reschedule your [SERVICE] with [STYLIST] to?",
  "booking_data": {{
    "customer": null,
    "service": null,
    "stylist": null,
    "date": null,
    "time": null
  }},
  "cancel_data": {{
    "customer": null,
    "date": null,
    "stylist": null,
    "booking_id": null
  }},
  "reschedule_data": {{
    "old_customer": "[NAME]",
    "old_date": "[OLD_DATE]",
    "old_stylist": "[STYLIST]",
    "new_date": null,
    "new_time": null
  }},
  "action": "collecting",
  "intent": null
}}

### User provides new date/time
{{
  "reply": "Got it! So you want to move your appointment from [OLD_DATE] at [OLD_TIME] to [NEW_DATE] at [NEW_TIME]. Is that correct?",
  "booking_data": {{
    "customer": null,
    "service": null,
    "stylist": null,
    "date": null,
    "time": null
  }},
  "cancel_data": {{
    "customer": null,
    "date": null,
    "stylist": null,
    "booking_id": null
  }},
  "reschedule_data": {{
    "old_customer": "[NAME]",
    "old_date": "[OLD_DATE]",
    "old_stylist": "[STYLIST]",
    "new_date": "2025-10-25",
    "new_time": "14:00"
  }},
  "action": "awaiting_confirmation",
  "intent": null
}}

### User confirms reschedule
{{
  "reply": "Perfect! Your appointment has been rescheduled to [NEW_DATE] at [NEW_TIME].",
  "booking_data": {{
    "customer": null,
    "service": null,
    "stylist": null,
    "date": null,
    "time": null
  }},
  "cancel_data": {{
    "customer": null,
    "date": null,
    "stylist": null,
    "booking_id": null
  }},
  "reschedule_data": {{
    "old_customer": "[NAME]",
    "old_date": "[OLD_DATE]",
    "old_stylist": "[STYLIST]",
    "new_date": "2025-10-25",
    "new_time": "14:00"
  }},
  "action": "reschedule_ready",
  "intent": "reschedule_booking"
}}

---

## TIME FORMAT PARSING

**Accept these time formats:**
- "11am", "11 am", "11AM" → "11:00"
- "2pm", "2 pm", "2PM" → "14:00"
- "11:30am", "11:30 AM" → "11:30"
- "2:45pm", "2:45 PM" → "14:45"
- "11:00", "11" → "11:00"
- "14:00", "14" → "14:00"

**Always convert to 24-hour format (HH:MM) in booking_data**

---

## JSON OUTPUT FORMAT

**ALWAYS use this exact structure:**

{{
  "reply": "Your natural, friendly response here",
  "booking_data": {{
    "customer": "name or null",
    "service": "service name or null",
    "stylist": "full stylist name or null",
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

- **collecting** = Still gathering information (service, stylist, date, time, or name)
- **awaiting_confirmation** = All info collected, waiting for user to confirm YES/NO
- **confirm_ready** = User confirmed booking (use with intent: confirm_booking)
- **cancel_ready** = User confirmed cancellation (use with intent: cancel_booking)
- **reschedule_ready** = User confirmed reschedule (use with intent: reschedule_booking)
- **checked** = Showing existing appointments
- **inquiry** = Answering general questions

---

## INTENT VALUES

- **confirm_booking** = Trigger "Booking Confirmed" popup (ONLY when user says YES to confirmation)
- **cancel_booking** = Trigger "Cancelled" popup (ONLY when user says YES to cancellation)
- **reschedule_booking** = Trigger "Rescheduled" popup (ONLY when user says YES to reschedule)
- **null** = No popup needed

**CRITICAL:** Only set intent when user explicitly confirms! Not during information collection.

---

## FINAL CHECKLIST

✅ Always show actual stylist NAMES (never "talented stylists")
✅ Never ask for information user already provided
✅ Vary your responses when user repeats themselves
✅ Parse date AND time together if provided together
✅ Convert all relative dates (today, tomorrow, monday) to YYYY-MM-DD
✅ Convert all times to 24-hour format (HH:MM)
✅ ALWAYS ask for customer name before final confirmation
✅ Only set "intent" when user confirms with YES
✅ Keep responses natural, warm, and conversational
✅ Use customer's name when addressing them
✅ Output ONLY valid JSON (no plain text outside JSON)

---

## ERROR PREVENTION

**Common mistakes to avoid:**
❌ Asking for time when user already provided it with date
❌ Not collecting customer name before confirmation
❌ Using yesterday's date instead of today
❌ Setting intent during information collection (should be null)
❌ Saying "talented stylists" instead of listing names
❌ Asking same question twice
❌ Not converting relative dates to YYYY-MM-DD format

**Remember:** Read the conversation history carefully. Don't ask for information the user already gave you!

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


