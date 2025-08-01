from fastapi import FastAPI, Request, HTTPException, APIRouter
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv
from routes.route_2 import route_query_to_tool_2

load_dotenv()

app = FastAPI()
router = APIRouter()

# Load templates
templates = Jinja2Templates(directory="templates")


# Pydantic model for chat
class ChatRequest(BaseModel):
    message: str


# HTML route
@router.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# Chat API route
@app.post("/api/chat")
async def chat(request: ChatRequest):
    if not request.message:
        raise HTTPException(status_code=400, detail="No message provided")

    result = route_query_to_tool_2(request.message)
    return {"response": result}

 
# ✅ IMPORTANT: Include the router
app.include_router(router)
