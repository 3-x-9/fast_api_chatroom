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

rooms = {

               }

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
            return FileResponse("static/register_page_fail/index.html")

    except Exception as e:
        if "duplicate key" in str(e).lower():
            return HTMLResponse("<h3>Username already taken.</h3>", status_code=400)
        return HTMLResponse(f"<h3>Registration failed: {str(e)}</h3>", status_code=400)
    
    redir_response = RedirectResponse("/chatroom", status_code=303)
    redir_response.set_cookie(key="username", value=username, httponly=False)
    return redir_response

@app.get("/login")
async def login_page():
    return FileResponse("static/login_page/index.html")

@app.post("/login")
async def login_user(username: str = Form(...), password: str = Form(...)):
    result = supabase.table("users").select("password").eq("username", username).execute()
    
    if not result.data:
        return FileResponse("static/login_page_fail/index.html")

    entered_password_bytes = password.encode("utf-8")

    stored_password = result.data[0]["password"]
    bytes_stored_password = stored_password.encode("utf-8")

    if not bcrypt.checkpw(entered_password_bytes, bytes_stored_password):
        return FileResponse("static/login_page_fail/index.html")

    response = RedirectResponse("/chatroom", status_code=303)
    response.set_cookie(key="username", value=username, httponly=False)
    return response 

@app.get("/chatroom/{room_name}")
async def chatroom_page():
    return FileResponse("static/chat/index.html")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, room_name: str):
    await websocket.accept()

    if room_name not in rooms:
        rooms[room_name] = {}

    first_msg = await websocket.receive_text()
    first_data = json.loads(first_msg)
    username = first_data.get("username", "anonymous")
    
    for msg in get_messages(room_name):
        prev_msg_data = json.dumps({
            "username": msg["username"],
            "body": msg["body"],
            "timestamp": msg["timestamp"],
            "room_name": room_name
        })
        await websocket.send_text(prev_msg_data)

    rooms[room_name][websocket] = username

    try:
        while True:
            msg_text = await websocket.receive_text()
            msg_data = json.loads(msg_text) 
            msg_data["username"] = rooms[room_name][websocket]
            
            for conn in list(rooms[room_name].keys()):
                try:
                    supabase.table("messages").insert({
                        "username": username,
                        "body": msg_data["body"],
                        "timestamp": datetime.now().isoformat(),
                        "room_name": room_name}).execute()
                    if conn != websocket:
                        await conn.send_text(json.dumps(msg_data))                

                except WebSocketDisconnect:
                    rooms[room_name].pop(conn, None)
    except WebSocketDisconnect:
        rooms[room_name].pop(websocket, None)

def get_messages(room_name, limit=50):
    try:
        results = supabase.table("messages").select("*").eq("room_name", room_name).order("id", desc=True).limit(limit).execute()
        return results.data[::-1] if results.data else []
    except Exception as e:
        return []