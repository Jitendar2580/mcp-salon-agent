import datetime
from typing import Optional
from fastapi import Depends, FastAPI, Form, Request, HTTPException, APIRouter
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv
from memory.memory import generate_response_with_memory
import os, json
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
import jwt
from utils.index import generate_jwt_token, get_current_user


load_dotenv()

app = FastAPI()
router = APIRouter()

# Load templates
templates = Jinja2Templates(directory="templates")


# Pydantic model for chat
class ChatRequest(BaseModel):
    message: str
    user_input: str
    session_id: str = "default"


# HTML route
# @router.get("/", response_class=HTMLResponse)
# async def read_root(request: Request):
#     return templates.TemplateResponse("index.html", {"request": request})
 
 
 
 
 
#  ----------------------------AUTHENTICATION-----------------
raw_users = os.getenv("USERS", "")
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')
USERS = {}

try:
    users_list = json.loads(raw_users)
    USERS = {}
    for user in users_list:
        USERS[user["email"].strip().lower()] = {
            "password": user["password"].strip(),
            "first_name": user["first_name"].strip(),
            "last_name": user["last_name"].strip()
        }

except json.JSONDecodeError:
    USERS = {}
    
    
    
# GET: Root redirect
@app.get("/")
async def index(request: Request):
    token = request.cookies.get("jwt_token")
    if token:
        try:
            jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
            return RedirectResponse(url="/dashboard")
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            pass
    return RedirectResponse(url="/login")

 

# GET: Login form
@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

# POST: Login handler
@app.post("/login")
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...)
):
    email = email.strip().lower()
    user = USERS.get(email)

    if user and user["password"] == password:
        token = generate_jwt_token(email, user, JWT_SECRET_KEY)
        expires = datetime.datetime.utcnow() + datetime.timedelta(hours=1)

        response = JSONResponse(content={"redirect": "/dashboard"})
        response.set_cookie(
            key="jwt_token",
            value=token,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="lax",
            expires=expires.strftime("%a, %d-%b-%Y %H:%M:%S GMT")
        )
        return response

    return JSONResponse(content={"error": "Invalid credentials"}, status_code=401)

# GET: Dashboard (protected)
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user_email: str = Depends(get_current_user)):
    user = USERS.get(user_email)
    full_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() if user else user_email

    response = templates.TemplateResponse("index.html", {"request": request, "user": full_name})
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

#  ----------------------------AUTHENTICATION-----------------

# Chat API route
@app.post("/api/chat")
async def chat(request: ChatRequest):
    if not request.message:
        raise HTTPException(status_code=400, detail="No message provided")

    result= generate_response_with_memory(request.user_input, request.session_id)
    return {"response": result}

 
# ✅ IMPORTANT: Include the router
app.include_router(router)
