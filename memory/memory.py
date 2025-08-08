
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
			"name": None,
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

	def update_info(self, key: str, value: str):
		if key in self.current_booking:
			self.current_booking[key] = value

	def get_missing_info(self) -> List[str]:
		return [key for key, value in self.current_booking.items() if value is None]

	def is_current_booking_complete(self) -> bool:
		return all(value is not None for value in self.current_booking.values())

	def finalize_current_booking(self):
		if self.is_current_booking_complete():
			self.bookings.append(self.current_booking.copy())
			self.current_booking = {
				"name": None,
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


def extract_info_from_input(user_input: str, memory: ConversationMemory) -> Dict[str, Any]:

	extracted = {
		"appointments": []
	}

	# 1. Extract name globally
	name_match = re.search(r"(?:i'?m|my name is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", user_input, re.IGNORECASE)
	if name_match:
		extracted["name"] = name_match.group(1).strip()

	# 2. Extract all service-stylist-date-time chunks
	services = ["haircut", "hair color", "manicure", "pedicure", "facial", "massage"]
	services_pattern = '|'.join(re.escape(s) for s in services)
	stylist_pattern = r"(?:with|stylist)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)"
	date_time_matches = search_dates(user_input, settings={"PREFER_DATES_FROM": "future"})

	# Split by ' and ', ' & ', or ',' for multiple appointments
	parts = re.split(r'\s+(?:and|&|,)\s+', user_input)

	for part in parts:
		appointment = {}
		
		# Service
		for service in services:
			if service in part.lower():
				appointment["service"] = service
				break

		# Stylist
		stylist_match = re.search(stylist_pattern, part, re.IGNORECASE)
		if stylist_match:
			appointment["stylist"] = stylist_match.group(1).strip()

		# Date & Time (search from whole input, then assign closest)
		if date_time_matches:
			for dt_text, dt_obj in date_time_matches:
				if dt_text in part:
					if dt_obj.hour != 0 or dt_obj.minute != 0:
						appointment["time"] = dt_obj.strftime("%H:%M")
					appointment["date"] = dt_obj.strftime("%Y-%m-%d")
					break

		if appointment:
			extracted["appointments"].append(appointment)

	return extracted

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

	# Extract new information
	extracted_info = extract_info_from_input(user_input, memory)
	print("extracted_info-------------4444444444444444444444444444444444444444444444-----", extracted_info)
	for key, value in extracted_info.items():
		memory.update_info(key, value)

	# Prepare tools in OpenAI format
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
		for msg in memory.messages[-6:]
	]
	messages = [system_instruction] + recent_messages

	try:
		chat_completion = client.chat.completions.create(
			model="gpt-4o",
			messages=messages,
			temperature=0.3,
			tools=openai_tools, # Use properly formatted tools
			tool_choice="auto" # Let the model decide when to use tools
		)

		print("chat_completion------------------", chat_completion)
		message = chat_completion.choices[0].message
		print("messagemessagemessage------------------", message)

		print("666666666666666666666666666666666666666666666666666666666666666666666666666666=========================>",memory.current_booking)

		# Handle tool calls
		if message.tool_calls:
			print("🚨 Tool call was requested🚨", message.tool_calls)

			for tool_call in message.tool_calls:
				tool_name = tool_call.function.name
				tool_args = json.loads(tool_call.function.arguments)
				result = handle_tool_call(tool_name, tool_args)

			messages.append({
				"role": "tool",
				"tool_call_id": tool_call.id,
				"content": result
			})

			# Execute the tool function
			if tool_name in tools:
				# tool_function = tools[tool_name].get("function")
				# if tool_function:
				# 	result = tool_function(**tool_args)
				# else:
				# 	result = handle_tool_call(tool_name, tool_args) # Fallback to existing handler

				# Generate human-readable reply
				if tool_name == "book_salon":
					reply = result
				elif tool_name == "show_appointments":
					reply=result 
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
						reply = result.get("message", "No services found.")
						memory.add_message("assistant", reply)
						return reply
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
						reply = result.get("message", "No stylists found.")
						memory.add_message("assistant", reply)
						return reply
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
						reply = result.get("message", "No customers found.")
						memory.add_message("assistant", reply)
						return reply
				elif tool_name == "weather":
					reply = f"""🌤️ Here's the current weather for **{tool_args.get('city')}**:\n\n{result}"""
				else:
					reply = result # Fallback to tool output

				# Only add the final human-readable response to memory, not the tool execution details
				memory.add_message("assistant", reply)
				return reply
			else:
				return f"⚠️ Unknown tool: {tool_name}"

		# No tool call, return regular response
		response = message.content.strip() if message.content else ""
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
		# Match args to function based on required + available order
		func = tool["function"]
		# Only pass valid args defined in properties
		accepted_args = tool["parameters"]["properties"].keys()
		filtered_args = {k: v for k, v in arguments.items() if k in accepted_args}

		result = func(**filtered_args)
		return result
	except Exception as e:
		return f"❌ Error calling tool '{tool_name}': {str(e)}"


def extract_tool_call(response: str) -> Optional[Tuple[str, Dict[str, str]]]:
	try:
		# Extract the first complete JSON object using brace counting
		brace_count = 0
		start_idx = None

		for i, char in enumerate(response):
			if char == '{':
				if brace_count == 0:
					start_idx = i
				brace_count += 1
			elif char == '}':
				brace_count -= 1
				if brace_count == 0 and start_idx is not None:
					json_block = response[start_idx:i + 1]
					try:
						parsed = json.loads(json_block)
						if "tool_call" in parsed:
							tool_call = parsed["tool_call"]
							return tool_call["name"], tool_call["arguments"]
					except json.JSONDecodeError as e:
						print(f"JSON parse error: {e}")
					break # Only extract the first complete block

		# Fallback: check older format
		fallback = re.search(r'\{"tool":\s*"(.*?)",\s*"args":\s*(\[.*?\]|\{.*?\})\}', response, re.DOTALL)
		if fallback:
			name = fallback.group(1)
			args_raw = fallback.group(2)
			args_data = json.loads(args_raw)
			if isinstance(args_data, list):
				args_dict = {f"arg{i+1}": val for i, val in enumerate(args_data)}
			else:
				args_dict = args_data
			return name, args_dict

	except Exception as e:
		print(f"Tool call parse error: {e}")
	return None


def format_natural_datetime(date_str: str, time_str: str) -> str:
	combined = f"{date_str} {time_str}"
	parsed_dt = dateparser.parse(combined)

	if not parsed_dt:
		return f"{date_str} at {time_str}" # fallback

	return parsed_dt.strftime("%A, %B %d at %I:%M %p") # e.g., Monday, August 05 at 11:00 AM




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
