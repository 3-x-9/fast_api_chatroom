from fastapi import FastAPI, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import aiosqlite
from contextlib import asynccontextmanager
import json
from datetime import datetime

user_db = None
msg_db = None

connections = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    global user_db, msg_db
    # init user db for passwords/usernames
    user_db = await aiosqlite.connect("user.db")
    await user_db.execute("""CREATE TABLE IF NOT EXISTS users (
                          id INTEGER PRIMARY KEY AUTOINCREMENT,
                          username TEXT UNIQUE NOT NULL,
                          password TEXT NOT NULL
                          )"""
                          )
    await user_db.commit()

    # init msg db for persisting msgs/history
    msg_db = await aiosqlite.connect("messages.db")
    await msg_db.execute("""CREATE TABLE IF NOT EXISTS messages (
                          id INTEGER PRIMARY KEY AUTOINCREMENT,
                          username TEXT NOT NULL,
                          body TEXT NOT NULL,
                          timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                          )"""
                          )
    await msg_db.commit()
    
    yield
    
    await user_db.close()
    await msg_db.close()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def homepage():
    return HTMLResponse("""<h1> Welcome to the chatroom! </h1>
                        <a href="/login"> Login </a> | <a href="/register"> Register </a>""")

@app.get("/register")
async def register_page():
    return HTMLResponse("""
                        <h1>Register</h1>
                        <form method="post">
                            <input name="username" placeholder="Username">
                            <input name="password" type="password" placeholder="Password">
                            <button type="submit">Register</button>
                        </form>
                        """)

@app.post("/register")
async def register_user(username: str = Form(...), password: str = Form(...)):
    global user_db
    try:
        await user_db.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
        await user_db.commit()
        return HTMLResponse(f"<h3>User {username} registered successfully!</h3>")
    except aiosqlite.IntegrityError:
        return HTMLResponse("<h3>Username already taken.</h3>")

@app.get("/login")
async def login_page():
    return HTMLResponse("""
                        <h1>Login</h1>
                        <form method="post">
                            <input name="username" placeholder="Username">
                            <input name="password" type="password" placeholder="Password">
                            <button type="submit">Login</button>
                        </form>
                        """)

@app.post("/login")
async def login_user(username: str = Form(...), password: str = Form(...)):
    global user_db
    async with user_db.execute("SELECT password FROM users WHERE username = ?", (username,)) as cursor:
        row = await cursor.fetchone()
        if row and row[0] == password:
            response = RedirectResponse("/chatroom", status_code=303)
            response.set_cookie(key="username", value=username, httponly=False)
            return response 
        else:
            return HTMLResponse("<h3>Wrong password or username.</h3>")


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/chatroom")
async def chatroom_page():
    return FileResponse("static/index.html")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    first_msg = await websocket.receive_text()
    first_data = json.loads(first_msg)
    username = first_data.get("username", "anonymous")
    
    for username, body, timestamp in await get_messages():
        prev_msg_data = json.dumps({
            "username": username,
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
                    await msg_db.execute("INSERT INTO MESSAGES (username, body, timestamp) VALUES (?, ?, ?)", (username, msg_data["body"], datetime.now().isoformat()))
                    await msg_db.commit()
                    await conn.send_text(json.dumps(msg_data))                

                except WebSocketDisconnect:
                    connections.pop(conn, None)
    except WebSocketDisconnect:
        connections.pop(websocket, None)

async def get_messages(limit=50):
    global msg_db
    cursor = await msg_db.execute("SELECT username, body, timestamp FROM messages ORDER BY id DESC LIMIT ?", (limit,))
    rows = await cursor.fetchall()
    await cursor.close()
    return rows[::-1]