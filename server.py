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
            "role": "user",
            "password": hashed.decode("utf-8")
        }).execute()
        if not result.data:
            return FileResponse("static/register_fail_page/index.html")

    except Exception as e:
        if "duplicate key" in str(e).lower():
            return HTMLResponse("<h3>Username already taken.</h3>", status_code=400)
        return HTMLResponse(f"<h3>Registration failed: {str(e)}</h3>", status_code=400)
    
    redir_response = RedirectResponse("/chatroom/global", status_code=303)
    redir_response.set_cookie(key="username", value=username, httponly=False)
    return redir_response

@app.get("/login")
async def login_page():
    return FileResponse("static/login_page/index.html")

@app.post("/login")
async def login_user(username: str = Form(...), password: str = Form(...)):
    result = supabase.table("users").select("password", ).eq("username", username).execute()
    
    if not result.data:
        return FileResponse("static/login_fail_page/index.html")

    entered_password_bytes = password.encode("utf-8")

    stored_password = result.data[0]["password"]
    bytes_stored_password = stored_password.encode("utf-8")

    if not bcrypt.checkpw(entered_password_bytes, bytes_stored_password):
        return FileResponse("static/login_fail_page/index.html")

    response = RedirectResponse("/chatroom/global", status_code=303)
    response.set_cookie(key="username", value=username, httponly=False)
    return response 

@app.get("/chatroom/{room_name}")
async def chatroom_page():
    return FileResponse("static/chat/index.html")

@app.websocket("/ws/{room_name}")
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
            "role": msg.get("role", "user"),
            "body": msg["body"],
            "timestamp": msg["timestamp"],
            "room_name": msg["room_name"]
        })
        await websocket.send_text(prev_msg_data)


    result = supabase.table("users").select("username, role").eq("username", username).execute()
    role = result.data[0]["role"]
    rooms[room_name][websocket] = {"username": username, "role": role}

    try:
        while True:
            msg_text = await websocket.receive_text()
            msg_data = json.loads(msg_text) 
            msg_data["username"] = rooms[room_name][websocket]["username"]
            msg_data["role"] = rooms[room_name][websocket]["role"]

            if await check_command(websocket, room_name, msg_data):
                continue

            supabase.table("messages").insert({
                        "username": msg_data["username"],
                        "role": msg_data["role"],
                        "body": msg_data["body"],
                        "timestamp": datetime.now().isoformat(),
                        "room_name": room_name}).execute()

            await broadcast(room_name, msg_data)
    except WebSocketDisconnect:
        rooms[room_name].pop(websocket, None)

def get_messages(room_name, limit=50):
    try:
        results = supabase.table("messages").select("*").eq("room_name", room_name).order("id", desc=True).limit(limit).execute()
        return results.data[::-1] if results.data else []
    except Exception as e:
        return []
    
async def check_command(self_conn, cur_room_name, message):
    if not message.get("body"):
        return False
    
    if message["body"].startswith("/"):
        
        error_msg = json.dumps({
                "username": "SERVER",
                "role": "[SERVER]",
                "body": f"Incorrect usage of command do /help for a list of commands!!",
                "timestamp": datetime.now().isoformat()
            })

        parts = message["body"].split(" ", 1)
        command = parts[0]

        if command.lower() == "/shout":
            value = parts[1] if len(parts) > 1 else ""
            shout_msg = {
                "username": f"SHOUT {message['username']}",
                "body": value,
                "timestamp": datetime.now().isoformat()
            }
            for room_name, connections in rooms.items():
                await broadcast(room_name, shout_msg)
            return True

        elif command.lower() == "/who":
            value = parts[1] if len(parts) > 1 else ""
            if value != "":
                users_inroom = list(rooms[value].values())
            else:
                users_inroom = list(rooms[cur_room_name].values())
            cur_users_msg = {
                "username": "SERVER",
                "body": f"Users in current room:\n{'\n   '.join(users_inroom)}",
                "timestamp": datetime.now().isoformat()
            }
            await broadcast(cur_room_name, cur_users_msg)
            return True
        elif command.lower() == "/msg":
            if len(parts) > 1 and parts[1].strip():
                value = parts [1]
            else:
                await self_conn.send_text(error_msg)
                return True
            try:
                reciever, pm = value.split(" ", 1) 
            except ValueError:
                await self_conn.send_text(error_msg)
                return False
            found = False

            for msg_room_name, msg_connections in rooms.items():
                for conn, user in msg_connections.items():
                    if user == reciever:
                        await conn.send_text(json.dumps({
                            "username": f"MSG from {message['username']}",
                            "body": pm,
                            "timestamp": datetime.now().isoformat() 
                        }))
                        await self_conn.send_text(json.dumps({
                            "username": f"MSG to {message['username']}",
                            "body": pm,
                            "timestamp": datetime.now().isoformat() 
                        }))
                        found = True
                        return True
            if not found:
                await self_conn.send_text(error_msg)

        elif command.lower() == "/help":
            if len(parts) > 1 and parts[1].strip():
                value = parts [1]
            else:
                value = "1"
            
            pg = value.strip() or "1"

            help_pages = {
            "1" : {
                "shout": "Usage: /shout [message] --- Sends a message to every room currently running does not log", 
                "msg": "Usage: /msg [reciever] [message] --- Sends a Private Message only to the reciever",
                "who": "Usage: /who [room_name] --- gives back a list of people in the specified room",
                "help": "Usage: /help [page] --- gives a list of all the commands with propper notation"
                }
            }
            help_text = "\n".join([f"{cmd}: {desc}" for cmd, desc in help_pages.get(pg, {}).items()])

            await self_conn.send_text(json.dumps({
                        "username": f"MSG to {message['username']}",
                        "body": help_text,
                        "timestamp": datetime.now().isoformat() 
                    }))

    else:
        return False  


async def broadcast(room_name, msg_data):
    for conn in list(rooms[room_name].keys()):
        try:
            if conn:
                await conn.send_text(json.dumps(msg_data))                

        except WebSocketDisconnect:
            rooms[room_name].pop(conn, None)  
 