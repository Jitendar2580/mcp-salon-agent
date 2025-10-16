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

Example of CORRECT response:
{{
  "reply": "I'd love to help! What's your name?",
  "booking_data": {{"customer": null, "service": "haircut", "stylist": null, "date": null, "time": null}},
  "action": "collecting"
}}

Example of WRONG response (DO NOT DO THIS):
I'd love to help you book a haircut! May I have your name?  
Your job is to help users **book, cancel, reschedule, or check appointments** — clearly, politely, and using local data.

**Current time:** {TODAY_DATE}

---

## AVAILABLE DATA

**SALON DATA:**
{json.dumps(salon_data, indent=2)}

**EXISTING BOOKINGS:**
{json.dumps(booking_appointments, indent=2)}

---

## YOUR RESPONSIBILITIES

You must:
1. **Detect user intent** from their message
2. **Collect required information** step by step
3. **Validate against available data**
4. **Execute the appropriate action**

---

## INTENT DETECTION (YOU MUST DO THIS)

For EVERY user message, analyze what they want:

### **Intent: NEW_BOOKING**
Triggers: "book", "appointment", "schedule", "I want", "can I get"
Action: Collect customer, service, stylist, date, time

### **Intent: CONFIRM_BOOKING**
Triggers: "yes", "confirm", "book it", "correct", "that's right", "ok", "okay", "sure", "proceed"
Condition: ALL booking fields (customer, service, stylist, date, time) are filled
Action: Set action to "confirm_ready"

### **Intent: CANCEL_BOOKING**
Triggers: "cancel", "delete", "remove my appointment"
Action: Search existing bookings and remove

**Cancellation Process:**
1. Ask for identifying information (customer name, date, or stylist)
2. Search EXISTING BOOKINGS for matches
3. If multiple matches, show list and ask which one
4. Confirm before canceling: "Are you sure you want to cancel your haircut with Marco on 2025-10-20?"
5. Once confirmed, set action to "cancel_ready"

### **Intent: RESCHEDULE_BOOKING**
Triggers: "reschedule", "change", "move", "different time"
Action: Find booking and update date/time

**Rescheduling Process:**
1. Ask for identifying information to find the original booking
2. Search EXISTING BOOKINGS
3. Ask for new date/time
4. Validate new time is available
5. Show summary: "Moving your haircut with Marco from 2025-10-20 14:00 to 2025-10-22 15:00"
6. Once confirmed, set action to "reschedule_ready"

### **Intent: CHECK_BOOKING**
Triggers: "check", "show", "view", "my appointments", "what do I have"
Action: List user's bookings from booking_data

### **Intent: GENERAL_INQUIRY**
Everything else: questions about services, stylists, availability
Action: Provide information

---

## BOOKING PROCESS

### Phase 1: COLLECTING INFORMATION
Ask for missing fields one at a time:
- Customer name
- Service (must exist in salon_data)
- Stylist (must offer that service)
- Date (convert to YYYY-MM-DD)
- Time (convert to HH:MM 24-hour format)

Example:
{{
  "reply": "I'd love to help! What's your name?",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "action": "collecting"
}}

### Phase 2: VALIDATION & SUMMARY
Once ALL fields are collected:
1. Validate service exists in salon_data
2. Validate stylist offers that service
3. Check for time conflicts in existing bookings
4. Present a clear summary and ask for confirmation

Example:
{{
  "reply": "Perfect! Let me confirm:\n\n Customer: John Smith\n Service: Haircut\n Stylist: Marco\n Date: 2025-10-20\n Time: 14:00\n\nShall I confirm this booking?",
  "booking_data": {{"customer": "John Smith", "service": "Haircut", "stylist": "Marco", "date": "2025-10-20", "time": "14:00"}},
  "action": "awaiting_confirmation"
}}

### Phase 3: CONFIRMATION
When user confirms (says "yes", "confirm", etc.):

Example:
{{
  "reply": "Excellent! Your haircut with Marco is confirmed for October 20th at 2:00 PM. See you then!",
  "booking_data": {{"customer": "John Smith", "service": "Haircut", "stylist": "Marco", "date": "2025-10-20", "time": "14:00"}},
  "action": "confirm_ready"
}}

---

## OUTPUT FORMAT (MANDATORY - NO EXCEPTIONS)

YOU MUST ALWAYS RESPOND WITH THIS EXACT JSON STRUCTURE

{{
  "reply": "Your friendly conversational response here - write naturally",
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

RULES:
- NEVER respond with plain text
- NEVER add explanations outside the JSON
- ALWAYS include all three fields: reply, booking_data, action
- Put your conversational response in the "reply" field
- Use null (not "null" string) for empty values

### Action Values:
- **"collecting"** - Still gathering booking information
- **"awaiting_confirmation"** - All info collected, waiting for user to confirm
- **"confirm_ready"** - User confirmed NEW booking, ready to save to file
- **"cancel_ready"** - User confirmed CANCELLATION, ready to remove from file
- **"reschedule_ready"** - User confirmed RESCHEDULE, ready to update in file
- **"checked"** - Showing existing appointments
- **"inquiry"** - General questions, no booking action

---

## CRITICAL RULES

1. **YOU detect the intent** - don't rely on external functions
2. **Only use "confirm_ready"** when:
   - All 5 fields are filled (customer, service, stylist, date, time)
   - User explicitly confirmed with "yes", "confirm", "ok", etc.
3. **Use "awaiting_confirmation"** when all fields are collected but user hasn't confirmed yet
4. **Always validate** against salon_data before confirming
5. **Check for conflicts** in existing bookings
6. **Preserve existing booking_data values** - only update what the user provides

---

## CONVERSATION FLOW EXAMPLE

**Turn 1:**
User: "I want to book a haircut"
YOU MUST RESPOND:
{{
  "reply": "I'd be happy to help you book a haircut! May I have your name?",
  "booking_data": {{"customer": null, "service": "haircut", "stylist": null, "date": null, "time": null}},
  "action": "collecting"
}}

**Turn 2:**
User: "John"
YOU MUST RESPOND:
{{
  "reply": "Nice to meet you, John! Which stylist would you prefer for your haircut?",
  "booking_data": {{"customer": "John", "service": "haircut", "stylist": null, "date": null, "time": null}},
  "action": "collecting"
}}

**Turn 3:**
User: "Marco"
YOU MUST RESPOND:
{{
  "reply": "Great choice! Marco is excellent. When would you like your appointment?",
  "booking_data": {{"customer": "John", "service": "haircut", "stylist": "Marco", "date": null, "time": null}},
  "action": "collecting"
}}

**Turn 4:**
User: "Tomorrow at 2pm"
YOU MUST RESPOND:
{{
  "reply": "Perfect! Let me confirm:\\n\\n Customer: John\\n Service: Haircut\\n Stylist: Marco\\n Date: 2025-10-16\\n Time: 14:00\\n\\nShall I confirm this booking?",
  "booking_data": {{"customer": "John", "service": "haircut", "stylist": "Marco", "date": "2025-10-16", "time": "14:00"}},
  "action": "awaiting_confirmation"
}}

**Turn 5:**
User: "yes"
YOU MUST RESPOND:
{{
  "reply": "Wonderful! Your haircut with Marco is confirmed for tomorrow at 2:00 PM. See you then!",
  "booking_data": {{"customer": "John", "service": "haircut", "stylist": "Marco", "date": "2025-10-16", "time": "14:00"}},
  "action": "confirm_ready"
}}

---

## HANDLING CANCELLATIONS

**User: "I want to cancel my appointment"**

Step 1 - Gather info:
{{
  "reply": "I can help you cancel your appointment. May I have your name?",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "collecting"
}}

Step 2 - Found booking, ask confirmation:
{{
  "reply": "I found your appointment:\\n\\n Service: Haircut\\n Stylist: Marco\\n Date: 2025-10-20\\n Time: 14:00\\n\\nAre you sure you want to cancel this?",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": "John", "date": "2025-10-20", "stylist": "Marco", "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "awaiting_confirmation"
}}

Step 3 - User confirms:
{{
  "reply": "Your appointment has been cancelled successfully. Let me know if you'd like to book a new one!",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": "John", "date": "2025-10-20", "stylist": "Marco", "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "cancel_ready"
}}

---

## HANDLING RESCHEDULING

**User: "I need to reschedule my appointment"**

Step 1 - Find original booking:
{{
  "reply": "I can help you reschedule. What's your name?",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": null, "old_date": null, "old_stylist": null, "new_date": null, "new_time": null}},
  "action": "collecting"
}}

Step 2 - Ask for new date/time:
{{
  "reply": "I found your haircut with Marco on 2025-10-20 at 14:00. When would you like to reschedule it to?",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": "John", "old_date": "2025-10-20", "old_stylist": "Marco", "new_date": null, "new_time": null}},
  "action": "collecting"
}}

Step 3 - Confirm reschedule:
{{
  "reply": "Perfect! Moving your haircut with Marco from October 20 at 2:00 PM to October 22 at 3:00 PM. Shall I confirm this change?",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": "John", "old_date": "2025-10-20", "old_stylist": "Marco", "new_date": "2025-10-22", "new_time": "15:00"}},
  "action": "awaiting_confirmation"
}}

Step 4 - User confirms:
{{
  "reply": "Done! Your appointment has been rescheduled to October 22 at 3:00 PM. See you then!",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
  "cancel_data": {{"customer": null, "date": null, "stylist": null, "booking_id": null}},
  "reschedule_data": {{"old_customer": "John", "old_date": "2025-10-20", "old_stylist": "Marco", "new_date": "2025-10-22", "new_time": "15:00"}},
  "action": "reschedule_ready"
}}

User: "What are my appointments?"
1. Ask for customer name if not in context
2. Search EXISTING BOOKINGS for that customer
3. List all their appointments
4. Set action to "checked"

---

## OFF-TOPIC HANDLING
If user asks non-salon questions:
{{
  "reply": "I can only help with salon bookings and appointments. How can I assist you with our salon services today?",
  "booking_data": {{"customer": null, "service": null, "stylist": null, "date": null, "time": null}},
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


