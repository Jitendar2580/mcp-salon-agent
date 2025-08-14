from database.connection import SessionLocal
from database.model import Appointment, Customer, Service, Stylist
from dotenv import load_dotenv
from datetime import datetime
from typing import Dict, List, Union
from sqlalchemy import func ,text 
from utils.util import is_stylist_available_on_day 



load_dotenv()


# Simulated storage (in-memory)
salon_appointments = {}


def book_salon(name: str, date: str, time: str, service: str, stylist: str) -> str:
	"""Book salon appointment"""
	session = SessionLocal()
	try:
		# Use ILIKE for flexible name matching
		customer = session.query(Customer).filter(Customer.name.ilike(f"%{name}%")).first()

		stylist_obj = session.query(Stylist).filter(Stylist.name.ilike(f"%{stylist}%")).first()

		service_obj = session.query(Service).filter(Service.name.ilike(f"%{service}%")).first()

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
			time=datetime.strptime(time, "%H:%M").time(),
			created_at=datetime.now(),
		)

		session.add(appointment)
		session.commit()

		return f"""✅ Your appointment with **{stylist_obj.name}** for a **{service_obj.name}** is booked on **{date}** at **{time}**."""

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
        # Find customer
        customer = session.query(Customer).filter(func.lower(Customer.name) == name.lower()).first()
        if not customer:
            return f"❌ No customer found with the name '{name}'."

        # Find the original appointment
        appointment = session.query(Appointment).filter_by(
            customer_id=customer.id,
            date=date,
            time=time
        ).first()

        if not appointment:
            return f"❌ No appointment found for {name} on {date} at {time}."

        # Find the stylist for this appointment
        stylist = session.query(Stylist).filter(Stylist.id == appointment.stylist_id).first()
        if not stylist:
            return f"❌ No stylist found for the existing appointment."

        # ✅ Check if stylist is available at the new date/time
        stylist_booking_conflict = session.query(Appointment).filter(
            Appointment.stylist_id == stylist.id,
            Appointment.date == new_date,
            Appointment.time == new_time,
            Appointment.id != appointment.id  # exclude current appointment
        ).first()

        if stylist_booking_conflict:
            return f"❌ {stylist.name} is already booked on {new_date} at {new_time}."

        # OPTIONAL: Check stylist availability table (if you have one)
        if hasattr(stylist, 'availability') and not stylist.availability:
            return f"❌ {stylist.name} is currently unavailable for bookings."

        # Update appointment with new date/time
        appointment.date = new_date
        appointment.time = new_time
        appointment.updated_at = datetime.now()
        session.commit()

        return f"✅ Appointment for {name} with {stylist.name} has been rescheduled to {new_date} at {new_time}."

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
		if name:
			matched_customers = session.query(Customer).filter(
				text("similarity(name, :query) > 0.3")
			).params(query=name).order_by(
				text("similarity(name, :query) DESC")
			).all()
		else:
			matched_customers = session.query(Customer).all()
		
		if not matched_customers:
			return f"❌ No customer found matching '{name}'."

		# Take the first matching customer
		customer = matched_customers[0]

		# Filter appointments
		appointment_query = session.query(Appointment).join(Customer).filter(
			Appointment.customer_id == customer.id
		)

		if date:
			appointment_query = appointment_query.filter(Appointment.date == date)
		if time:
			appointment_query = appointment_query.filter(Appointment.time == time)

		appointments = appointment_query.all()

		if not appointments:
			return f"❌ No appointments found for '{customer.name}'" + \
				(f" on {date}" if date else '') + (f" at {time}" if time else '') + "."

		result = f"📅 Appointments for {customer.name}:\n"
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
		if query:
			matched_services = session.query(Service).filter(
				text("similarity(name, :query) > 0.3")
			).params(query=query).order_by(
				text("similarity(name, :query) DESC")
			).all()
		else:
			matched_services = session.query(Service).all()
   
		# if query:
		# 	like_pattern = f"%{query}%"
		# 	matched_services = session.query(Customer).filter(
		# 		Customer.name.ilike(like_pattern)  # Use .like for MySQL if ilike not supported
		# 	).all()
		# else:
		# 	matched_services = session.query(Customer).all()

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

		print(f"ILIKE matched services for '{query}': {[s.name for s in matched_services]}")

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

def get_stylist(query: str = None, date: str = None, time: str = None) -> Dict[str, Union[List[Dict], str]]:
    session = SessionLocal()
    try:
        # Step 1: Filter by name similarity if query given
        if query:
            matched_stylists = session.query(Stylist).filter(
                text("similarity(name, :query) > 0.3")
            ).params(query=query).order_by(
                text("similarity(name, :query) DESC")
            ).all()
        else:
            matched_stylists = session.query(Stylist).all()

        if query and not matched_stylists:
            return {
                'stylists': [],
                'message': f"Sorry, we couldn’t find any stylist named '{query}'.",
                'status': 'not_found'
            }

        # Step 2: Filter by day availability if date given
        if date:
            try:
                target_day = datetime.strptime(date, "%Y-%m-%d").strftime("%a")
                day_filtered = [
                    s for s in matched_stylists
                    if is_stylist_available_on_day(s.availability, target_day)
                ]
            except ValueError:
                return {
                    'stylists': [],
                    'message': f"Invalid date format: {date}. Please use YYYY-MM-DD.",
                    'status': 'error'
                }

            if not day_filtered:
                return {
                    'stylists': [],
                    'message': f"'{query}' is not available on {date}.",
                    'status': 'not_available'
                }

            matched_stylists = day_filtered

        # Step 3: Filter out stylists with a conflicting appointment
        if date and time:
            available_stylists = []
            conflict_found = False

            for stylist in matched_stylists:
                has_conflict = session.query(Appointment).filter(
                    Appointment.stylist_id == stylist.id,
                    Appointment.date == date,
                    Appointment.time == time
                ).first() is not None

                if has_conflict:
                    conflict_found = True
                else:
                    available_stylists.append(stylist)

            if not available_stylists and conflict_found:
                return {
                    'stylists': [],
                    'message': f"Sorry, {query} is already booked on {date} at {time}. Would you like to pick another time?",
                    'status': 'booked'
                }

            matched_stylists = available_stylists

        # Step 4: If still none found
        if not matched_stylists:
            return {
                'stylists': [],
                'message': "No stylists available for the requested time.",
                'status': 'not_found'
            }

        # Step 5: Serialize output
        serialized_stylists = [
            {"id": s.id, "name": s.name, "availability": s.availability}
            for s in matched_stylists
        ]

        return {
            'stylists': serialized_stylists,
            'message': f"Found {len(serialized_stylists)} stylist(s)"
                       + (f" matching '{query}'" if query else '')
                       + (f" available on {date}" if date else '')
                       + (f" at {time}" if time else ''),
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
		if query:
			matched_customers = session.query(Customer).filter(
				text("similarity(name, :query) > 0.3")
			).params(query=query).order_by(
				text("similarity(name, :query) DESC")
			).all()
		else:
			matched_customers = session.query(Customer).all()

		if not matched_customers:
			polite_message = (
				f"Sorry, we couldn't find any customers matching '{query}'. 🤔 Would you mind double-checking the spelling for me?"
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
			"required": ['query'],
		},
		"function": get_services
	},
	"get_stylist": {
        "description": (
            "Check available stylists by name, date, and time for booking appointments. "
            "Use this whenever the user mentions a stylist name, booking time, or wants to "
            "see who is available on a specific date."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Name of the stylist to search for"
                },
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format for checking availability"
                },
                "time": {
                    "type": "string",
                    "description": "Time in HH:MM 24-hour format for checking availability"
                }
            }
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
			"required": ['query']
		},
		"function": get_customers
	}, 
}
