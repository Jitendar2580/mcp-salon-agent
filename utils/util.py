import os , re
import requests
from sqlalchemy import func


def get_weather(city: str) -> str:
	api_key = os.getenv("WEATHER_API_KEY")
	url = f"http://api.weatherapi.com/v1/current.json?key={api_key}&q={city}"

	try:
		res = requests.get(url)
		data = res.json()
		return f"{data['location']['name']}: {data['current']['temp_c']}°C, {data['current']['condition']['text']}"
	except Exception as e:
		return f"Weather fetch failed: {e}"



def is_stylist_available_on_day(availability_str: str, day_abbr: str) -> bool:
	"""
	Checks if a stylist is available on the given day abbreviation (e.g. 'Mon').
	availability_str example: 'Mon-Fri 9am-5pm'
	"""
	if not availability_str:
		return False

	match = re.match(r"(\w{3})(?:-(\w{3}))?", availability_str)
	if not match:
		return False

	start_day, end_day = match.groups()
	days_order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

	if start_day and end_day:
		start_idx = days_order.index(start_day)
		end_idx = days_order.index(end_day)
		if start_idx <= end_idx:
			valid_days = days_order[start_idx:end_idx + 1]
		else:
			valid_days = days_order[start_idx:] + days_order[:end_idx + 1]
	else:
		valid_days = [start_day]

	return day_abbr in valid_days




def one_substitution_like_filters(column, term, substring=False):
    """
    Build OR'ed LIKE patterns that allow exactly one character to differ.
    - column: SQLAlchemy column (e.g., Customer.name)
    - term:   user query (string)
    - substring: if True, wrap each pattern with %...% for substring matches
    """
    term = (term or "").strip()
    if not term:
        return []

    patterns = []
    for i in range(len(term)):
        # replace the i-th character with a single-character wildcard
        p = term[:i] + '_' + term[i+1:]
        patterns.append(f"%{p}%" if substring else p)

    # case-insensitive LIKE using LOWER() for MySQL/SQL Server
    return [func.lower(column).like(p.lower()) for p in patterns]






	# "weather": {
	# 	"description": "Get current weather information for a city.",
	# 	"parameters": {
	# 		"type": "object",
	# 		"properties": {
	# 			"city": {
	# 				"type": "string",
	# 				"description": "City name (e.g., Tokyo, Paris)"
	# 			}
	# 		},
	# 		"required": ["city"]
	# 	},
	# 	"function": get_weather,
	# }, 
