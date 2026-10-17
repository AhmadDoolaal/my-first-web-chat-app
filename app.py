"""
Discord Clone — Real-Time Chat Application
------------------------------------------
A full-stack Discord replica built with Python, Flask, Flask-SocketIO, and SQLite.

Features:
- Servers (guilds) with text & voice channels
- Direct Messages between users
- User registration & login (hashed passwords)
- Real-time messaging via WebSockets
- Online/Idle/Do Not Disturb/Offline status
- Member list with roles
- Colored avatars with initials
- Discord dark theme UI
"""

import os
import random
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import or_, and_

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, abort
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_sqlalchemy import SQLAlchemy
from flask.ctx import RequestContext

# --------------------------------------------------------------------------- #
# Flask 3.x / Werkzeug 3.x compatibility patch for Flask-SocketIO
# --------------------------------------------------------------------------- #
if not hasattr(RequestContext, "session_setter_patched"):
    _orig_session_getter = RequestContext.session.fget

    def _session_getter(self):
        try:
            return _orig_session_getter(self)
        except (AttributeError, RuntimeError):
            return {}

    def _session_setter(self, value):
        pass  # Ignore — we track users via sid_to_user mapping

    RequestContext.session = property(_session_getter, _session_setter)
    RequestContext.session_setter_patched = True

# --------------------------------------------------------------------------- #
# App configuration
# --------------------------------------------------------------------------- #
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'discord.db')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Map socket.io session IDs to user IDs
sid_to_user = {}

# Discord avatar colors
AVATAR_COLORS = [
    "#5865f2", "#eb459e", "#f04747", "#faa81a", "#43b581",
    "#a3a3a3", "#99aab5", "#7289da", "#5b6aae", "#4f545c",
]

# --------------------------------------------------------------------------- #
# Database models
# --------------------------------------------------------------------------- #
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    avatar_color = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="online")  # online, idle, dnd, offline
    custom_status = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    server_memberships = db.relationship("ServerMember", back_populates="user", cascade="all, delete-orphan")
    messages = db.relationship("Message", back_populates="author", foreign_keys="Message.user_id", cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "avatar_color": self.avatar_color,
            "status": self.status,
            "custom_status": self.custom_status,
            "initial": self.username[0].upper() if self.username else "?",
        }


class Server(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    icon = db.Column(db.String(10), nullable=True)  # emoji
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    owner = db.relationship("User", foreign_keys=[owner_id])
    members = db.relationship("ServerMember", back_populates="server", cascade="all, delete-orphan")
    channels = db.relationship("Channel", back_populates="server", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "icon": self.icon or "💬",
            "owner_id": self.owner_id,
        }


class ServerMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    server_id = db.Column(db.Integer, db.ForeignKey("server.id"), nullable=False)
    role = db.Column(db.String(50), nullable=False, default="Member")
    joined_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", back_populates="server_memberships")
    server = db.relationship("Server", back_populates="members")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "server_id": self.server_id,
            "role": self.role,
        }


class Channel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20), nullable=False, default="text")  # text, voice
    server_id = db.Column(db.Integer, db.ForeignKey("server.id"), nullable=False)
    position = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    server = db.relationship("Server", back_populates="channels")
    messages = db.relationship("Message", back_populates="channel", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "server_id": self.server_id,
        }


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    channel_id = db.Column(db.Integer, db.ForeignKey("channel.id"), nullable=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)  # DMs
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    author = db.relationship("User", foreign_keys=[user_id], back_populates="messages")
    channel = db.relationship("Channel", foreign_keys=[channel_id], back_populates="messages")
    recipient = db.relationship("User", foreign_keys=[recipient_id])

    def to_dict(self):
        author = self.author
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": author.username if author else "Unknown",
            "avatar_color": author.avatar_color if author else "#72767d",
            "initial": author.username[0].upper() if author else "?",
            "channel_id": self.channel_id,
            "recipient_id": self.recipient_id,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
        }


# --------------------------------------------------------------------------- #
# Auth helpers
# --------------------------------------------------------------------------- #
def login_required(view_fn):
    from functools import wraps

    @wraps(view_fn)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view_fn(*args, **kwargs)
    return wrapped


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return db.session.get(User, uid)


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if not username or not password:
            return render_template("register.html", error="Username and password required.")
        if User.query.filter_by(username=username).first():
            return render_template("register.html", error="Username already taken.")
        if len(password) < 4:
            return render_template("register.html", error="Password must be at least 4 characters.")

        user = User(username=username, avatar_color=random.choice(AVATAR_COLORS))
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        session["user_id"] = user.id
        session["username"] = user.username
        return redirect(url_for("dashboard"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            return render_template("login.html", error="Invalid username or password.")

        session["user_id"] = user.id
        session["username"] = user.username
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    uid = session.get("user_id")
    if uid:
        user = db.session.get(User, uid)
        if user:
            user.status = "offline"
            user.last_seen = datetime.now(timezone.utc)
            db.session.commit()
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    if not user:
        session.clear()
        return redirect(url_for("login"))

    # Servers user is member of
    memberships = ServerMember.query.filter_by(user_id=user.id).all()
    servers = [m.server for m in memberships]

    # All other users for DMs
    other_users = User.query.filter(User.id != user.id).all()

    return render_template(
        "discord.html",
        user=user,
        servers=[s.to_dict() for s in servers],
        users=[u.to_dict() for u in other_users],
    )


# ----- Server API -----
@app.route("/api/servers")
@login_required
def api_servers():
    user = current_user()
    memberships = ServerMember.query.filter_by(user_id=user.id).all()
    return jsonify([m.server.to_dict() for m in memberships])


@app.route("/api/servers/new", methods=["POST"])
@login_required
def api_create_server():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    icon = (data.get("icon") or "💬").strip()
    if not name:
        return jsonify({"error": "Server name required"}), 400

    user = current_user()
    server = Server(name=name, icon=icon, owner_id=user.id)
    db.session.add(server)
    db.session.flush()

    # Add creator as Owner
    membership = ServerMember(user_id=user.id, server_id=server.id, role="Owner")
    db.session.add(membership)
    db.session.commit()
    return jsonify(server.to_dict()), 201


@app.route("/api/servers/<int:server_id>/channels")
@login_required
def api_channels(server_id):
    server = db.session.get(Server, server_id)
    if not server:
        abort(404)
    # Check membership
    member = ServerMember.query.filter_by(user_id=current_user().id, server_id=server_id).first()
    if not member:
        abort(403)
    channels = Channel.query.filter_by(server_id=server_id).order_by(Channel.position.asc()).all()
    return jsonify([c.to_dict() for c in channels])


@app.route("/api/servers/<int:server_id>/channels/new", methods=["POST"])
@login_required
def api_create_channel(server_id):
    server = db.session.get(Server, server_id)
    if not server:
        abort(404)
    member = ServerMember.query.filter_by(user_id=current_user().id, server_id=server_id).first()
    if not member or member.role not in ("Owner", "Admin", "Moderator"):
        return jsonify({"error": "Insufficient permissions"}), 403

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    ctype = data.get("type", "text")
    if not name:
        return jsonify({"error": "Channel name required"}), 400

    channel = Channel(name=name, type=ctype, server_id=server_id)
    db.session.add(channel)
    db.session.commit()
    return jsonify(channel.to_dict()), 201


@app.route("/api/servers/<int:server_id>/members")
@login_required
def api_members(server_id):
    server = db.session.get(Server, server_id)
    if not server:
        abort(404)
    members = ServerMember.query.filter_by(server_id=server_id).all()
    result = []
    for m in members:
        u = m.user.to_dict()
        u["role"] = m.role
        result.append(u)
    return jsonify(result)


# ----- Messages -----
@app.route("/api/messages/<int:channel_id>")
@login_required
def api_channel_messages(channel_id):
    channel = db.session.get(Channel, channel_id)
    if not channel:
        abort(404)
    member = ServerMember.query.filter_by(user_id=current_user().id, server_id=channel.server_id).first()
    if not member:
        abort(403)
    msgs = (
        Message.query.filter_by(channel_id=channel_id)
        .order_by(Message.created_at.asc())
        .limit(100)
        .all()
    )
    return jsonify([m.to_dict() for m in msgs])


@app.route("/api/dm/<int:other_user_id>")
@login_required
def api_dm_messages(other_user_id):
    me = current_user()
    other = db.session.get(User, other_user_id)
    if not other:
        abort(404)
    msgs = (
        Message.query.filter(
            Message.channel_id.is_(None),
            or_(
                and_(Message.user_id == me.id, Message.recipient_id == other_user_id),
                and_(Message.user_id == other_user_id, Message.recipient_id == me.id),
            ),
        )
        .order_by(Message.created_at.asc())
        .limit(100)
        .all()
    )
    return jsonify([m.to_dict() for m in msgs])


# --------------------------------------------------------------------------- #
# SocketIO events
# --------------------------------------------------------------------------- #
def get_user_from_sid(sid):
    return sid_to_user.get(sid)


@socketio.on("connect")
def on_connect():
    uid = session.get("user_id")
    if uid:
        user = db.session.get(User, uid)
        if user:
            sid_to_user[request.sid] = user.id
            user.status = "online"
            db.session.commit()
            join_room(str(user.id))  # personal room for DMs
            emit("auth_ok", {"user_id": user.id, "username": user.username})
            emit("user_status", {"user_id": user.id, "status": "online"}, broadcast=True)
    else:
        emit("auth_required", {"message": "Please log in"})


@socketio.on("disconnect")
def on_disconnect():
    uid = sid_to_user.pop(request.sid, None)
    if uid:
        user = db.session.get(User, uid)
        if user:
            user.status = "offline"
            db.session.commit()
            emit("user_status", {"user_id": uid, "status": "offline"}, broadcast=True)


@socketio.on("join_channel")
def on_join_channel(data):
    uid = sid_to_user.get(request.sid)
    if not uid:
        emit("error", {"message": "Not authenticated"})
        return
    channel_id = data.get("channel_id")
    if channel_id:
        join_room(f"channel_{channel_id}")


@socketio.on("leave_channel")
def on_leave_channel(data):
    channel_id = data.get("channel_id")
    if channel_id:
        leave_room(f"channel_{channel_id}")


@socketio.on("send_message")
def on_send_message(data):
    uid = sid_to_user.get(request.sid)
    if not uid:
        emit("error", {"message": "Not authenticated"})
        return

    user = db.session.get(User, uid)
    if not user:
        return

    content = (data.get("content") or "").strip()
    channel_id = data.get("channel_id")
    recipient_id = data.get("recipient_id")

    if not content:
        return

    msg = Message(user_id=user.id, channel_id=channel_id, recipient_id=recipient_id, content=content)
    db.session.add(msg)
    db.session.commit()
    payload = msg.to_dict()

    if channel_id:
        emit("new_message", payload, room=f"channel_{channel_id}")
    elif recipient_id:
        emit("new_message", payload, room=str(user.id))
        emit("new_message", payload, room=str(recipient_id))


# --------------------------------------------------------------------------- #
# Entrypoint
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    socketio.run(app, host="127.0.0.1", port=5001, debug=True)
