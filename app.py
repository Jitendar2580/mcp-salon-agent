from typing import Dict
import uuid
from fastapi import FastAPI, Request, HTTPException, APIRouter
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv
from memory.memory import generate_response_with_memory

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
@router.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

chat_sessions: Dict[str, dict] = {}


def get_or_create_memory(session_id: str):
    if session_id not in chat_sessions:
        chat_sessions[session_id] = {
            "messages": [],
            "current_booking": {
                "customer": None,
                "service": None,
                "stylist": None,
                "date": None,
                "time": None
            }
        }
    return chat_sessions[session_id]




@app.post("/api/start-session")
async def start_session():
    session_id = str(uuid.uuid4())
    chat_sessions[session_id] = {} 
    return {"session_id": session_id}

@app.post("/api/chat")
async def chat_endpoint(request: dict):
    user_input = request.get("message", "")
    session_id = request.get("session_id")

    if not session_id:
        session_id = str(uuid.uuid4())
        print(f"🆕 Created new session: {session_id}")

    memory = get_or_create_memory(session_id)

    memory["messages"].append({"role": "user", "content": user_input})

    response = generate_response_with_memory(user_input, session_id)

    response["session_id"] = session_id
    return response


@app.post("/api/clear-session")
async def clear_session(request: dict):
    session_id = request.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="No session_id provided")

    if session_id in chat_sessions:
        del chat_sessions[session_id]
        return {"status": "Session cleared"}
    return {"status": "No session found"}

 
# ✅ IMPORTANT: Include the router
app.include_router(router)
