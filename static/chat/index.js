console.log("hey")

const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";

const roomName = window.location.pathname.split("/").pop();  

const fileInput = document.getElementById('file_input');

const room_buttons = document.querySelectorAll("#room_nav button")

const URL = `${protocol}//${window.location.host}/ws/${roomName}`

const ws = new WebSocket(URL)
const chat_form = document.getElementById('chat_form')
const messageList = document.querySelector('#messages')
const text_area = document.querySelector("#text_input")
const room_list = document.querySelector("#room_list")

const username = getCookie("username")


ws.onopen = (event) =>{
    console.log("Connection established")
    sendMessage()
}

ws.onmessage = (event) =>{
    console.log("Received raw:", event.data);
    const eventData = JSON.parse(event.data)
    const role_class = eventData.role.toLowerCase();

    const message = `
                    <div class="message ${role_class}">
                    <p><b>[${eventData.role}] ${eventData.username}</b> : ${eventData.body}</p>
                    </div>`;
                    
    messageList.innerHTML += message;
    messageList.scrollTop = messageList.scrollHeight;
}

ws.onclose = (event) =>{
    console.log("Connection closed")
}

ws.onerror = (event) =>{
    console.log("Connection error")
}

chat_form.addEventListener('submit', (event) => {
    event.preventDefault();

    sendMessage();
})

text_area.addEventListener('keydown', (event) => {
    if (event.key == 'Enter' && !event.shiftKey){
        event.preventDefault();

        sendMessage();
    }
})

function sendMessage() {
    const formData = new FormData(chat_form);
    const message = formData.get('text_input');
    ws.send(JSON.stringify({"username": username,
                            "body": message
    }));
    chat_form.reset();
}

function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
}

room_buttons.forEach(btn => {
    btn.addEventListener('click', () => {
        const room = btn.dataset.room;
        if(room === "new"){
            const newRoom = prompt("Enter new room name:");
            if(newRoom) window.location.href = `/chatroom/${newRoom}`;
        } else {
            window.location.href = `/chatroom/${room}`;
        }
    });
});

function set_active_btn() {
    const cur_room = window.location.pathname.split("/").pop();
    room_buttons.forEach(b => {
        if (b.dataset.room === cur_room) {
            b.classList.add("active");
        }
        else {
            b.classList.remove("active");
        }
})}
/*
rooms_form.addEventListener('submit', (event) => {
    event.preventDefault()
    const room_input = document.getElementById('new_room_input');
    const roomName = room_input.value.trim();
    if(roomName) {
        createRoom(roomName);
        room_input.value = '';
   }
});
*/

function createRoom(room_name) {
    const li = document.createElement('li');
    li.textContent = `# ${room_name}`;
    li.classList.add('room_item');
    li.dataset.room = room_name
    
    li.addEventListener('click', () => {
        window.location.href = `/chatroom/${room_name}`;
    });
    
    room_list.appendChild(li);

}

fileInput.addEventListener('change', async () => {
    const file = fileInput.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch('/upload', { method: 'POST', body: formData });
    const data = await response.json();

    if (data.success) {
        ws.send(JSON.stringify({
            "username": username,
            body: "Sent a file: ",
            attachments: [{ url: data.url, name: data.name, type: data.type }]
        }));
    }
    fileInput.value = "";
});
set_active_btn()
