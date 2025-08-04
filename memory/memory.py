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

    # MCP-style system message
    tool_descriptions = "\n".join(
        [f"- {name}: {info['description']}" for name, info in tools.items()]
    )

    system_instruction = {
        "role": "system",
        "content": f"""
            You're a smart assistant. You must decide whether to answer directly or use a tool.

            If you have enough information, respond with this EXACT format:

            {{
            "tool_call": {{
                "name": "<tool_name>",
                "arguments": {{
                "arg1": "value",
                "arg2": "value"
                }}
            }}
            }}

            Only use tools from the following list:
            {tool_descriptions}

            If you do **not** have all required fields, do **not** call a tool.  
            Instead, **respond naturally** to the user, clearly asking for the missing information.
            Ask the user directly for just the missing parts, without extra explanation.
        """
    }

    # Build message history
    recent_messages = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in memory.messages[-6:]
    ]
    messages = [system_instruction] + recent_messages

    try:
        chat_completion = client.chat.completions.create(
            model=os.getenv("MODEL_NAME", "llama3-70b-8192"),
            messages=messages,
            temperature=0.3
        )
        response = chat_completion.choices[0].message.content.strip()
    except Exception as e:
        return f"⚠️ LLM error: {e}"

    # Detect tool call
    tool_call = extract_tool_call(response)

    if tool_call:
        tool_name, tool_args = tool_call
        result = handle_tool_call(tool_name, tool_args)
        print("tool_argstool_argstool_args-----------",tool_args)
        memory.add_message("assistant", f"[Tool `{tool_name}` called with args]")
        memory.add_message("tool", result)


        # Clean, human-readable reply
        if tool_name == "book_salon":
            print("book_salonbook_salonbook_salon",book_salon)
            readable_datetime = format_natural_datetime(tool_args.get('date', ''), tool_args.get('time', ''))
            print("readable_datetimereadable_datetimereadable_datetime",readable_datetime)
            
            reply = f"""✅ Your appointment with **{tool_args.get('stylist')}** for a **{tool_args.get('service')}** is booked on **{readable_datetime}**."""
        elif tool_name == "cancel_appointment":
            reply = f"""❌ Your appointment on **{tool_args.get('date')}** has been canceled, {tool_args.get('name')}."""
        elif tool_name == "reschedule_appointment":
            reply = f"""🔁 Your appointment has been rescheduled to **{tool_args.get('new_date')} at {tool_args.get('new_time')}**, {tool_args.get('name')}."""
        elif tool_name == "weather":
            reply = f"""🌤️ Here's the current weather for **{tool_args.get('city')}**:\n\n{result}"""
        else:
            reply = result  # Fallback to tool output

        memory.add_message("assistant", reply)
        return reply

    # No tool call, return assistant response
    memory.add_message("assistant", response)
    return response


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
                    break  # Only extract the first complete block

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
        return f"{date_str} at {time_str}"  # fallback

    return parsed_dt.strftime("%A, %B %d at %I:%M %p")  # e.g., Monday, August 05 at 11:00 AM




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
