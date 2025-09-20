from fastapi import FastAPI, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
# import aiosqlite ==> not needed anymore switched to PostgreSQL 
from contextlib import asynccontextmanager
import json
from datetime import datetime
import os 
from dotenv import load_dotenv
from pathlib import Path
import psycopg2
import bcrypt

from supabase import create_client


env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

connections = {}

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")

supabase = create_client(url, key)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # init user db for passwords/usernames
    yield
    
app = FastAPI(lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def homepage():
    return FileResponse("static/landing_page/index.html")

@app.get("/register")
async def register_page():
    return FileResponse("static/register_page/index.html")

@app.post("/register")
async def register_user(username: str = Form(...), password: str = Form(...)):
    byte_password = password.encode("utf-8")
    hashed = bcrypt.hashpw(byte_password, bcrypt.gensalt())

    try:
        result = supabase.table("users").insert({
            "username": username,
            "password": hashed.decode("utf-8")
        }).execute()
        if not result.data:
            return HTMLResponse("<h3>Registration failed.</h3>", status_code=400)

    except Exception as e:
        if "duplicate key" in str(e).lower():
            return HTMLResponse("<h3>Username already taken.</h3>", status_code=400)
        return HTMLResponse(f"<h3>Registration failed: {str(e)}</h3>", status_code=400)
    return RedirectResponse("/chatroom", status_code=303)
    
@app.get("/login")
async def login_page():
    return FileResponse("static/login_page/index.html")

@app.post("/login")
async def login_user(username: str = Form(...), password: str = Form(...)):
    result = supabase.table("users").select("password").eq("username", username).execute()
    
    if not result.data:
        return HTMLResponse("<h3>User not found.</h3>", status_code=400)
    
    entered_password_bytes = password.encode("utf-8")

    stored_password = result.data[0]["password"]
    bytes_stored_password = stored_password.encode("utf-8")

    if not bcrypt.checkpw(entered_password_bytes, bytes_stored_password)
        return HTMLResponse("<h3>Wrong password.</h3>", status_code=400)

    response = RedirectResponse("/chatroom", status_code=303)
    response.set_cookie(key="username", value=username, httponly=False)
    return response 

@app.get("/chatroom")
async def chatroom_page():
    return FileResponse("static/chat/index.html")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    first_msg = await websocket.receive_text()
    first_data = json.loads(first_msg)
    username = first_data.get("username", "anonymous")
    
    for msg in get_messages():
        prev_msg_data = json.dumps({
            "username": msg["username"],
            "body": msg["body"],
            "timestamp": msg["timestamp"]
        })
        await websocket.send_text(prev_msg_data)

    connections[websocket] = username

    try:
        while True:
            msg_text = await websocket.receive_text()
            msg_data = json.loads(msg_text) 
            msg_data["username"] = connections[websocket]
            
            for conn in list(connections):
                try:
                    supabase.table("messages").insert({
                        "username": username,
                        "body": msg_data["body"],
                        "timestamp": datetime.now().isoformat()}).execute()
                    await conn.send_text(json.dumps(msg_data))                

                except WebSocketDisconnect:
                    connections.pop(conn, None)
    except WebSocketDisconnect:
        connections.pop(websocket, None)

def get_messages(limit=50):
    try:
        results = supabase.table("messages").select("*").order("id", desc=True).limit(limit).execute()
        return results.data[::-1] if results.data else []
    except Exception as e:
        return []