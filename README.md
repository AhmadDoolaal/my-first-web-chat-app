# 💬 Somcord — Discord Clone

A fully responsive, real-time chat application modeled after Discord, built with **Python, Flask, Flask-SocketIO, and SQLite**.

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.1.3-000.svg)](https://flask.palletsprojects.com)
[![Flask-SocketIO](https://img.shields.io/badge/SocketIO-5.5.1-000.svg)](https://flask-socketio.com)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-blue.svg)](https://sqlalchemy.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## 🚀 Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/AhmadDoolaal/my-first-web-chat-app.git
cd my-first-web-chat-app

# 2. Create and activate a virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the application
python app.py
```

Then open your browser to: **http://127.0.0.1:5001**

---

## 🎯 Features

| Feature | Description |
|---------|-------------|
| 🖥 **Somcord Dark Theme** | Full Discord-inspired dark UI with custom colors |
| 📱 **Fully Responsive** | Mobile-friendly with collapsible sidebars and hamburger menu |
| 🏠 **Servers** | Create servers with custom names and emoji icons |
| 💬 **Channels** | Text & voice channels inside each server |
| 🌍 **Universal Channel** | A global chat channel (`#🌍 universal`) where every logged-in user can talk |
| 👥 **Direct Messages** | Chat 1-on-1 with friends |
| 🤝 **Add Friend** | Send, accept, or decline friend requests |
| 📋 **Member List** | View server members with roles and online status |
| 🔴 **Status Indicators** | Online / Idle / Do Not Disturb / Offline |
| 🎨 **Colored Avatars** | Initials in unique colored circles |
| 🔐 **Authentication** | Register/Login with unique usernames and hashed passwords |
| ⚡ **Real-time** | WebSocket-powered instant messaging via Flask-SocketIO |

---

## 📁 Project Structure

```
my-first-web-chat-app/
├── app.py                  # Somcord backend (servers, channels, DMs, friends, SocketIO)
├── requirements.txt        # Python dependencies
├── README.md               # This file
├── .gitignore              # Git ignore rules
├── instance/               # SQLite database (created automatically)
│   └── somcord.db
├── static/css/style.css    # Legacy glassmorphism CSS (kept for login/register)
└── templates/
    ├── base.html           # Base layout
    ├── login.html          # Sign-in page
    ├── register.html       # Sign-up page
    └── somcord.html        # Full Discord replica UI + embedded CSS + JS
```

---

## 🔌 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Redirect to login or dashboard |
| `/register` | GET/POST | User registration (unique usernames) |
| `/login` | GET/POST | User login |
| `/logout` | GET | Logout |
| `/dashboard` | GET | Main Somcord interface |
| `/api/servers` | GET | List user's servers |
| `/api/servers/new` | POST | Create a new server |
| `/api/servers/join` | POST | Join a server by ID |
| `/api/servers/list` | GET | List all public servers |
| `/api/servers/<id>/channels` | GET | List channels in a server |
| `/api/servers/<id>/channels/new` | POST | Create a channel |
| `/api/servers/<id>/members` | GET | List server members |
| `/api/messages/<channel_id>` | GET | Get channel message history |
| `/api/dm/<user_id>` | GET | Get direct message history |
| `/api/friends` | GET | List accepted friends |
| `/api/friends/requests` | GET | Incoming friend requests |
| `/api/friends/sent` | GET | Outgoing friend requests |
| `/api/friends/add` | POST | Send a friend request |
| `/api/friends/requests/<id>/accept` | POST | Accept a friend request |
| `/api/friends/requests/<id>/decline` | POST | Decline a friend request |

---

## 🎮 How to Use

### 1. Create an Account
Register with a **unique username** (2–32 characters) and password.

### 2. Create or Join a Server
- Click **+** in the server sidebar to create your own server
- Use **Join a Server** to enter an existing server by its ID

### 3. Universal Chat
Every user is automatically part of the **#🌍 universal** channel. Select any server, then click the universal channel at the top of the channel list to chat with everyone on Somcord.

### 4. Add Friends
- Go to the **Friends** section in the left sidebar
- Click **+** to send a friend request by username
- Your friend receives a request they can accept or decline
- Once friends, you can open a direct message with them

### 5. Chat in Real-Time
Select a channel or friend, type your message, and hit **Send**. Messages appear instantly for everyone in that channel or conversation.

---

## 🎨 UI Highlights

- **Discord dark theme** — `#2f3136`, `#36393f`, `#40444b` palette
- **Server sidebar** with emoji icons
- **Channel list** with text/voice indicators
- **Member sidebar** showing online status and roles
- **Message bubbles** with timestamps and colored author initials
- **Hamburger menu** on mobile for collapsible sidebars
- **Modals** for creating servers, joining servers, adding friends, and creating channels

---

## 🧠 CV / Portfolio Talking Points

- **Full-Stack Development:** Complete Flask application with frontend, backend, and database
- **Real-Time Communication:** WebSocket implementation with Flask-SocketIO for instant messaging
- **Database Design:** Relational schema with SQLAlchemy ORM (Users, Servers, Channels, Messages, Friendships, ServerMemberships)
- **Authentication:** Secure user registration/login with Werkzeug password hashing and session management
- **Responsive Design:** Mobile-first CSS with collapsible sidebars and hamburger navigation
- **Friend System:** Bidirectional friend requests with pending/accepted states
- **JSON Data Model:** Flexible API endpoints returning structured JSON

---

## 📄 License

MIT License — see the [LICENSE](LICENSE) file for details.

---

## 👨‍💻 Author

**AhmadDoolaal**  
GitHub: https://github.com/AhmadDoolaal

---

⭐ **Star this repo** if you found it helpful!
