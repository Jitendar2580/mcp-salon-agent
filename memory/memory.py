from datetime import datetime
from typing import List, Optional, Tuple
from dotenv import load_dotenv
from tools import tools
from groq import Groq
from typing import Dict
from datetime import datetime 
import os , re
from tools import book_salon
import json
import dateparser
from datetime import datetime
from openai import OpenAI

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
		self.collected_info = {
			"name": None,
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
	"""Extract appointment information from user input using pattern matching (no LLM)."""
	extracted = {}

	# 1. Extract date (supports "tomorrow", "August 5", "next Monday", etc.)
	date = dateparser.parse(user_input, settings={"PREFER_DATES_FROM": "future"})
	if date:
		extracted["date"] = date.strftime("%Y-%m-%d")

	# 2. Extract time
	time_match = re.search(r'\b(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?\b', user_input, re.IGNORECASE)
	if time_match:
		hour = int(time_match.group(1))
		minute = int(time_match.group(2)) if time_match.group(2) else 0
		am_pm = time_match.group(3)
		if am_pm:
			if am_pm.lower() == 'pm' and hour != 12:
				hour += 12
			elif am_pm.lower() == 'am' and hour == 12:
				hour = 0
		extracted["time"] = f"{hour:02}:{minute:02}"

	# 3. Extract name (look for "I'm NAME", "my name is NAME")
	name_match = re.search(r"(?:i'?m|my name is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", user_input, re.IGNORECASE)
	if name_match:
		extracted["name"] = name_match.group(1).strip()

	# 4. Extract service (match common service words)
	services = ["haircut", "hair color", "manicure", "pedicure", "facial", "massage"]
	for service in services:
		if service in user_input.lower():
			extracted["service"] = service
			break

	# 5. Extract stylist (look for "with NAME", "stylist NAME")
	stylist_match = re.search(r"(?:with|stylist)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", user_input, re.IGNORECASE)
	if stylist_match:
		extracted["stylist"] = stylist_match.group(1).strip()

	return extracted

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

	# System message
	today = datetime.today().strftime("%A, %B %d, %Y") # e.g., "Monday, August 4, 2025"
	# system_instruction = {
	# 	"role": "system",
	# 	"content": f"""
	# 	                You're a smart assistant. You can use the available tools when you have all required information.

	# 	                🧠 If the user's message includes a natural time reference (like "tomorrow", "today", or a weekday), interpret it based on today's date: {today}.  
	# 	                Always resolve and include the **full date** in your response — weekday, month, day, and year.

	# 	                If you don't have all required information for a tool call, ask the user naturally for the missing information.
	# 	            """
	# }
	# system_instruction = {
	# 	"role": "system",
	# 	"content": f"""
	# 	            	You are a smart assistant for a salon. Use the available tools when you have enough information.
		            
	# 	            	- If a user says something like "I want a haircut", "book a manicure", or "I need coloring", and the service is mentioned, use the `get_services` tool to confirm availability.
	# 	            	- Do NOT wait for all fields before using helper tools like `get_services` or `get_stylist`.
	# 	            	- Today's date is {today}. Resolve natural time like "tomorrow" into full date.
		            	
	# 	            	If you're missing booking fields like time, date, stylist, or name — ask the user naturally for those.
	# 	            """
	# }
	
	# system_instruction = {
	# 	"role": "system",
	# 	"content": f"""
	# 	You are a smart, helpful assistant for a salon booking system. Your primary goal is to help users book salon appointments by using the available tools efficiently. You should always sound friendly, polite, and easy to understand.

	# 	🎯 Purpose:
	# 	Your job is to guide users through booking a salon appointment using real-time tools.

	# 	📅 Today's date is {today}. Convert natural phrases like “tomorrow”, “next Friday”, etc., into full dates.

	# 	🧠 MCP (Model Context Protocol) Behavior:
	# 	- Call helper tools like `get_services` and `get_stylist` **as soon as you have enough context**. Do not wait for all booking fields before using them.
	# 	- Only call `book_salon` after collecting all required fields **and confirming with the user**.
	# 	- Always maintain memory of previously collected data.

	# 	🛠️ Tool Usage Rules: 
	# 	1. **Booking Appointments**
	# 	- Use `get_services` if a service is mentioned.
	# 	- Use `get_stylist` if a stylist is mentioned or needs to be checked.
	# 	- Collect the following fields before calling `book_salon`:
	# 		- `name`, `date`, `time`, `service`, and `stylist`
	# 	- Once all fields are collected:
	# 		- Summarize the appointment.
	# 		- Ask: “Would you like me to confirm this appointment?”
	# 		- Wait for the user to confirm (e.g., “Yes” or “Please go ahead”).
	# 		- Then call `book_salon`.

	# 	2. **Cancelling Appointments**
	# 	- If a user wants to cancel, use `get_appointments` or `search_appointments` (if available) to find matches using their name and the provided date/time.
	# 	- Show the matched appointments in a readable format:
	# 		- “Jitendra | 2025-08-06 at 15:00 | Stylist: John | Service: Haircut”
	# 	- Then ask:
	# 		- “Please confirm which appointment you'd like to cancel.”
	# 		- OR “Would you like to cancel all of these?”
   
   
	# 	- Wait for user confirmation before calling `cancel_appointment`.
	# 	- Use `get_services` if a service (e.g., haircut, manicure, facial) is mentioned.
	# 	- Use `get_stylist` if a stylist name is given or needs verification.
	# 	- Use `book_salon` **only when you have these fields**:
	# 	- `name`
	# 	- `date` (in full format)
	# 	- `time`
	# 	- `service`
	# 	- `stylist`
	# 	- Before calling `book_salon`, confirm the full booking details with the user. Ask something like:
	# 	- “Shall I go ahead and book this appointment for you?”
	# 	- Wait for the user to confirm (e.g., “Yes” or “Please do it”) before proceeding.

	# 	🗣️ Conversation Style:
	# 	- Ask naturally and politely for any missing info:
	# 	- “What date and time would you prefer?”
	# 	- “May I know your name to complete the booking?”
	# 	- After using a tool, summarize the result in user-friendly language:
	# 	- ✅ “Yes, we do offer hair coloring.”
	# 	- ✅ “Riya is available tomorrow at 4 PM.”
	# 	- After gathering all booking details, repeat them back and ask for confirmation:
	# 	- “You're booking a haircut with Riya on August 6th at 3 PM. Should I confirm this now?”

	# 	🚫 Don’ts:
	# 	- Do not assume any booking without confirmation.
	# 	- Do not call `book_salon` without all required arguments.
	# 	- Do not mention tool names in the user-facing responses.

	# 	✅ Example:
	# 	User: “I want a facial with Riya tomorrow”
	# 	→ You:
	# 	1. Use `get_services` to confirm facial is available.
	# 	2. Use `get_stylist` to check Riya’s availability.
	# 	3. If `name`, `date`, `time`, `service`, and `stylist` are available:
	# 	- Repeat: “You’re booking a facial with Riya on [resolved date]. May I confirm this appointment?”
	# 	- Wait for the user’s yes.
	# 	- Then call `book_salon`.

	# 	Be helpful and proactive — always move the conversation forward toward booking the appointment.
	# 	"""
	# }

	system_instruction = {
		"role": "system",
		"content": f"""
		You are a smart, helpful assistant for a salon booking system. You assist users in booking or cancelling appointments using available tools. Always be friendly, polite, and speak in clear, natural language.

		📅 Today’s date is {today}. Convert phrases like “tomorrow”, “next Friday”, or “this weekend” into full dates.

		---

		🧠 General Rules (MCP Protocol):
		- Understand whether the user wants to **book** or **cancel** an appointment.
		- Use helper tools early when you have enough context — don’t wait for all inputs.
		- Never perform booking or cancellation without **explicit user confirmation**.
		- Always remember previously collected details (like name or service).

		---

		🛠️ TOOL USAGE:

		### 1. Booking Appointments

		Use these tools in the following order:
		- `get_services`: When a service is mentioned.
		- `get_stylist`: When a stylist is mentioned or needed.
		- Collect all required fields:
		- `name`, `date` (resolved), `time`, `service`, `stylist`
		- After collecting all:
		- Repeat the booking summary (e.g., “You’re booking a haircut with John on August 6th at 3 PM.”)
		- Ask: “Shall I go ahead and confirm this appointment for you?”
		- Wait for user confirmation (e.g., “Yes” or “Confirm”)
		- Then call `book_salon`

		### 2. Cancelling Appointments

		- If user mentions cancellation, ask for:
		- `name`
		- `date` and `time` (or “all” if they want to cancel all)
		- Use `get_appointments` (or `search_appointments`) to find matches.
		- Present appointments clearly, like:
		- “Jitendra | 2025-08-06 at 15:00 | Stylist: John | Service: Haircut”
		- Ask:
		- “Which of these would you like to cancel?” or “Do you want to cancel all of them?”
		- Wait for confirmation, then call `cancel_appointment`

		---

		💬 Conversation Style:
		- Always ask naturally for missing fields:
		- “What time would you prefer?”
		- “May I know your name to complete the booking?”
		- After tool calls, summarize results like:
		- ✅ “Yes, we offer hair coloring.”
		- ✅ “John is available at 3 PM tomorrow.”

		---

		🚫 DON’TS:
		- ❌ Don’t assume user intent — clarify if unclear.
		- ❌ Don’t call `book_salon` or `cancel_appointment` without full details AND confirmation.
		- ❌ Don’t mention tool names in user responses — only use tools internally.

		---

		✅ Example — Booking:
		User: “I want a facial with Riya tomorrow”
		→ You:
		- Confirm facial is available (`get_services`)
		- Check Riya’s availability (`get_stylist`)
		- Ask for time and name
		- Then confirm: “You're booking a facial with Riya on August 6th at 3 PM. Should I confirm this?”

		✅ Example — Cancel:
		User: “Cancel my appointment tomorrow”
		→ You:
		- Ask for name
		- Search appointments by name/date (`get_appointments`)
		- Show options
		- Ask: “Which one should I cancel?”
		- Call `cancel_appointment` after confirmation

		---

		Always stay helpful, friendly, and focused on completing the user’s request step-by-step.
		"""
	}

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

		# Handle tool calls
		if message.tool_calls:
			print("🚨 Tool call was requested🚨", message.tool_calls)

			tool_call = message.tool_calls[0]
			tool_name = tool_call.function.name
			tool_args = json.loads(tool_call.function.arguments)

			print("tool_args-----------", tool_args)

			# Execute the tool function
			if tool_name in tools:
				tool_function = tools[tool_name].get("function")
				if tool_function:
					result = tool_function(**tool_args)
				else:
					result = handle_tool_call(tool_name, tool_args) # Fallback to existing handler

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
