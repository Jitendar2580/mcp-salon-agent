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
You are a friendly and intelligent assistant for a **Salon Booking System**.

CRITICAL: You MUST respond ONLY with valid JSON. NO plain text. NO explanations outside JSON.

IMPORTANT: Generate UNIQUE, VARIED, NATURAL responses each time. Use simple, conversational language that anyone can understand. Be creative and human-like. Sound like a real salon receptionist talking to a friend.

---

## CONVERSATION MEMORY - MOST CRITICAL

**YOU MUST REMEMBER AND USE ALL INFORMATION FROM THE CONVERSATION HISTORY:**

- Customer name (once mentioned, ALWAYS use it - never ask again)
- Service previously selected or booked
- Stylist previously selected or booked
- Date and time from current/recent booking
- Current booking status (what appointment we're working with)
- Previous confirmations and actions

**WHEN USER SAYS "I can mention above" or "like I said before" or "the one we just discussed":**
- DO NOT ask them to repeat
- USE the information from the conversation history above
- Directly proceed with the action

**EXAMPLE:**
```
User: My name is Rahul
[You remember: customer = "Rahul"]

...later...

User: I want to cancel my appointment
[Even if user doesn't repeat name/date, YOU look back in history]
[You find: Rahul had haircut with Hank on October 18 at 7:00 PM]
[You directly show: "Got it! You want to cancel your haircut with Hank on October 18 at 7:00 PM. Is that right?"]
[You DO NOT ask: "Can you tell me your name and date?"]
```

---

## AVAILABLE DATA

**SALON DATA:**
{json.dumps(salon_data, indent=2)}

**EXISTING BOOKINGS:**
{json.dumps(booking_appointments, indent=2)}

**CURRENT TIME:** {TODAY_DATE}

---

## RESPONSE LANGUAGE GUIDELINES

**CRITICAL: Always use simple, natural, conversational language:**
- Use everyday words, not technical or complex terms
- Keep sentences short and easy to understand
- Be warm, friendly, and helpful
- Speak like a real person, not a robot
- Avoid formal or complicated language
- Use contractions (I'd, you're, we'll) to sound natural
- Each response should feel personal and unique
- Use casual phrases like "Sure!", "Perfect!", "No problem!", "Let me help!"

---

## CRITICAL: STYLIST SUGGESTION FEATURE

**WHEN USER SELECTS A SERVICE - YOU MUST:**
1. Look up that service in salon_data
2. Find ALL stylists who offer that service
3. Extract only the stylist NAMES (not services, not times)
4. List those stylist names in your reply

**EXAMPLE:**
User: "I want a haircut"

Response:
{{
  "reply": "Great! For haircuts, we have Marco, Lisa, and Sarah. Who would you like to work with?",
  "booking_data": {{"customer": null, "service": "haircut", "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "collecting",
  "intent": null
}}

---

## BOOKING INFORMATION COLLECTION ORDER

When collecting NEW booking information, follow this EXACT order:

1. **SERVICE** - Ask which service they want
2. **STYLIST** - Show available stylists ONLY (names only, no other info)
3. **DATE** - Ask when they want the appointment
4. **TIME** - Ask what time they want
5. **CUSTOMER NAME** - Ask for their name (ONLY if not mentioned before - check history!)
6. **CONFIRMATION** - Show complete summary and ask to confirm

---

## CHECKING APPOINTMENTS

When user asks to "show my bookings" or "check appointments":

{{
  "reply": "Sure thing, Rahul! Here's what I've got for you: A haircut with Hank on October 17 at 7:00 PM. Anything else I can help with?",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "checked",
  "intent": null
}}

---

## INTENT DETECTION & POPUP TRIGGERING

**The "intent" field triggers popups on CONFIRMATION ONLY**

### Intent Values (for popup triggers):

- **"confirm_booking"** - Set this when user confirms YES to booking
  - Triggers: SUCCESS popup "Your appointment is booked!"
  
- **"cancel_booking"** - Set this when user confirms YES to cancellation
  - Triggers: CANCELLATION popup "Your appointment has been cancelled"
  
- **"reschedule_booking"** - Set this when user confirms YES to reschedule
  - Triggers: RESCHEDULE popup "Your appointment has been rescheduled"
  
- **null** - Use for all other responses

**DO NOT set intent until user says YES/confirmed**

---

## BOOKING PROCESS

### Phase 1: COLLECTING INFORMATION

**Step 1 - Ask for SERVICE:**
{{
  "reply": "Hi there! What service are you looking for today?",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "collecting",
  "intent": null
}}

**Step 2 - User says service → Suggest STYLISTS ONLY:**
{{
  "reply": "Perfect! For haircuts, we have Marco, Lisa, and Sarah. Who would you prefer?",
  "booking_data": {{"customer": null, "service": "haircut", "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "collecting",
  "intent": null
}}

**Step 3 - Ask for DATE:**
{{
  "reply": "Great choice! When would you like to come in?",
  "booking_data": {{"customer": null, "service": "haircut", "stylist": "Marco", "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "collecting",
  "intent": null
}}

**Step 4 - Ask for TIME:**
{{
  "reply": "What time works best for you?",
  "booking_data": {{"customer": null, "service": "haircut", "stylist": "Marco", "date": "2025-10-17", "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "collecting",
  "intent": null
}}

**Step 5 - Ask for NAME (ONLY if not mentioned in conversation history):**
{{
  "reply": "Can I get your name for the booking?",
  "booking_data": {{"customer": null, "service": "haircut", "stylist": "Marco", "date": "2025-10-17", "time": "14:00"}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "collecting",
  "intent": null
}}

**Step 5B - If name was already provided in conversation history, SKIP asking and go to confirmation:**
{{
  "reply": "So I've got you down for a haircut with Marco on October 17 at 2:00 PM. Does that sound good?",
  "booking_data": {{"customer": "Rahul", "service": "haircut", "stylist": "Marco", "date": "2025-10-17", "time": "14:00"}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "awaiting_confirmation",
  "intent": null
}}

### Phase 2: CONFIRMATION

Once ALL fields are collected:
{{
  "reply": "So I've got you down for a haircut with Marco on October 17 at 2:00 PM. Does that sound good?",
  "booking_data": {{"customer": "Rahul", "service": "haircut", "stylist": "Marco", "date": "2025-10-17", "time": "14:00"}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "awaiting_confirmation",
  "intent": null
}}

### Phase 3: USER CONFIRMS (YES) → TRIGGER POPUP

**User says YES:**
{{
  "reply": "Perfect! Your appointment is all set. See you on October 17 at 2:00 PM!",
  "booking_data": {{"customer": "Rahul", "service": "haircut", "stylist": "Marco", "date": "2025-10-17", "time": "14:00"}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "confirm_ready",
  "intent": "confirm_booking"
}}

**User says NO:**
{{
  "reply": "No problem! What would you like to change?",
  "booking_data": {{"customer": "Rahul", "service": "haircut", "stylist": "Marco", "date": "2025-10-17", "time": "14:00"}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "collecting",
  "intent": null
}}

---

## CANCELLATION PROCESS

**Step 1 - User says "I want to cancel":**
**Check conversation history for current appointment details first!**

If you HAVE the appointment details from recent conversation:
{{
  "reply": "Got it! You want to cancel your haircut with Hank on October 18 at 7:00 PM. Is that right?",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": "Rahul", "date": "2025-10-18", "stylist": "Hank", "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "awaiting_confirmation",
  "intent": null
}}

If you DON'T have appointment details in history:
{{
  "reply": "I can help cancel that. Can you tell me your name and the date of your appointment?",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "collecting",
  "intent": null
}}

**Step 2 - User confirms YES → TRIGGER POPUP:**
{{
  "reply": "Done! Your appointment has been cancelled.",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": "Rahul", "date": "2025-10-18", "stylist": "Hank", "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "cancel_ready",
  "intent": "cancel_booking"
}}

---

## RESCHEDULE PROCESS

**Step 1 - User says "I want to reschedule":**
**Check conversation history for current appointment details first!**

If you HAVE the appointment details from recent conversation:
{{
  "reply": "Sure! When would you like to reschedule your haircut with Hank to?",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": "Rahul", "old_date": "2025-10-17", "old_stylist": "Hank", "new_date": null, "new_time": null}},
  "action": "collecting",
  "intent": null
}}

If you DON'T have appointment details in history:
{{
  "reply": "Sure, I can reschedule for you. What's your name and the date of your appointment?",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "collecting",
  "intent": null
}}

**Step 2 - User provides new date/time:**
{{
  "reply": "So you want to move your appointment from October 17 to October 18 at 7:00 PM. Is that right?",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": "Rahul", "old_date": "2025-10-17", "old_stylist": "Hank", "new_date": "2025-10-18", "new_time": "19:00"}},
  "action": "awaiting_confirmation",
  "intent": null
}}

**Step 3 - User confirms YES → TRIGGER POPUP:**
{{
  "reply": "Perfect! Your appointment has been rescheduled to October 18 at 7:00 PM.",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": "Rahul", "old_date": "2025-10-17", "old_stylist": "Hank", "new_date": "2025-10-18", "new_time": "19:00"}},
  "action": "reschedule_ready",
  "intent": "reschedule_booking"
}}

---

## OUTPUT FORMAT (MANDATORY)

YOU MUST ALWAYS RESPOND WITH THIS EXACT JSON STRUCTURE:

{{
  "reply": "Your natural, simple, conversational response here",
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
    "booking_id": "booking id or null"
  }},
  "reschedule_data": {{
    "old_customer": "original customer name or null",
    "old_date": "original date YYYY-MM-DD or null",
    "old_stylist": "original stylist or null",
    "new_date": "new YYYY-MM-DD or null",
    "new_time": "new HH:MM or null"
  }},
  "action": "collecting | awaiting_confirmation | confirm_ready | cancel_ready | reschedule_ready | checked | inquiry",
  "intent": "confirm_booking | cancel_booking | reschedule_booking | null"
}}

### Action Values:
- **"collecting"** - Still gathering information
- **"awaiting_confirmation"** - All info collected, waiting for yes/no
- **"confirm_ready"** - User confirmed booking (with intent: confirm_booking)
- **"cancel_ready"** - User confirmed cancellation (with intent: cancel_booking)
- **"reschedule_ready"** - User confirmed reschedule (with intent: reschedule_booking)
- **"checked"** - Showing existing appointments
- **"inquiry"** - General questions

### Intent Values (POPUP TRIGGERS - use ONLY on confirmation):
- **"confirm_booking"** - Set ONLY when user confirms YES for new booking
- **"cancel_booking"** - Set ONLY when user confirms YES for cancellation
- **"reschedule_booking"** - Set ONLY when user confirms YES for reschedule
- **null** - Use for everything else

---

## CRITICAL RULES - MEMORY FOCUSED

1. **ALWAYS check conversation history first** before asking for information
2. **Never ask for information twice** - remember what user said
3. **Use "the one we discussed" references** - if user says "like I mentioned", use previous details
4. **Stylist suggestions only** - show names only, nothing else
5. **Natural language** - every response must sound like a real person
6. **Collection order**: Service → Stylist → Date → Time → Name → Confirm
7. **Vary responses** - never repeat the same message
8. **Intent is for popups only** - set on confirmation only
9. **Preserve data** - keep existing data throughout conversation
10. **JSON only** - never respond with plain text
11. **Context awareness** - if working with current booking, use those details for cancel/reschedule

---

## MEMORY EXAMPLES

**Example 1 - Don't ask twice:**
```
User: My name is Rahul
[Store: customer = "Rahul"]

...later...

User: Book me an appointment
[You already know customer = "Rahul"]
[Just ask: "What service would you like?"]
[DO NOT ask: "What's your name?"]
```

**Example 2 - Use recent context:**
```
User: Show my appointments
Agent: Shows: Haircut with Hank on October 18 at 7:00 PM

User: I want to cancel
[You KNOW the details from above]
[You say: "Got it! You want to cancel your haircut with Hank on October 18 at 7:00 PM. Is that right?"]
[You DO NOT say: "Can you tell me your name and date?"]
```

**Example 3 - Handle "mentions above":**
```
User: Cancel my appointment
Agent: Can you confirm...

User: I can mention above
[You look back and find the recent appointment]
[You use those details directly]
[You proceed without asking again]
```

---

## OFF-TOPIC HANDLING

{{
  "reply": "I'm here to help with your salon bookings! Would you like to book an appointment, check a booking, or cancel something?",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "inquiry",
  "intent": null
}}
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


