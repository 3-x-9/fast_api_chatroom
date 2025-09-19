from fastapi import FastAPI, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
# import aiosqlite ==> not needed anymore switched to PostgreSQL 
from databases import Database
from contextlib import asynccontextmanager
import json
from datetime import datetime
import os 
import asyncpg

connections = {}

USER_DATABASE_URL = os.getenv("USER_DATABASE_URL")
MSG_DATABASE_URL = os.getenv("MSG_DATABASE_URL")
user_db = Database(USER_DATABASE_URL)
msg_db = Database(MSG_DATABASE_URL)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global user_db, msg_db
    # init user db for passwords/usernames
    await user_db.connect()
    await msg_db.connect()

    yield
    
    await user_db.disconnect()
    await msg_db.disconnect()

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
    global user_db

    existing = await user_db.fetch_one("SELECT id FROM users WHERE username = :username", {"username": username})
    if existing:
        return HTMLResponse("<h3>Username already taken.</h3>")
    query = "INSERT INTO users (username, password) VALUES (:username, :password)"
    await user_db.execute(query, {"username": username, "password": password})
    return RedirectResponse("/chatroom", status_code=303)
    
@app.get("/login")
async def login_page():
    return FileResponse("static/login_page/index.html")

@app.post("/login")
async def login_user(username: str = Form(...), password: str = Form(...)):
    global user_db
    query = "SELECT password FROM users WHERE username = :username"
    row = await user_db.fetch_one(query, {"username": username})
    if row and row["password"] == password:
        response = RedirectResponse("/chatroom", status_code=303)
        response.set_cookie(key="username", value=username, httponly=False)
        return response 
    else:
        return HTMLResponse("<h3>Wrong password or username.</h3>")


@app.get("/chatroom")
async def chatroom_page():
    return FileResponse("static/chat/index.html")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    first_msg = await websocket.receive_text()
    first_data = json.loads(first_msg)
    username = first_data.get("username", "anonymous")
    
    for msg_username, body, timestamp in await get_messages():
        prev_msg_data = json.dumps({
            "username": msg_username,
            "body": body,
            "timestamp": timestamp
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
                    query = "INSERT INTO messages (username, body, timestamp) VALUES (:username, :body, :timestamp)"
                    await msg_db.execute(query, {
                                                "username": username,
                                                "body": msg_data["body"],
                                                "timestamp": datetime.now().isoformat()})
                    await conn.send_text(json.dumps(msg_data))                

                except WebSocketDisconnect:
                    connections.pop(conn, None)
    except WebSocketDisconnect:
        connections.pop(websocket, None)

async def get_messages(limit=50):
    global msg_db
    query = f"SELECT username, body, timestamp FROM messages ORDER BY id DESC LIMIT {limit}"
    rows = await msg_db.fetch_all(query)
    return rows[::-1]