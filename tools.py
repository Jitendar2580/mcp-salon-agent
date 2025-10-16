from database.connection import SessionLocal
from database.model import Appointment, Customer, Service, Stylist
from dotenv import load_dotenv
from datetime import datetime
from typing import Dict, List, Union
from sqlalchemy import func ,text , or_
from utils.util import is_stylist_available_on_day, one_substitution_like_filters 



load_dotenv()


# Simulated storage (in-memory)
salon_appointments = {}


def validate_date(date_str: str) -> tuple[bool, str]:
    """Validate date format and ensure it's not in the past"""
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        today = datetime.today().date()
        
        if date_obj < today:
            return False, "Cannot book appointments in the past"
        return True, ""
    except ValueError:
        return False, "Invalid date format. Please use YYYY-MM-DD"

def validate_time(time_str: str) -> tuple[bool, str]:
    """Validate time format"""
    try:
        datetime.strptime(time_str, "%H:%M")
        return True, ""
    except ValueError:
        return False, "Invalid time format. Please use HH:MM (24-hour format)"



def get_greeting() -> dict:
    """Generate greeting message"""
    return {
        'message': "Welcome to YOYO Salon! 💇✨ We're excited to help you with your appointment today.",
        'status': "success"
    }

def book_salon(name: str, date: str, time: str, service: str, stylist: str) -> str:
    """Book salon appointment"""
    # Validate inputs
    is_valid_date, date_error = validate_date(date)
    if not is_valid_date:
        return f"❌ {date_error}"
    
    is_valid_time, time_error = validate_time(time)
    if not is_valid_time:
        return f"❌ {time_error}"
    
    # Simulate booking (replace with actual database logic)
    return f"✅ Your appointment with **{stylist}** for a **{service}** is booked on **{date}** at **{time}**."

def cancel_appointment(name: str, date: str, time: str) -> str:
    """Cancel appointment"""
    is_valid_date, date_error = validate_date(date)
    if not is_valid_date:
        return f"❌ {date_error}"
    
    is_valid_time, time_error = validate_time(time)
    if not is_valid_time:
        return f"❌ {time_error}"
    
    return f"✅ Appointment for {name} on {date} at {time} has been canceled."

def reschedule_appointment(name: str, date: str, time: str, new_date: str, new_time: str) -> str:
    """Reschedule appointment"""
    is_valid_date, date_error = validate_date(new_date)
    if not is_valid_date:
        return f"❌ {date_error}"
    
    is_valid_time, time_error = validate_time(new_time)
    if not is_valid_time:
        return f"❌ {time_error}"
    
    return f"✅ Appointment rescheduled to {new_date} at {new_time}."

def show_appointments(name: str = None, date: str = None, time: str = None) -> str:
    """Show appointments"""
    if date:
        is_valid_date, date_error = validate_date(date)
        if not is_valid_date:
            return f"❌ {date_error}"
    
    return f"📅 Showing appointments for {name or 'all customers'}"

def get_services(query: str = None) -> Dict:
    """Get available services"""
    mock_services = [
        {"id": 1, "name": "haircut"},
        {"id": 2, "name": "manicure"},
        {"id": 3, "name": "facial"},
        {"id": 4, "name": "spa treatment"}
    ]
    
    if query:
        filtered = [s for s in mock_services if query.lower() in s["name"].lower()]
        if not filtered:
            return {
                'services': [],
                'message': f"Sorry! We couldn't find any services matching '{query}'.",
                'status': 'not_found'
            }
        return {
            'services': filtered,
            'message': f"Found {len(filtered)} service(s) matching '{query}'",
            'status': 'success'
        }
    
    return {
        'services': mock_services,
        'message': f"Here are all {len(mock_services)} available services",
        'status': 'success'
    }

def get_stylist(query: str = None, date: str = None, time: str = None) -> Dict:
    """Get available stylists"""
    mock_stylists = [
        {"id": 1, "name": "Jitendra", "availability": "Mon-Fri"},
        {"id": 2, "name": "Sarah", "availability": "Tue-Sat"}
    ]
    
    if query:
        filtered = [s for s in mock_stylists if query.lower() in s["name"].lower()]
        if not filtered:
            return {
                'stylists': [],
                'message': f"Sorry, we couldn't find any stylist named '{query}'.",
                'status': 'not_found'
            }
        return {
            'stylists': filtered,
            'message': f"Found {len(filtered)} stylist(s) matching '{query}'",
            'status': 'success'
        }
    
    return {
        'stylists': mock_stylists,
        'message': f"Here are all {len(mock_stylists)} available stylists",
        'status': 'success'
    }

def get_customers(query: str = None) -> Dict:
    """Get customers"""
    mock_customers = [
        {"id": 1, "name": "John Doe", "email": "john@example.com", "phone": "1234567890"}
    ]
    
    if query:
        filtered = [c for c in mock_customers if query.lower() in c["name"].lower()]
        if not filtered:
            return {
                'customers': [],
                'message': f"Sorry, we couldn't find any customers matching '{query}'.",
                'status': 'not_found'
            }
        return {
            'customers': filtered,
            'message': f"Found {len(filtered)} customer(s) matching '{query}'",
            'status': 'success'
        }
    
    return {
        'customers': mock_customers,
        'message': f"Here are all registered customers",
        'status': 'success'
    }

    
    
# tools definition
tools = {
    "get_greeting": {
        "description": "Generate a personalized greeting message for salon customers.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        },
        "function": get_greeting
    },
    "book_salon": {
        "description": "Book a salon appointment with name, date, time, stylist, and service.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Client's name"},
                "date": {"type": "string", "description": "Appointment date (YYYY-MM-DD)"},
                "time": {"type": "string", "description": "Time of appointment (HH:MM)"},
                "stylist": {"type": "string", "description": "Stylist name"},
                "service": {"type": "string", "description": "Service requested"},
            },
            "required": ["name", "date", "time", "service", "stylist"]
        },
        "function": book_salon
    },
    "cancel_appointment": {
        "description": "Cancel a previously booked salon appointment.",
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
    "reschedule_appointment": {
        "description": "Reschedule an existing appointment to a new date and time.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Client's name"},
                "date": {"type": "string", "description": "Current appointment date (YYYY-MM-DD)"},
                "time": {"type": "string", "description": "Current appointment time (HH:MM)"},
                "new_date": {"type": "string", "description": "New appointment date (YYYY-MM-DD)"},
                "new_time": {"type": "string", "description": "New appointment time (HH:MM)"},
            },
            "required": ["name", "date", "time", "new_date", "new_time"]
        },
        "function": reschedule_appointment
    },
    "show_appointments": {
        "description": "View salon appointments filtered by name, date, or time.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Client's name"},
                "date": {"type": "string", "description": "Appointment date (YYYY-MM-DD)"},
                "time": {"type": "string", "description": "Time of appointment (HH:MM)"}
            },
            "required": []
        },
        "function": show_appointments
    },
    "get_services": {
        "description": "Get available salon services, optionally filtered by query.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search string to filter services"}
            },
            "required": []
        },
        "function": get_services
    },
    "get_stylist": {
        "description": "Check available stylists by name, date, and time.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Stylist name to search"},
                "date": {"type": "string", "description": "Date (YYYY-MM-DD)"},
                "time": {"type": "string", "description": "Time (HH:MM)"}
            },
            "required": []
        },
        "function": get_stylist
    },
    "get_customers": {
        "description": "Get customers, optionally filtered by query.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search string to filter customers"}
            },
            "required": []
        },
        "function": get_customers
    }
}
