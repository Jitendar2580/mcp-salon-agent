import os
import requests
from database.connection import SessionLocal
from database.model import Appointment, Customer, Service, Stylist
from dotenv import load_dotenv
from datetime import datetime
from typing import Dict, List, Union
from sqlalchemy import func
from rapidfuzz import fuzz ,process as rf_process
from rapidfuzz.process import extractOne



load_dotenv()


# Simulated storage (in-memory)
salon_appointments = {}


def book_salon(name: str, date: str, time: str, service: str, stylist: str) -> str:
	"""Book salon appointment"""
	session = SessionLocal()
	try:
		# Fetch related IDs from names
		customer = session.query(Customer).filter(func.lower(Customer.name) == name.lower()).first()

		stylist_obj = session.query(Stylist).filter(func.lower(Stylist.name) == stylist.lower()).first()

		service_obj = session.query(Service).filter(func.lower(Service.name) == service.lower()).first()

		# Validate all foreign key lookups
		if not customer:
			return f"❌ Customer with name '{name}' not found."
		if not stylist_obj:
			return f"❌ Stylist with name '{stylist}' not found."
		if not service_obj:
			return f"❌ Service with name '{service}' not found."

		# Create appointment
		appointment = Appointment(
			customer_id=customer.id,
			stylist_id=stylist_obj.id,
			service_id=service_obj.id,
			date=datetime.strptime(date, "%Y-%m-%d").date(),
			time=datetime.strptime(time, "%H:%M").time()
		)

		session.add(appointment)
		session.commit()
		return f"""✅ Your appointment with **{stylist}** for a **{service}** is booked on **{date}** at **{time}**."""

	except Exception as e:
		session.rollback()
		return f"❌ Failed to book appointment: {e}"

	finally:
		session.close()

def cancel_appointment(name: str, date: str, time: str) -> str:
	session = SessionLocal()
	try:
		customer = session.query(Customer).filter(func.lower(Customer.name) == name.lower()).first()
		if not customer:
			return f"❌ No customer found with name '{name}'."

		print(f"Canceling appointment for customer: {customer.name} (ID: {customer.id})")

		appointment = session.query(Appointment).filter_by(
			customer_id=customer.id,
			date=date,
			time=time
		).first()

		if not appointment:
			return f"❌ No appointment found for {name} on {date} at {time}."

		session.delete(appointment)
		session.commit()
		return f"✅ Appointment for {name} on {date} at {time} has been canceled."
	except Exception as e:
		print(f"Error canceling appointment------------------>: {e}")
		return f"❌ Failed to cancel appointment: {e}"
	finally:
		session.close()

def reschedule_appointment(name: str, date: str, time: str, new_date: str, new_time: str) -> str:
	session = SessionLocal()
	try:
		# Find existing appointment
		customer = session.query(Customer).filter(func.lower(Customer.name) == name.lower()).first()

		appointment = session.query(Appointment).filter_by(
			customer_id=customer.id,
			date=date,
			time=time
		).first()

		# appointment = session.query(Appointment).filter_by(name=name, date=date, time=time).first()
		print(f"Rescheduling appointment: {appointment}")

		if not appointment:
			return f"❌ No appointment found for {name} on {date} at {time}."

		# Update date and time
		appointment.date = new_date
		appointment.time = new_time
		session.commit()
		return f"✅ Appointment for {name} has been rescheduled to {new_date} at {new_time}."
	except Exception as e:
		print(f"Error rescheduling appointment ------------------>: {e}")
		return f"❌ Failed to reschedule appointment: {e}"
	finally:
		session.close()

# def show_appointments(name: str = None, date: str = None, time: str = None) -> str:
# 	session = SessionLocal()
# 	try:
# 		customer = session.query(Customer).filter(func.lower(Customer.name) == name.lower()).first() 
# 		appointments=session.query(Appointment).join(Customer).filter((Appointment.customer_id == customer.id)).all()

# 		if not appointments:
# 			return "❌ No matching appointments found."
# 		result = "📅 Matching Appointments:\n"
# 		for a in appointments:
# 			result += f"- {a.customer.name} | {a.date} at {a.time} | Stylist: {a.stylist.name} | Service: {a.service.name}\n"
# 		return result
# 	except Exception as e:
# 		return f"❌ Failed to fetch appointments: {e}"
# 	finally:
# 		session.close() 

def show_appointments(name: str = None, date: str = None, time: str = None) -> str:
    session = SessionLocal()
    try:
        all_customers = session.query(Customer).all()
        customer_names = [c.name for c in all_customers]
        matched_customer = None

        if name:
            for c in all_customers:
                if name in c.name.lower():
                    matched_customer = c
                    break

            if not matched_customer:
                match_result = rf_process.extractOne(name, customer_names, scorer=fuzz.token_sort_ratio)
                print(f"Fuzzy match result for '{name}': {match_result}")
                if match_result and match_result[1] >= 70:
                    matched_name = match_result[0]
                    matched_customer = next((c for c in all_customers if c.name.lower() == matched_name.lower()), None)

        if not matched_customer:
            return f"❌ No customer found matching '{name}'."

        appointment_query = session.query(Appointment).join(Customer).filter(Appointment.customer_id == matched_customer.id)

        if date:
            appointment_query = appointment_query.filter(Appointment.date == date)
        if time:
            appointment_query = appointment_query.filter(Appointment.time == time)

        appointments = appointment_query.all()

        if not appointments:
            return f"❌ No appointments found for '{matched_customer.name}'" + \
                   (f" on {date}" if date else '') + (f" at {time}" if time else '') + "."

        result = f"📅 Appointments for {matched_customer.name}:\n"
        for a in appointments:
            result += f"- {a.date} at {a.time} | Stylist: {a.stylist.name} | Service: {a.service.name}\n"

        return result

    except Exception as e:
        return f"❌ Failed to fetch appointments: {e}"
    finally:
        session.close()
         
def get_services(query: str = None) -> Dict[str, Union[List[Dict], str]]:
	session = SessionLocal()
	try:
		all_services = session.query(Service).all()
		service_names = [service.name for service in all_services]

		if query:
			# Use fuzzy matching to find the best match
			match_result = extractOne(query, service_names, scorer=fuzz.token_sort_ratio)

			if match_result and match_result[1] >= 70: # threshold
				matched_name = match_result[0]
				matched_services = [
					s for s in all_services if s.name.lower() == matched_name.lower()
				]
			else:
				matched_services = []
		else:
			matched_services = all_services

		if not matched_services:
			polite_message = (
				f"Sorry! We couldn't find any services related to '{query}'. "
				"Try a different name or check our full service list." if query
				else "It looks like we don't have any services listed at the moment. Please check back again soon!"
			)
			return {
				'services': [],
				'message': polite_message,
				'status': 'not_found'
			}

		print(f"Fuzzy matched services for '{query}': {[s.name for s in matched_services]}")

		serialized_services = [
			{"id": s.id, "name": s.name}
			for s in matched_services
		]
		return {
			'services': serialized_services,
			'message': f"Found {len(serialized_services)} services" + (f" matching '{query}'" if query else ''),
			'status': 'success'
		}

	finally:
		session.close()

# def get_stylist(query: str = None) -> Dict[str, Union[List[Dict], str]]:
# 	session = SessionLocal()
# 	try:
# 		if query:
# 			stylists = session.query(Stylist).filter(Stylist.name.ilike(f"%{query}%")).all()
# 		else:
# 			stylists = session.query(Stylist).all()

# 		if query:
# 			query_lower = query.lower()
# 			stylists = [s for s in stylists if query_lower in s.name.lower()]

# 		if not stylists:
# 			polite_message = (
# 				f"Oops! No stylists found matching '{query}'. Please try a different name."
# 				if query else
# 				"Looks like we don't have any stylists listed right now. Please check back later!"
# 			)
# 			return {
# 				'stylists': [],
# 				'message': polite_message,
# 				'status': 'not_found'
# 			}
# 		return {
# 			'stylists': [
# 				{
# 					'id': s.id,
# 					'name': s.name, 
# 					# Add more fields as needed
# 				} for s in stylists
# 			],
# 			'message': f"Found {len(stylists)} stylist(s)" + (f" matching '{query}'" if query else ''),
# 			'status': 'success'
# 		}
# 	finally:
# 		session.close()

def get_stylist(query: str = None) -> Dict[str, Union[List[Dict], str]]:
	session = SessionLocal()
	try:
		print(f"Fetching stylists with query==================================================: {query}")
		all_stylists = session.query(Stylist).all()
		stylist_names = [stylist.name for stylist in all_stylists]

		if query:
			matched_stylists = [
				s for s in all_stylists if query.lower() in s.name.lower()
			]

			# If no match found, try fuzzy match
			if not matched_stylists:
				match_result = rf_process.extractOne(
					query, stylist_names, scorer=fuzz.token_sort_ratio
				)
				print(f"Fuzzy match result for=======================99999999999999999999999----------------- '{query}': {match_result}")
				if match_result and match_result[1] >= 70:
					matched_name = match_result[0]
					matched_stylists = [
						s for s in all_stylists if s.name.lower() == matched_name.lower()
					]
		else:
			matched_stylists = all_stylists

		if not matched_stylists:
			polite_message = (
				f"Oops! No stylists found matching '{query}'. Please try a different name."
				if query else
				"Looks like we don't have any stylists listed right now. Please check back later!"
			)
			return {
				'stylists': [],
				'message': polite_message,
				'status': 'not_found'
			}

		print(f"Matched stylists for '{query}': {[s.name for s in matched_stylists]}")

		serialized_stylists = [
			{"id": s.id, "name": s.name}
			for s in matched_stylists
		]

		return {
			'stylists': serialized_stylists,
			'message': f"Found {len(serialized_stylists)} stylist(s)" + (f" matching '{query}'" if query else ''),
			'status': 'success'
		}
	finally:
		session.close()

# def get_customers(query: str = None) -> Dict[str, Union[List[Dict], str]]:
# 	session = SessionLocal()
# 	try:
# 		if query:
# 			customers = session.query(Customer).filter(Customer.name.ilike(f"%{query}%")).all()
# 		else:
# 			customers = session.query(Customer).all()

# 		if query:
# 			query_lower = query.lower()
# 			customers = [c for c in customers if query_lower in c.name.lower()]

# 		if not customers:
# 			polite_message = (
# 				f"Sorry, we couldn't find any customers matching '{query}'. Try checking the spelling!"
# 				if query else
# 				"No customers found in our records at the moment."
# 			)
# 			return {
# 				'customers': [],
# 				'message': polite_message,
# 				'status': 'not_found'
# 			}

# 		return {
# 			'customers': [
# 				{
# 					'id': c.id,
# 					'name': c.name,
# 					'email': c.email,
# 					'phone': c.phone,
# 					# Add more fields as needed
# 				} for c in customers
# 			],
# 			'message': f"Found {len(customers)} customer(s)" + (f" matching '{query}'" if query else ''),
# 			'status': 'success'
# 		}
# 	finally:
# 		session.close()

def get_customers(query: str = None) -> Dict[str, Union[List[Dict], str]]:
    session = SessionLocal()
    try:
        all_customers = session.query(Customer).all()
        customer_names = [customer.name for customer in all_customers]

        if query:
            matched_customers = [
                c for c in all_customers if query.lower() in c.name.lower()
            ]
            if not matched_customers:
                match_result = rf_process.extractOne(
                    query, customer_names, scorer=fuzz.token_sort_ratio
                )
                if match_result and match_result[1] >= 70:
                    matched_name = match_result[0]
                    matched_customers = [
                        c for c in all_customers if c.name.lower() == matched_name.lower()
                    ]
        else:
            matched_customers = all_customers

        if not matched_customers:
            polite_message = (
                f"Sorry, we couldn't find any customers matching '{query}'. Try checking the spelling!"
                if query else
                "No customers found in our records at the moment."
            )
            return {
                'customers': [],
                'message': polite_message,
                'status': 'not_found'
            }

        print(f"Matched customers for '{query}': {[c.name for c in matched_customers]}")

        serialized_customers = [
            {
                'id': c.id,
                'name': c.name,
                'email': c.email,
                'phone': c.phone,
                # Add more fields as needed
            } for c in matched_customers
        ]

        return {
            'customers': serialized_customers,
            'message': f"Found {len(serialized_customers)} customer(s)" + (f" matching '{query}'" if query else ''),
            'status': 'success'
        }
    finally:
        session.close()
        
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
		"function": book_salon
	},
	"show_appointments": {
		"description": "View specific salon appointments filtered by name, date, or time.",
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



	"get_services": {
		"description": "Get the list of available salon services, optionally filtered by a search query.",
		"parameters": {
			"type": "object",
			"properties": {
				"query": {
					"type": "string",
					"description": "Optional search string to filter services by name"
				}
			},
			"required": ['services'],
		},
		"function": get_services
	},
	"get_stylist": {
		"description": "Get the list of available stylists, optionally filtered by a search query.",
		"parameters": {
			"type": "object",
			"properties": {
				"query": {
					"type": "string",
					"description": "Optional search string to filter stylists by name or expertise"
				}
			},
			"required": ['stylists']
		},
		"function": get_stylist
	},
	"get_customers": {
		"description": "Get the list of customers, optionally filtered by a search query.",
		"parameters": {
			"type": "object",
			"properties": {
				"query": {
					"type": "string",
					"description": "Optional search string to filter customers by name or contact"
				}
			},
			"required": ['customers']
		},
		"function": get_customers
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
}
