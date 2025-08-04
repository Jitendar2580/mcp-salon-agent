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


# Chat API route
@app.post("/api/chat")
async def chat(request: ChatRequest):
    if not request.message:
        raise HTTPException(status_code=400, detail="No message provided")

    result= generate_response_with_memory(request.user_input, request.session_id)
    return {"response": result}

 
# ✅ IMPORTANT: Include the router
app.include_router(router)
