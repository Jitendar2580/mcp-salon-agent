import random
import wikipedia
import os
import requests
from dotenv import load_dotenv
from groq import Groq
from datetime import datetime


load_dotenv()


# Simulated storage (in-memory)
salon_appointments = {}


def book_salon(name: str, date: str, time: str, service: str,stylist: str) -> str:
    """Book salon appointment"""
    key = f"{name}_{date}_{time}"
    if key in salon_appointments:
        return f"❌ Sorry, there's already a booking for {name} on {date} at {time}. Would you like to choose a different time?"

    salon_appointments[key] = {
        "name": name,
        "date": date,
        "time": time,
        "service": service,
        "stylist": stylist,
        "created_at": datetime.now().isoformat()
    }
    # Debugging line 
    
    return f"✅ Booking confirmed! Your {service} appointment is scheduled for {date} at {time}."


def cancel_salon(name: str, date: str, time: str) -> str:
    key = f"{name}_{date}_{time}"
    if key in salon_appointments:
        del salon_appointments[key]
        return f"Booking canceled for {name} on {date} at {time}."
    else:
        return f"No booking found for {name} on {date} at {time}."


def get_weather(city: str) -> str:
    api_key = os.getenv("WEATHER_API_KEY")
    url = f"http://api.weatherapi.com/v1/current.json?key={api_key}&q={city}"

    try:
        res = requests.get(url)
        data = res.json()
        return f"{data['location']['name']}: {data['current']['temp_c']}°C, {data['current']['condition']['text']}"
    except Exception as e:
        return f"Weather fetch failed: {e}"


# tools definition
tools = {
    "salon_booking": {
        "description": "Book a salon appointment with name, date, time, and service.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Client's name"},
                "date": {"type": "string", "description": "Appointment date (YYYY-MM-DD)"},
                "time": {"type": "string", "description": "Time of appointment (HH:MM)"},
                "service": {"type": "string", "description": "Service requested (e.g., haircut, manicure)"}
            },
            "required": ["name", "date", "time", "service"]
        },
        "function": book_salon  # this should be your actual function
    },
    "weather": {
        "description": "Get current weather information for a city.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City name (e.g., Tokyo, Paris)"
                }
            },
            "required": ["city"]
        },
        "function": get_weather,
    },
    "salon_cancel": {
        "description": "Cancel a previously booked salon appointment using name, date, and time.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Client's name"},
                "date": {"type": "string", "description": "Date of appointment (YYYY-MM-DD)"},
                "time": {"type": "string", "description": "Time of appointment (HH:MM)"}
            },
            "required": ["name", "date", "time"]
        },
        "function": cancel_salon
    },
    # "math_solver": {
    #     "description": "Solve basic arithmetic or math expressions.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "expression": {
    #                 "type": "string",
    #                 "description": "Math expression like '2 + 2'"
    #             }
    #         },
    #         "required": ["expression"]
    #     },
    #     "function": solve_math,
    # },
}
