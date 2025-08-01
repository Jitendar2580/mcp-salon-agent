from datetime import datetime
from typing import List
from dotenv import load_dotenv
from groq import Groq
from typing import Dict
from datetime import datetime 
import os
from tools import book_salon
import json
load_dotenv()

API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=API_KEY)


# In-memory storage for appointments and conversations
salon_appointments = {}
conversation_memory = {}


class ConversationMemory:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.messages = []
        self.collected_info = {
            "name": None,
            "date": None,
            "time": None,
            "service": None,
            "stylist": None
        }
        # greeting, collecting, confirming, completed
        self.conversation_state = "greeting"

    def add_message(self, role: str, content: str):
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })

    def update_info(self, key: str, value: str):
        if key in self.collected_info:
            self.collected_info[key] = value

    def get_missing_info(self) -> List[str]:
        return [key for key, value in self.collected_info.items() if value is None]

    def is_complete(self) -> bool:
        return all(value is not None for value in self.collected_info.values())


def get_or_create_memory(session_id: str) -> ConversationMemory:
    """Get existing conversation memory or create new one"""
    if session_id not in conversation_memory:
        conversation_memory[session_id] = ConversationMemory(session_id)
    return conversation_memory[session_id]


def extract_info_from_input(user_input: str, memory: ConversationMemory) -> Dict[str, str]:
    """Extract appointment information from user input using LLM"""
    extraction_prompt = f"""
        Extract appointment information from the user's message. Return ONLY a JSON object with the fields that can be clearly identified.
        Use null for missing information. Format dates as YYYY-MM-DD and times as HH:MM (24-hour format).

        Current collected info: {json.dumps(memory.collected_info)}
        User message: "{user_input}"

        Return format:
        {{"name": "value or null", "date": "value or null", "time": "value or null", "service": "value or null", "stylist": "value or null"}}
    """

    try:
        chat_completion = client.chat.completions.create(
            model=os.getenv("MODEL_NAME", "llama3-70b-8192"),
            messages=[{"role": "user", "content": extraction_prompt}],
            temperature=0.1
        )

        response = chat_completion.choices[0].message.content.strip()
        # Extract JSON from response
        start_idx = response.find('{')
        end_idx = response.rfind('}') + 1
        if start_idx != -1 and end_idx != -1:
            json_str = response[start_idx:end_idx]
            extracted_info = json.loads(json_str)
            return {k: v for k, v in extracted_info.items() if v is not None}
        return {}
    except Exception as e:
        print(f"Extraction error: {e}")
        return {}

 

def get_conversation_summary(session_id: str) -> Dict:
    """Get conversation summary for debugging/monitoring"""
    if session_id in conversation_memory:
        memory = conversation_memory[session_id]
        return {
            "session_id": session_id,
            "state": memory.conversation_state,
            "collected_info": memory.collected_info,
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
 

def generate_response_with_memory(user_input: str, session_id: str) -> str:
    """Generate contextual response based on conversation memory"""
    memory = get_or_create_memory(session_id)
    memory.add_message("user", user_input)
    
    # Extract new information
    extracted_info = extract_info_from_input(user_input, memory)
    for key, value in extracted_info.items():
        memory.update_info(key, value)
    
    # Build conversation context
    recent_messages = memory.messages[-6:]  # Last 3 exchanges
    conversation_context = "\n".join([f"{msg['role']}: {msg['content']}" for msg in recent_messages])
    
    missing_info = memory.get_missing_info()
    
    # Generate contextual prompt
    if memory.is_complete():
        # Ready to book
        prompt = f"""
            You are a friendly salon assistant. The user has provided all necessary information for booking.

            Conversation history:
            {conversation_context}

            Collected information:
            - Name: {memory.collected_info['name']}
            - Date: {memory.collected_info['date']}
            - Time: {memory.collected_info['time']}
            - Service: {memory.collected_info['service']}
            - Stylist: {memory.collected_info['stylist']}

            Confirm the booking details and proceed to book the appointment using the salon_booking tool.
            """
        memory.conversation_state = "confirming"
        
        # Make the booking
        booking_result = book_salon(
            memory.collected_info['name'],
            memory.collected_info['date'], 
            memory.collected_info['time'],
            memory.collected_info['service'],
            memory.collected_info['stylist']
        )
        
        response = f"Perfect! Let me confirm your appointment details:\n\n"
        response += f"📅 **Name:** {memory.collected_info['name']}\n"
        response += f"📅 **Date:** {memory.collected_info['date']}\n"
        response += f"🕐 **Time:** {memory.collected_info['time']}\n"
        response += f"💄 **Service:** {memory.collected_info['service']}\n\n"
        response += f"💄 **Stylist:** {memory.collected_info['stylist']}\n\n"
        response += f"{booking_result}\n\n"
        response += "Is there anything else I can help you with today?"
        
        memory.conversation_state = "completed"
        
    elif len(missing_info) > 0:
        # Still collecting information
        memory.conversation_state = "collecting"
        
        prompt = f"""
            You are a friendly salon assistant helping a customer book an appointment.

            Conversation history:
            {conversation_context}

            Information collected so far:
            {json.dumps({k: v for k, v in memory.collected_info.items() if v is not None}, indent=2)}

            Still need: {', '.join(missing_info)}

            Continue the conversation naturally, asking for the missing information one piece at a time. 
            Be conversational and helpful. If they provided some info, acknowledge it before asking for what's missing.
            """
        
        try:
            chat_completion = client.chat.completions.create(
                model=os.getenv("MODEL_NAME", "llama3-70b-8192"),
                messages=[
                    {"role": "system", "content": "You are a helpful salon assistant. Be friendly, conversational, and ask for missing appointment details naturally."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5
            )
            response = chat_completion.choices[0].message.content.strip()
        except Exception as e:
            response = f"I'd be happy to help you book an appointment. Could you please provide your {missing_info[0]}?"
    
    else:
        # Initial greeting
        response = "Hello! Welcome to our salon. I'd be happy to help you book an appointment. What service are you interested in today?"
        memory.conversation_state = "greeting"
    
    memory.add_message("assistant", response)
    return response


# Example usage:
# if __name__ == "__main__":
#     # Simulate conversation
#     session_id = "user123"
    
#     print("=== Salon Booking Conversation ===")
    
#     # Conversation flow
#     responses = [
#         route_query_to_tool_2("Hi, I want to book an appointment", session_id),
#         route_query_to_tool_2("I want a haircut", session_id),
#         route_query_to_tool_2("My name is John Smith", session_id),
#         route_query_to_tool_2("How about tomorrow at 2pm?", session_id),
#         route_query_to_tool_2("Actually, make it 3pm on December 15th, 2024", session_id)
#     ]
    
#     for i, response in enumerate(responses, 1):
#         print(f"\nResponse {i}: {response}")
    
#     # Show conversation summary
#     print(f"\nConversation Summary: {get_conversation_summary(session_id)}")
#     print(f"\nBookings: {salon_appointments}")
