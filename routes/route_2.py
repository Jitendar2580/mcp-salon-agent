# from tools import tools
# import os
# import json
# import requests
# from dotenv import load_dotenv
# from groq import Groq
# from typing import Dict
# from datetime import datetime
# from memory.memory import generate_response_with_memory
# load_dotenv()

# API_KEY = os.getenv("GROQ_API_KEY")
# client = Groq(api_key=API_KEY)
 
 
# def route_query_to_tool_2(user_input: str, session_id: str = "default") -> str:
#     """Main routing function with memory support"""
#     try:
#         return generate_response_with_memory(user_input, session_id)
#     except Exception as e:
#         return f"I apologize, but I encountered an error. Could you please try again? Error: {e}"


