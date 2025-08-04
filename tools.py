import random
# import wikipedia
import os
import requests
from dotenv import load_dotenv
from groq import Groq
from datetime import datetime


load_dotenv()


# Simulated storage (in-memory)
salon_appointments = {}


def book_salon(name: str, date: str, time: str, service: str, stylist: str) -> str:
    """Book salon appointment"""
    appointment_id = f"{name}_{date}_{time}"
    salon_appointments[appointment_id] = {  
        "name": name,
        "date": date,
        "time": time,
        "service": service,
        "stylist": stylist
    }
    
    return f"✅ Appointment booked for {name} on {date} at {time} for a {service} with {stylist}."

def cancel_appointment(name: str, date: str) -> str:
    for key, appt in list(salon_appointments.items()):
        if appt['name'].lower() == name.lower() and appt['date'] == date:
            del salon_appointments[key]
            return f"✅ Appointment for {name} on {date} has been canceled."
    return f"⚠️ No appointment found for {name} on {date}."

def reschedule_appointment(name: str, date: str, new_date: str, new_time: str) -> str:
    for key, appt in list(salon_appointments.items()):
        if appt['name'].lower() == name.lower() and appt['date'] == date:
            new_key = f"{name}_{new_date}_{new_time}"
            salon_appointments[new_key] = {
                **appt,
                "date": new_date,
                "time": new_time
            }
            del salon_appointments[key]
            return f"🔁 Appointment rescheduled for {name} to {new_date} at {new_time}."
    return f"⚠️ No appointment found for {name} on {date}."


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
    "book_salon": {
        "description": "Book a salon appointment with name, date, time, stylist, and service.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Client's name"},
                "date": {"type": "string", "description": "Appointment date (YYYY-MM-DD)"},
                "time": {"type": "string", "description": "Time of appointment (HH:MM)"},
                "stylist": {"type": "string", "description": "Stylist name (e.g., John, Sarah)"},
                "service": {"type": "string", "description": "Service requested (e.g., haircut, manicure)"},
            },
            "required": ["name", "date", "time", "service", "stylist"]
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
    "cancel_appointment": {
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
        "function": cancel_appointment
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
