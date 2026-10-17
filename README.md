# ChatApp — Real-Time Chat Application

A full-stack real-time chat app with user auth, public rooms, direct messages, and online presence. Built with **Python, Flask, Flask-SocketIO (WebSockets), and SQLite**, wrapped in a glassmorphism "fantastico" UI.

## Features
- User registration & login (bcrypt password hashing via Werkzeug)
- Public chat rooms with persistent message history
- Direct 1-on-1 messaging (DMs)
- Real-time messaging via WebSockets (Flask-SocketIO)
- Online/offline user presence indicators
- Create new rooms on the fly
- Responsive layout (sidebar / chat / users list)
- Message timestamps and own-vs-other message styling

## Tech Stack
- **Backend:** Python 3, Flask, Flask-SocketIO, Flask-SQLAlchemy
- **Database:** SQLite (file-based, zero config)
- **Frontend:** HTML5, CSS3 (glassmorphism), vanilla JavaScript, Socket.IO client
- **Realtime:** WebSockets via Eventlet

## Run Locally

```bash
# 1. Enter the project folder
cd chat-app

# 2. Create a virtual environment (recommended)
python -m venv venv
venv\Scripts\activate      # Windows
source venv/bin/activate   # Mac/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the app
python app.py
```

Then open: **http://127.0.0.1:5001**

## Project Structure
```
chat-app/
├── app.py                 # Flask app + SocketIO events + SQLAlchemy models
├── requirements.txt       # Python dependencies
├── README.md
├── instance/              # SQLite database (created on first run)
├── static/
│   ├── css/style.css      # Glassmorphism UI
│   └── js/app.js          # Reserved for modular JS
└── templates/
    ├── base.html          # Base layout
    ├── login.html         # Sign in
    ├── register.html      # Sign up
    └── chat.html          # Main chat interface + embedded JS
```

## CV Talking Points
- **WebSockets:** Real-time bidirectional communication with Flask-SocketIO
- **Authentication:** Session-based auth with hashed passwords
- **Database:** Relational modeling (users, rooms, messages) with SQLAlchemy ORM
- **Frontend:** Responsive glassmorphism UI, DOM manipulation, fetch API
- **Concurrency:** Eventlet async mode for handling many simultaneous connections

## License
MIT — free to use for learning and portfolio projects.