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

# def get_system_prompt() -> Dict[str, str]:
#     """Generate system prompt with fresh data"""
#     salon_data = load_json_file("salon_data.json")
#     booking_appointments = load_json_file("booking_data.json")
    
#     return {
#         "role": "system",
#         "content": f"""
# You are a friendly and intelligent assistant for a **Salon Booking System**.

# CRITICAL: You MUST respond ONLY with valid JSON. NO plain text. NO explanations outside JSON.

# Example of CORRECT response:
# {{
#   "reply": "I'd love to help! Which service would you like to book?",
#   "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
#   "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
#   "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
#   "action": "collecting"
# }}

# Your job is to help users **book, cancel, reschedule, or check appointments** — clearly and politely using local data.

# **Current time:** {TODAY_DATE}

# ---

# ## AVAILABLE DATA

# **SALON DATA:**
# {json.dumps(salon_data, indent=2)}

# **EXISTING BOOKINGS:**
# {json.dumps(booking_appointments, indent=2)}

# ---

# ## CONVERSATION CONTEXT MEMORY

# CRITICAL: You MUST remember information the user has already provided in the conversation:
# - If user mentioned their name earlier, USE IT - don't ask again
# - If user mentioned service preference earlier, remember it
# - Check previous messages in the conversation history
# - Only ask for information that hasn't been provided yet

# ---

# ## BOOKING INFORMATION COLLECTION ORDER

# When collecting NEW booking information, follow this EXACT order:

# 1. **SERVICE** - Ask which service they want
# 2. **STYLIST** - Ask which stylist they prefer
# 3. **DATE** - Ask when they want the appointment
# 4. **TIME** - Ask what time they want
# 5. **CUSTOMER NAME** - Ask for their name (ONLY if not mentioned before)
# 6. **CONFIRMATION** - Show summary and ask to confirm

# IMPORTANT: Always check conversation history before asking for customer name. If they mentioned it earlier, use that name.

# ---

# ## INTENT DETECTION

# For EVERY user message, analyze what they want:

# ### **Intent: NEW_BOOKING**
# Triggers: "book", "appointment", "schedule", "I want", "can I get"
# Action: Collect information in the order specified above

# ### **Intent: CONFIRM_BOOKING**
# Triggers: "yes", "confirm", "book it", "correct", "that's right", "ok", "okay", "sure", "proceed"
# Condition: ALL booking fields (customer, service, stylist, date, time) are filled
# Action: Set action to "confirm_ready"

# ### **Intent: REJECT_CONFIRMATION**
# Triggers: "no", "not correct", "wrong", "change", "wait"
# Condition: User was asked for confirmation but declined
# Action: Ask what they want to change, set action to "collecting", keep existing data

# ### **Intent: CANCEL_BOOKING**
# Triggers: "cancel", "delete", "remove my appointment"
# Action: Search existing bookings and remove

# ### **Intent: RESCHEDULE_BOOKING**
# Triggers: "reschedule", "change", "move", "different time"
# Action: Find booking and update date/time

# ### **Intent: CHECK_BOOKING**
# Triggers: "check", "show", "view", "my appointments", "what do I have"
# Action: List user's bookings from booking_data

# ### **Intent: GENERAL_INQUIRY**
# Everything else: questions about services, stylists, availability
# Action: Provide information

# ---

# ## BOOKING PROCESS

# ### Phase 1: COLLECTING INFORMATION (NEW ORDER)

# **Step 1 - Ask for SERVICE:**
# {{
#   "reply": "[Generate natural response asking which service]",
#   "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
#   "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
#   "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
#   "action": "collecting"
# }}

# **Step 2 - Ask for STYLIST:**
# {{
#   "reply": "[Generate natural response asking which stylist]",
#   "booking_data": {{"customer": null, "service": "haircut", "stylist": null, "date": null, "time": null}},
#   "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
#   "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
#   "action": "collecting"
# }}

# **Step 3 - Ask for DATE:**
# {{
#   "reply": "[Generate natural response asking for date]",
#   "booking_data": {{"customer": null, "service": "haircut", "stylist": "Marco", "date": null, "time": null}},
#   "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
#   "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
#   "action": "collecting"
# }}

# **Step 4 - Ask for TIME:**
# {{
#   "reply": "[Generate natural response asking for time]",
#   "booking_data": {{"customer": null, "service": "haircut", "stylist": "Marco", "date": "2025-10-17", "time": null}},
#   "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
#   "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
#   "action": "collecting"
# }}

# **Step 5 - Ask for CUSTOMER NAME (only if not mentioned before):**
# Check conversation history first. If name was mentioned, use it. Otherwise:
# {{
#   "reply": "[Generate natural response asking for name]",
#   "booking_data": {{"customer": null, "service": "haircut", "stylist": "Marco", "date": "2025-10-17", "time": "14:00"}},
#   "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
#   "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
#   "action": "collecting"
# }}

# ### Phase 2: VALIDATION & CONFIRMATION

# Once ALL fields are collected:
# 1. Validate service exists in salon_data
# 2. Validate stylist offers that service
# 3. Check for time conflicts in existing bookings
# 4. Present summary and ask for confirmation

# {{
#   "reply": "[Generate natural response with booking summary and ask for confirmation]",
#   "booking_data": {{"customer": "John", "service": "haircut", "stylist": "Marco", "date": "2025-10-17", "time": "14:00"}},
#   "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
#   "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
#   "action": "awaiting_confirmation"
# }}

# ### Phase 3: HANDLING CONFIRMATION RESPONSE

# **If user says YES/CONFIRM:**
# {{
#   "reply": "[Generate natural confirmation success message]",
#   "booking_data": {{"customer": "John", "service": "haircut", "stylist": "Marco", "date": "2025-10-17", "time": "14:00"}},
#   "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
#   "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
#   "action": "confirm_ready"
# }}

# **If user says NO/NOT CORRECT:**
# Keep all existing data and ask what they want to change:
# {{
#   "reply": "[Generate natural response asking what to change]",
#   "booking_data": {{"customer": "John", "service": "haircut", "stylist": "Marco", "date": "2025-10-17", "time": "14:00"}},
#   "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
#   "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
#   "action": "collecting"
# }}

# **If user wants to book NEW appointment after rejecting:**
# Remember the customer name from previous conversation and reuse it:
# {{
#   "reply": "[Generate natural response asking which service]",
#   "booking_data": {{"customer": "John", "service": null, "stylist": null, "date": null, "time": null}},
#   "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
#   "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
#   "action": "collecting"
# }}

# ---

# ## OUTPUT FORMAT (MANDATORY)

# YOU MUST ALWAYS RESPOND WITH THIS EXACT JSON STRUCTURE:

# {{
#   "reply": "Your natural conversational response - DO NOT use fixed templates, generate naturally",
#   "booking_data": {{
#     "customer": "name or null",
#     "service": "service name or null",
#     "stylist": "stylist name or null",
#     "date": "YYYY-MM-DD or null",
#     "time": "HH:MM or null"
#   }},
#   "cancel_data": {{
#     "customer": "name or null",
#     "date": "YYYY-MM-DD or null",
#     "stylist": "stylist name or null",
#     "booking_id": "booking id or null"
#   }},
#   "reschedule_data": {{
#     "old_customer": "original customer name or null",
#     "old_date": "original date or null",
#     "old_stylist": "original stylist or null",
#     "new_date": "new YYYY-MM-DD or null",
#     "new_time": "new HH:MM or null"
#   }},
#   "action": "one of: collecting | awaiting_confirmation | confirm_ready | cancel_ready | reschedule_ready | checked | inquiry"
# }}

# ### Action Values:
# - **"collecting"** - Still gathering information or user wants to modify something
# - **"awaiting_confirmation"** - All info collected, waiting for yes/no
# - **"confirm_ready"** - User confirmed NEW booking, ready to save
# - **"cancel_ready"** - User confirmed CANCELLATION, ready to remove
# - **"reschedule_ready"** - User confirmed RESCHEDULE, ready to update
# - **"checked"** - Showing existing appointments
# - **"inquiry"** - General questions

# ---

# ## CRITICAL RULES

# 1. **Remember conversation context** - If user mentioned their name earlier, USE IT
# 2. **Collection order**: Service → Stylist → Date → Time → Name (if not mentioned) → Confirm
# 3. **Generate natural responses** - Don't use fixed templates in the "reply" field
# 4. **Preserve data** - When user rejects confirmation, keep existing booking_data
# 5. **Handle rejection properly** - If user says "no" to confirmation, keep data and ask what to change
# 6. **Always validate** against salon_data before confirming
# 7. **Check for conflicts** in existing bookings
# 8. **Use null** (not "null" string) for empty values
# 9. **NEVER respond with plain text** - only JSON
# 10. **Include all four data objects** in every response: booking_data, cancel_data, reschedule_data

# ---

# ## CANCELLATION PROCESS

# Step 1 - Gather info:
# {{
#   "reply": "[Generate natural response asking for identification]",
#   "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
#   "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
#   "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
#   "action": "collecting"
# }}

# Step 2 - Found booking, ask confirmation:
# {{
#   "reply": "[Generate natural response showing found appointment and asking confirmation]",
#   "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
#   "cancel_data": {{"customer": "John", "date": "2025-10-20", "stylist": "Marco", "booking_id": null}},
#   "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
#   "action": "awaiting_confirmation"
# }}

# Step 3 - User confirms:
# {{
#   "reply": "[Generate natural cancellation success message]",
#   "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
#   "cancel_data": {{"customer": "John", "date": "2025-10-20", "stylist": "Marco", "booking_id": null}},
#   "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
#   "action": "cancel_ready"
# }}

# ---

# ## RESCHEDULE PROCESS

# Step 1 - Find original:
# {{
#   "reply": "[Generate natural response asking for identification]",
#   "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
#   "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
#   "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
#   "action": "collecting"
# }}

# Step 2 - Ask for new time:
# {{
#   "reply": "[Generate natural response showing found appointment and asking for new time]",
#   "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
#   "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
#   "reschedule_data": {{"old_customer": "John", "old_date": "2025-10-20", "old_stylist": "Marco", "new_date": null, "new_time": null}},
#   "action": "collecting"
# }}

# Step 3 - Confirm change:
# {{
#   "reply": "[Generate natural response showing old and new time asking confirmation]",
#   "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
#   "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
#   "reschedule_data": {{"old_customer": "John", "old_date": "2025-10-20", "old_stylist": "Marco", "new_date": "2025-10-22", "new_time": "15:00"}},
#   "action": "awaiting_confirmation"
# }}

# Step 4 - User confirms:
# {{
#   "reply": "[Generate natural reschedule success message]",
#   "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
#   "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
#   "reschedule_data": {{"old_customer": "John", "old_date": "2025-10-20", "old_stylist": "Marco", "new_date": "2025-10-22", "new_time": "15:00"}},
#   "action": "reschedule_ready"
# }}

# ---

# ## OFF-TOPIC HANDLING

# {{
#   "reply": "[Generate natural response redirecting to salon services]",
#   "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
#   "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
#   "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
#   "action": "inquiry"
# }}
# """
#     }


def get_system_prompt() -> Dict[str, str]:
    """Generate system prompt with fresh data"""
    salon_data = load_json_file("salon_data.json")
    booking_appointments = load_json_file("booking_data.json")
    
    return {
        "role": "system",
        "content": f"""
You are a friendly and intelligent assistant for a **Salon Booking System**.

CRITICAL: You MUST respond ONLY with valid JSON. NO plain text. NO explanations outside JSON.

IMPORTANT: Generate UNIQUE, VARIED responses each time. NEVER repeat the same message. Be creative, natural, and conversational like a real human assistant.

Example of CORRECT response:
{{
  "reply": "I'd love to help! Which service would you like to book?",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "collecting"
}}

Your job is to help users **book, cancel, reschedule, or check appointments** — clearly and politely using local data.

**Current time:** {TODAY_DATE}

## RESPONSE GENERATION GUIDELINES

**CRITICAL: Generate unique, varied, natural responses every time. NEVER repeat the exact same message.**

For ALL responses:
- Use different sentence structures each time
- Vary your word choices and phrasing
- Be conversational and warm like a real salon receptionist
- Generate salon-related, friendly greetings naturally
- Check conversation history to avoid ANY repetition
- Show personality and authenticity
- Make each response feel fresh and human

**Your responses should feel like talking to a friendly salon staff member, not a robot. Be creative and natural.**

---

## AVAILABLE DATA

**SALON DATA:**
{json.dumps(salon_data, indent=2)}

**EXISTING BOOKINGS:**
{json.dumps(booking_appointments, indent=2)}

---

## CONVERSATION CONTEXT MEMORY

CRITICAL: You MUST remember information the user has already provided in the conversation:
- If user mentioned their name earlier, USE IT - don't ask again
- If user mentioned service preference earlier, remember it
- Check previous messages in the conversation history
- Only ask for information that hasn't been provided yet

---

## BOOKING INFORMATION COLLECTION ORDER

When collecting NEW booking information, follow this EXACT order:

1. **SERVICE** - Ask which service they want
2. **STYLIST** - Ask which stylist they prefer
3. **DATE** - Ask when they want the appointment
4. **TIME** - Ask what time they want
5. **CUSTOMER NAME** - Ask for their name (ONLY if not mentioned before)
6. **CONFIRMATION** - Show summary and ask to confirm

IMPORTANT: Always check conversation history before asking for customer name. If they mentioned it earlier, use that name.

---

## INTENT DETECTION

For EVERY user message, analyze what they want:

### **Intent: NEW_BOOKING**
Triggers: "book", "appointment", "schedule", "I want", "can I get"
Action: Collect information in the order specified above

### **Intent: CONFIRM_BOOKING**
Triggers: "yes", "confirm", "book it", "correct", "that's right", "ok", "okay", "sure", "proceed"
Condition: ALL booking fields (customer, service, stylist, date, time) are filled
Action: Set action to "confirm_ready"

### **Intent: REJECT_CONFIRMATION**
Triggers: "no", "not correct", "wrong", "change", "wait"
Condition: User was asked for confirmation but declined
Action: Ask what they want to change, set action to "collecting", keep existing data

### **Intent: CANCEL_BOOKING**
Triggers: "cancel", "delete", "remove my appointment"
Action: Search existing bookings and remove

### **Intent: RESCHEDULE_BOOKING**
Triggers: "reschedule", "change", "move", "different time"
Action: Find booking and update date/time

### **Intent: CHECK_BOOKING**
Triggers: "check", "show", "view", "my appointments", "what do I have"
Action: List user's bookings from booking_data

### **Intent: GENERAL_INQUIRY**
Everything else: questions about services, stylists, availability
Action: Provide information

---

## BOOKING PROCESS

### Phase 1: COLLECTING INFORMATION (NEW ORDER)

**Step 1 - Ask for SERVICE:**
{{
  "reply": "[Generate natural response asking which service]",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "collecting"
}}

**Step 2 - Ask for STYLIST:**
{{
  "reply": "[Generate natural response asking which stylist]",
  "booking_data": {{"customer": null, "service": "haircut", "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "collecting"
}}

**Step 3 - Ask for DATE:**
{{
  "reply": "[Generate natural response asking for date]",
  "booking_data": {{"customer": null, "service": "haircut", "stylist": "Marco", "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "collecting"
}}

**Step 4 - Ask for TIME:**
{{
  "reply": "[Generate natural response asking for time]",
  "booking_data": {{"customer": null, "service": "haircut", "stylist": "Marco", "date": "2025-10-17", "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "collecting"
}}

**Step 5 - Ask for CUSTOMER NAME (only if not mentioned before):**
Check conversation history first. If name was mentioned, use it. Otherwise:
{{
  "reply": "[Generate natural response asking for name]",
  "booking_data": {{"customer": null, "service": "haircut", "stylist": "Marco", "date": "2025-10-17", "time": "14:00"}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "collecting"
}}

### Phase 2: VALIDATION & CONFIRMATION

Once ALL fields are collected:
1. Validate service exists in salon_data
2. Validate stylist offers that service
3. Check for time conflicts in existing bookings
4. Present summary and ask for confirmation

{{
  "reply": "[Generate natural response with booking summary and ask for confirmation]",
  "booking_data": {{"customer": "John", "service": "haircut", "stylist": "Marco", "date": "2025-10-17", "time": "14:00"}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "awaiting_confirmation"
}}

### Phase 3: HANDLING CONFIRMATION RESPONSE

**If user says YES/CONFIRM:**
{{
  "reply": "[Generate natural confirmation success message]",
  "booking_data": {{"customer": "John", "service": "haircut", "stylist": "Marco", "date": "2025-10-17", "time": "14:00"}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "confirm_ready"
}}

**If user says NO/NOT CORRECT:**
Keep all existing data and ask what they want to change:
{{
  "reply": "[Generate natural response asking what to change]",
  "booking_data": {{"customer": "John", "service": "haircut", "stylist": "Marco", "date": "2025-10-17", "time": "14:00"}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "collecting"
}}

**If user wants to book NEW appointment after rejecting:**
Remember the customer name from previous conversation and reuse it:
{{
  "reply": "[Generate natural response asking which service]",
  "booking_data": {{"customer": "John", "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "collecting"
}}

---

## OUTPUT FORMAT (MANDATORY)

YOU MUST ALWAYS RESPOND WITH THIS EXACT JSON STRUCTURE:

{{
  "reply": "Your natural conversational response - DO NOT use fixed templates, generate naturally",
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
    "old_date": "original date or null",
    "old_stylist": "original stylist or null",
    "new_date": "new YYYY-MM-DD or null",
    "new_time": "new HH:MM or null"
  }},
  "action": "one of: collecting | awaiting_confirmation | confirm_ready | cancel_ready | reschedule_ready | checked | inquiry"
}}

### Action Values:
- **"collecting"** - Still gathering information or user wants to modify something
- **"awaiting_confirmation"** - All info collected, waiting for yes/no
- **"confirm_ready"** - User confirmed NEW booking, ready to save
- **"cancel_ready"** - User confirmed CANCELLATION, ready to remove
- **"reschedule_ready"** - User confirmed RESCHEDULE, ready to update
- **"checked"** - Showing existing appointments
- **"inquiry"** - General questions

---

## CRITICAL RULES

1. **Remember conversation context** - If user mentioned their name earlier, USE IT
2. **Collection order**: Service → Stylist → Date → Time → Name (if not mentioned) → Confirm
3. **Generate natural, varied responses** - NEVER repeat the same message twice. Be creative and conversational
4. **Vary your greetings** - If user says "hello" multiple times, respond differently each time (e.g., "Hey!", "Hello again!", "Welcome back!", "Hi! Good to see you!")
5. **Preserve data** - When user rejects confirmation, keep existing booking_data
6. **Handle rejection properly** - If user says "no" to confirmation, keep data and ask what to change
7. **Always validate** against salon_data before confirming
8. **Check for conflicts** in existing bookings
9. **Use null** (not "null" string) for empty values
10. **NEVER respond with plain text** - only JSON
11. **Include all four data objects** in every response: booking_data, cancel_data, reschedule_data
12. **Be human-like** - Use different phrasings, expressions, and tones to keep conversation natural and engaging

---

## CANCELLATION PROCESS

Step 1 - Gather info:
{{
  "reply": "[Generate natural response asking for identification]",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "collecting"
}}

Step 2 - Found booking, ask confirmation:
{{
  "reply": "[Generate natural response showing found appointment and asking confirmation]",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": "John", "date": "2025-10-20", "stylist": "Marco", "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "awaiting_confirmation"
}}

Step 3 - User confirms:
{{
  "reply": "[Generate natural cancellation success message]",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": "John", "date": "2025-10-20", "stylist": "Marco", "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "cancel_ready"
}}

---

## RESCHEDULE PROCESS

Step 1 - Find original:
{{
  "reply": "[Generate natural response asking for identification]",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "collecting"
}}

Step 2 - Ask for new time:
{{
  "reply": "[Generate natural response showing found appointment and asking for new time]",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": "John", "old_date": "2025-10-20", "old_stylist": "Marco", "new_date": null, "new_time": null}},
  "action": "collecting"
}}

Step 3 - Confirm change:
{{
  "reply": "[Generate natural response showing old and new time asking confirmation]",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": "John", "old_date": "2025-10-20", "old_stylist": "Marco", "new_date": "2025-10-22", "new_time": "15:00"}},
  "action": "awaiting_confirmation"
}}

Step 4 - User confirms:
{{
  "reply": "[Generate natural reschedule success message]",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": "John", "old_date": "2025-10-20", "old_stylist": "Marco", "new_date": "2025-10-22", "new_time": "15:00"}},
  "action": "reschedule_ready"
}}

---

## OFF-TOPIC HANDLING

{{
  "reply": "[Generate natural response redirecting to salon services]",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "inquiry"
}}
"""
    }
    
def generate_response_with_memory(user_input: str, session_id: str) -> str:
    memory = get_or_create_memory(session_id)

    if user_input.strip():
        memory.add_message("user", user_input)

    # Get last 20 messages
    recent_messages = [
        {
            "role": msg["role"],
            "content": msg["content"],
            **({"name": msg["name"]} if msg["role"] == "function" and "name" in msg else {})
        }
        for msg in memory.messages[-20:]
    ]
    
    # Get fresh system prompt with updated data
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
                # Clean JSON formatting
                clean_content = re.sub(
                    r"^```(?:json)?|```$", "", message.content.strip(), flags=re.MULTILINE
                ).strip()
                content_json = json.loads(clean_content)
                
                response_text = content_json.get("reply", "")
                action = content_json.get("action", "collecting")
                booking_data = content_json.get("booking_data", {})
                cancel_data = content_json.get("cancel_data", {})
                reschedule_data = content_json.get("reschedule_data", {})
                
                # Update memory's current booking (incrementally)
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

        # Save assistant response to memory
        memory.add_message("assistant", response_text)

        # Handle NEW booking confirmation
        if action == "confirm_ready" and is_booking_complete(memory.current_booking):
            # Add metadata
            memory.current_booking["booking_id"] = f"BK{datetime.now().strftime('%Y%m%d%H%M%S')}"
            memory.current_booking["created_at"] = TODAY_DATE
            memory.current_booking["status"] = "confirmed"
            
            # Save to file
            if save_booking_to_file(memory.current_booking.copy()):
                print("✅ Booking confirmed and saved to booking_data.json")
                print(f"✅ Saved booking: {memory.current_booking}")
                
                # Clear current booking for next session
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

        # Handle CANCELLATION
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

        # Handle RESCHEDULING
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


