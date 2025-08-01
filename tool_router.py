# from tools import tools
# import os
# import json
# import requests
# from dotenv import load_dotenv
# from groq import Groq

# load_dotenv()

# API_KEY = os.getenv("GROQ_API_KEY")
# client = Groq(api_key=API_KEY)




# def route_query_to_tool(user_input: str) -> str:
#     # Describe available tools
#     tool_descriptions = "\n".join(
#         [f"{k}: {v['description']}" for k, v in tools.items()]
#     )

#     # Prompt
#     prompt = f"""
#         You are an AI assistant. Based on the user's input, choose the best tool from the list below:
#         {tool_descriptions}
        
#         Respond in JSON like: {{"tool": "tool_name", "input": "string to pass"}}
        
#         User input: "{user_input}"
#     """.strip()


#     try:
#         chat_completion = client.chat.completions.create(
#             model=os.getenv("MODEL_NAME", "llama3-70b-8192"),
#             messages=[
#                 {"role": "system", "content": "You're a tool-calling assistant."},
#                 {"role": "user", "content": prompt},
#             ],
#             temperature=0.2,
#         )

#         # No .json() needed here
#         content = chat_completion.choices[0].message.content.strip()

#         try:
#             parsed = json.loads(content)
#             tool_name = parsed.get("tool")
#             tool_input = parsed.get("input")

#             if tool_name in tools:
#                 return tools[tool_name]["function"](tool_input)
#             else:
#                 return f"Tool '{tool_name}' not found."

#         except Exception as e:
#             return f"Failed to parse tool response: {e}\nRaw content: {content}"

#     except Exception as e:
#         return f"Request failed: {e}"
    
    
    
    
    
    
    
    
# 		# response = requests.post(
# 		#     "https://api.groq.com/openai/v1/chat/completions",
# 		#     headers={
# 		#         "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
# 		#         "Content-Type": "application/json",
# 		#     },
# 		#     json={
# 		#         "model": os.getenv("MODEL_NAME", "llama3-70b-8192"),
# 		#         "messages": [
# 		#             {"role": "system", "content": "You're a tool-calling assistant."},
# 		#             {"role": "user", "content": prompt},
# 		#         ],
# 		#         "temperature": 0.2,
# 		#     },
# 		#     timeout=20,
# 		# )
# 		# result = response.json()
