import jwt ,os
import datetime
from fastapi import Request
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv 

load_dotenv()


JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')

# JWT token generation
def generate_jwt_token(email: str, user: dict, jwt_secret_key: str) -> str:
    payload = {
        "sub": email,
        "first_name": user.get("first_name"),
        "last_name": user.get("last_name"),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=1)
    }
    return jwt.encode(payload, jwt_secret_key, algorithm="HS256")


# Auth dependency
def get_current_user(request: Request) -> str:
    token = request.cookies.get("jwt_token")
    if not token:
        raise RedirectResponse(url="/login", status_code=302)
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
        email = payload.get("sub")
        if not email:
            raise jwt.InvalidTokenError("Missing subject in token")
        return email
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return RedirectResponse(url="/login", status_code=302)
