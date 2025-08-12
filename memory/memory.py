
from typing import Any, List, Optional, Tuple
from dotenv import load_dotenv
from tools import tools
from typing import Dict 
import os , re
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
	api_key=os.getenv("OPENAI_API_KEY"), # Make sure to set your API key
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
		self.conversation_state = "greeting"  # greeting, collecting, confirming, completed

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
				print(f"⚠️ memory.update_info: Unknown key '{key}' -> skipped (value={value})")
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


def generate_response_with_memory(user_input: str, session_id: str) -> str:
    """Generate contextual response based on conversation memory"""
    memory = get_or_create_memory(session_id)
    memory.add_message("user", user_input)
 
    openai_tools = []
    for tool_name, tool_info in tools.items():
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool_name,
                "description": tool_info["description"],
                "parameters": tool_info["parameters"]
            }
        })

    # Build message history
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
        if message.content:
            try:
                content_json = json.loads(message.content)

                # Update booking_data internally
                booking_data = content_json.get("booking_data")
                if booking_data:
                    for key, value in booking_data.items():
                        if value is not None:
                            memory.current_booking[key] = value
                    print("Updated booking_data from LLM response:", memory.current_booking)

                # Only keep reply for user output
                response = content_json.get("reply", "").strip()

            except json.JSONDecodeError:
                # Not JSON — use raw text
                response = message.content.strip()

        # Handle tool calls if any
        if message.tool_calls:
            print("🚨 Tool call was requested🚨", message.tool_calls)
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)
                result = handle_tool_call(tool_name, tool_args)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

            # Execute the tool function and prepare reply
            if tool_name in tools:
                if tool_name == "book_salon":
                    reply = result
                elif tool_name == "show_appointments":
                    reply = result
                elif tool_name == "cancel_appointment":
                    reply = result
                elif tool_name == "reschedule_appointment":
                    reply = result
                elif tool_name == "get_services":
                    if result and isinstance(result, dict) and result.get('services'):
                        services = result['services']
                        if services and hasattr(services[0], '__dict__'):
                            result['services'] = [
                                {"id": s.id, "name": s.name, "description": s.description}
                                for s in services
                            ]
                        memory.add_message("function", json.dumps(result), name=tool_name)
                        return generate_response_with_memory("", session_id)
                    else:
                        memory.add_message("assistant", "⚠️ No services found matching your request.")
                        return result.get("message", "No services found.")

                elif tool_name == "get_stylist":
                    if result and isinstance(result, dict) and result.get('stylists'):
                        stylists = result['stylists']
                        if stylists and hasattr(stylists[0], '__dict__'):
                            result['stylists'] = [
                                {"id": s.id, "name": s.name, "description": s.description}
                                for s in stylists
                            ]
                        memory.add_message("function", json.dumps(result), name=tool_name)
                        return generate_response_with_memory("", session_id)
                    else:
                        memory.add_message("assistant", "⚠️ No stylists found matching your request.")
                        return result.get("message", "No stylists found.")

                elif tool_name == "get_customers":
                    if result and isinstance(result, dict) and result.get('customers'):
                        customers = result['customers']
                        if customers and hasattr(customers[0], '__dict__'):
                            result['customers'] = [
                                {"id": s.id, "name": s.name, "description": s.description}
                                for s in customers
                            ]
                        memory.add_message("function", json.dumps(result), name=tool_name)
                        return generate_response_with_memory("", session_id)
                    else:
                        memory.add_message("assistant", "⚠️ No customers found matching your request.")
                        return result.get("message", "No customers found.")

                else:
                    reply = result  # Fallback

                memory.add_message("assistant", reply)
                return reply
            else:
                return f"⚠️ Unknown tool: {tool_name}"

        # No tool call → store reply in memory and return to user
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
		filtered_args = {k: v for k, v in arguments.items() if k in accepted_args}

		result = func(**filtered_args)
		return result
	except Exception as e:
		return f"❌ Error calling tool '{tool_name}': {str(e)}"





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
