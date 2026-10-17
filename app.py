"""
Real-Time Chat Application
--------------------------
A CV-worthy full-stack chat app built with Python, Flask, Flask-SocketIO, and SQLite.

Features:
- User registration & login (hashed passwords)
- Public chat rooms + private direct messages
- Real-time messaging via WebSockets
- Online/offline user presence
- Message history per room / per conversation
- Glassmorphism "fantastico" UI
"""

import os
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import or_, and_

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, abort
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_sqlalchemy import SQLAlchemy

# --------------------------------------------------------------------------- #
# Patch for Flask 3.x / Werkzeug 3.x compatibility with Flask-SocketIO.
# Flask-SocketIO tries to set ctx.session on the RequestContext, but newer
# Werkzeug removed the setter. We add a setter that simply ignores the value
# since we track users via sid_to_user mapping instead of flask.session.
# --------------------------------------------------------------------------- #
from flask.ctx import RequestContext

if not hasattr(RequestContext, "session_setter_patched"):
    _orig_session_getter = RequestContext.session.fget

    def _session_getter(self):
        try:
            return _orig_session_getter(self)
        except (AttributeError, RuntimeError):
            return {}

    def _session_setter(self, value):
        pass  # Ignore - we use sid_to_user for auth tracking

    RequestContext.session = property(_session_getter, _session_setter)
    RequestContext.session_setter_patched = True

# --------------------------------------------------------------------------- #
# App configuration
# --------------------------------------------------------------------------- #
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'chat.db')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Map socket.io session IDs to user IDs for tracking connected users
sid_to_user = {}

# --------------------------------------------------------------------------- #
# Database models
# --------------------------------------------------------------------------- #
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_seen = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_online = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "is_online": self.is_online,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
        }


class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    is_private = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    creator = db.relationship("User", foreign_keys=[created_by])
    messages = db.relationship("Message", backref="room", lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "is_private": self.is_private,
            "created_by": self.created_by,
        }


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey("room.id"), nullable=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)  # DMs
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", foreign_keys=[user_id])
    recipient = db.relationship("User", foreign_keys=[recipient_id])

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.user.username if self.user else None,
            "room_id": self.room_id,
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

        user = User(username=username)
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
            user.is_online = False
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
    rooms = Room.query.order_by(Room.created_at.desc()).all()
    users = User.query.filter(User.id != user.id).all()
    return render_template("chat.html", user=user, rooms=rooms, users=users)


@app.route("/api/rooms")
@login_required
def api_rooms():
    rooms = Room.query.order_by(Room.created_at.desc()).all()
    return jsonify([r.to_dict() for r in rooms])


@app.route("/api/users")
@login_required
def api_users():
    me = current_user()
    users = User.query.filter(User.id != me.id).all()
    return jsonify([u.to_dict() for u in users])


@app.route("/api/messages/<int:room_id>")
@login_required
def api_messages(room_id):
    room = db.session.get(Room, room_id)
    if not room:
        abort(404)
    msgs = (
        Message.query.filter_by(room_id=room_id)
        .order_by(Message.created_at.asc())
        .limit(100)
        .all()
    )
    return jsonify([m.to_dict() for m in msgs])


@app.route("/api/dm/<int:other_user_id>")
@login_required
def api_dm(other_user_id):
    me = current_user()
    other = db.session.get(User, other_user_id)
    if not other:
        abort(404)
    msgs = (
        Message.query.filter(
            Message.room_id.is_(None),
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


@app.route("/api/create_room", methods=["POST"])
@login_required
def api_create_room():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Room name required"}), 400

    room = Room(name=name, created_by=current_user().id)
    db.session.add(room)
    db.session.commit()
    return jsonify(room.to_dict()), 201


# --------------------------------------------------------------------------- #
# SocketIO events
# --------------------------------------------------------------------------- #
def get_user_from_sid(sid):
    return sid_to_user.get(sid)


@socketio.on("connect")
def on_connect():
    """Allow connection, mark user online if authenticated via session cookie."""
    uid = session.get("user_id")
    if uid:
        user = db.session.get(User, uid)
        if user:
            sid_to_user[request.sid] = user.id
            user.is_online = True
            user.last_seen = datetime.now(timezone.utc)
            db.session.commit()
            # Join personal room so DMs work
            join_room(str(user.id))
            # Auto-join everyone to the global "Talk to Everybody" room
            global_room = Room.query.filter_by(name="🌍 Global").first()
            if global_room:
                join_room(str(global_room.id))
            emit("user_status", {"user_id": user.id, "is_online": True}, broadcast=True)
            emit("auth_ok", {"user_id": user.id, "username": user.username})
    else:
        emit("auth_required", {"message": "Please log in"})


@socketio.on("disconnect")
def on_disconnect():
    uid = sid_to_user.pop(request.sid, None)
    if uid:
        user = db.session.get(User, uid)
        if user:
            user.is_online = False
            user.last_seen = datetime.now(timezone.utc)
            db.session.commit()
            emit("user_status", {"user_id": user.id, "is_online": False}, broadcast=True)


@socketio.on("join")
def on_join(data):
    """Join a public room room_id."""
    uid = sid_to_user.get(request.sid)
    if not uid:
        emit("error", {"message": "Not authenticated"})
        return

    room_id = data.get("room_id")
    if room_id:
        join_room(str(room_id))
        emit("joined", {"room_id": room_id}, room=str(room_id))


@socketio.on("leave")
def on_leave(data):
    room_id = data.get("room_id")
    if room_id:
        leave_room(str(room_id))


@socketio.on("send_message")
def on_send_message(data):
    """Handle incoming chat messages (public room or DM)."""
    uid = sid_to_user.get(request.sid)
    if not uid:
        emit("error", {"message": "Not authenticated"})
        return

    user = db.session.get(User, uid)
    if not user:
        return

    content = (data.get("content") or "").strip()
    room_id = data.get("room_id")
    recipient_id = data.get("recipient_id")

    if not content:
        return

    msg = Message(user_id=user.id, room_id=room_id, recipient_id=recipient_id, content=content)
    db.session.add(msg)
    db.session.commit()

    payload = msg.to_dict()

    if room_id:
        # Public room: broadcast to room (includes sender)
        emit("new_message", payload, room=str(room_id))
    elif recipient_id:
        # DM: send to both sender and recipient personal rooms
        emit("new_message", payload, room=str(user.id))
        emit("new_message", payload, room=str(recipient_id))


# --------------------------------------------------------------------------- #
# Entrypoint
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        # Ensure the "Talk to Everybody" global room exists
        if not Room.query.filter_by(name="🌍 Global").first():
            global_room = Room(
                name="🌍 Global",
                is_private=False,
                created_by=1,  # will be fixed on first user creation if needed
            )
            db.session.add(global_room)
            db.session.commit()
    socketio.run(app, host="127.0.0.1", port=5001, debug=True)
