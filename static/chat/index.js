console.log("hey")

const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";

const roomName = window.location.pathname.split("/").pop();  

const rooms = document.querySelectorAll(".room_item")

const URL = `${protocol}//${window.location.host}/ws/${roomName}`

const ws = new WebSocket(URL)
const chat_form = document.getElementById('chat_form')
const rooms_form = document.getElementById('new_room_form')
const messageList = document.querySelector('#messages')
const text_area = document.querySelector("#text_input")
const room_list = document.querySelector("#room_list")


ws.onopen = (event) =>{
    console.log("Connection established")
    sendMessage()
}

ws.onmessage = (event) =>{
    console.log("Received raw:", event.data);
    const eventData = JSON.parse(event.data)
    const message = `
    <div class="message">
        <p><b>${eventData.username}</b> : ${eventData.body}</p>
    </div>`

    messageList.innerHTML += message

    console.log("Message: ", eventData)
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

rooms.forEach(room => {
    room.addEventListener('click', (event) => {
        const roomName = event.target.dataset.room;
        window.location.href = `/chatroom/${roomName}`;
    });
});

rooms_form.addEventListener('submit', (event) => {
    event.preventDefault()
    const room_input = document.getElementById('new_room_input');
    const roomName = room_input.value.trim();
    if(roomName) {
        createRoom(roomName);
        room_input.value = '';
   }
});

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

const username = getCookie("username")
