"""
Somcord — Real-Time Chat Application (Discord Clone)
----------------------------------------------------
A full-stack Somcord replica built with Python, Flask, Flask-SocketIO, and SQLite.

Features:
- Servers (guilds) with text & voice channels
- Universal chat channel (everyone can post)
- Direct Messages between friends
- Add friend / friend request system
- User registration & login (unique usernames, hashed passwords)
- Real-time messaging via WebSockets
- Online/Idle/Do Not Disturb/Offline status
- Member list with roles
- Colored avatars with initials
- Fully responsive UI (mobile-friendly)
- Somcord dark theme
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
        pass

    RequestContext.session = property(_session_getter, _session_setter)
    RequestContext.session_setter_patched = True

# --------------------------------------------------------------------------- #
# App configuration
# --------------------------------------------------------------------------- #
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'somcord.db')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

sid_to_user = {}

AVATAR_COLORS = [
    "#5865f2", "#eb459e", "#f04747", "#faa81a", "#43b581",
    "#a3a3a3", "#99aab5", "#7289da", "#5b6aae", "#4f545c",
]

UNIVERSAL_CHANNEL_NAME = "🌍 universal"


# --------------------------------------------------------------------------- #
# Database models
# --------------------------------------------------------------------------- #
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    avatar_color = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="online")
    custom_status = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    server_memberships = db.relationship("ServerMember", back_populates="user", cascade="all, delete-orphan")
    messages = db.relationship("Message", back_populates="author", foreign_keys="Message.user_id", cascade="all, delete-orphan")

    # Friends (accepted friendships where this user is user1 or user2)
    friendships_sent = db.relationship("Friendship", foreign_keys="Friendship.user1_id", back_populates="user1", cascade="all, delete-orphan")
    friendships_received = db.relationship("Friendship", foreign_keys="Friendship.user2_id", back_populates="user2", cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_friends_with(self, other_id):
        return db.session.query(Friendship).filter(
            Friendship.status == "accepted",
            or_(
                and_(Friendship.user1_id == self.id, Friendship.user2_id == other_id),
                and_(Friendship.user1_id == other_id, Friendship.user2_id == self.id),
            ),
        ).first() is not None

    def has_pending_request_with(self, other_id):
        return db.session.query(Friendship).filter(
            Friendship.status == "pending",
            or_(
                and_(Friendship.user1_id == self.id, Friendship.user2_id == other_id),
                and_(Friendship.user1_id == other_id, Friendship.user2_id == self.id),
            ),
        ).first()

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
    icon = db.Column(db.String(10), nullable=True)
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


class Channel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20), nullable=False, default="text")
    server_id = db.Column(db.Integer, db.ForeignKey("server.id"), nullable=True)  # None = universal channel
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
    recipient_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
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


class Friendship(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user1_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    user2_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")  # pending, accepted, declined
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user1 = db.relationship("User", foreign_keys=[user1_id], back_populates="friendships_sent")
    user2 = db.relationship("User", foreign_keys=[user2_id], back_populates="friendships_received")


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
        if len(username) < 2 or len(username) > 32:
            return render_template("register.html", error="Username must be 2–32 characters.")
        if len(password) < 4:
            return render_template("register.html", error="Password must be at least 4 characters.")
        if User.query.filter_by(username=username).first():
            return render_template("register.html", error="Username already taken. Please choose another.")

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

    memberships = ServerMember.query.filter_by(user_id=user.id).all()
    servers = [m.server for m in memberships]

    other_users = User.query.filter(User.id != user.id).all()

    # Get universal channel
    universal = Channel.query.filter_by(server_id=None, name=UNIVERSAL_CHANNEL_NAME).first()

    return render_template(
        "somcord.html",
        user=user,
        servers=[s.to_dict() for s in servers],
        users=[u.to_dict() for u in other_users],
        universal=universal.to_dict() if universal else None,
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

    membership = ServerMember(user_id=user.id, server_id=server.id, role="Owner")
    db.session.add(membership)
    db.session.commit()
    return jsonify(server.to_dict()), 201


@app.route("/api/servers/join", methods=["POST"])
@login_required
def api_join_server():
    data = request.get_json(silent=True) or {}
    server_id = data.get("server_id")
    if not server_id:
        return jsonify({"error": "Server ID required"}), 400

    server = db.session.get(Server, server_id)
    if not server:
        return jsonify({"error": "Server not found"}), 404

    user = current_user()
    existing = ServerMember.query.filter_by(user_id=user.id, server_id=server_id).first()
    if existing:
        return jsonify({"error": "Already a member"}), 400

    membership = ServerMember(user_id=user.id, server_id=server.id, role="Member")
    db.session.add(membership)
    db.session.commit()
    return jsonify(server.to_dict()), 200


@app.route("/api/servers/list")
@login_required
def api_list_servers():
    """List all public servers available to join."""
    servers = Server.query.all()
    result = []
    for s in servers:
        d = s.to_dict()
        d["member_count"] = ServerMember.query.filter_by(server_id=s.id).count()
        result.append(d)
    return jsonify(result)


@app.route("/api/servers/<int:server_id>/channels")
@login_required
def api_channels(server_id):
    server = db.session.get(Server, server_id)
    if not server:
        abort(404)
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
    # Universal channel (server_id=None) is open to all
    if channel.server_id is not None:
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
    if not me.is_friends_with(other_user_id):
        return jsonify({"error": "You must be friends to DM"}), 403
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


# ----- Friends API -----
@app.route("/api/friends")
@login_required
def api_friends():
    me = current_user()
    friendships = db.session.query(Friendship).filter(
        Friendship.status == "accepted",
        or_(Friendship.user1_id == me.id, Friendship.user2_id == me.id),
    ).all()

    friends = []
    for f in friendships:
        other_id = f.user2_id if f.user1_id == me.id else f.user1_id
        other = db.session.get(User, other_id)
        if other:
            d = other.to_dict()
            d["since"] = f.created_at.isoformat()
            friends.append(d)
    return jsonify(friends)


@app.route("/api/friends/requests")
@login_required
def api_friend_requests():
    me = current_user()
    requests = db.session.query(Friendship).filter(
        Friendship.user2_id == me.id,
        Friendship.status == "pending",
    ).all()

    result = []
    for r in requests:
        u = r.user1.to_dict()
        u["request_id"] = r.id
        result.append(u)
    return jsonify(result)


@app.route("/api/friends/sent")
@login_required
def api_sent_requests():
    me = current_user()
    requests = db.session.query(Friendship).filter(
        Friendship.user1_id == me.id,
        Friendship.status == "pending",
    ).all()
    return jsonify([{"id": r.id, "user": r.user2.to_dict()} for r in requests])


@app.route("/api/friends/add", methods=["POST"])
@login_required
def api_add_friend():
    data = request.get_json(silent=True) or {}
    target_username = (data.get("username") or "").strip()
    if not target_username:
        return jsonify({"error": "Username required"}), 400

    me = current_user()
    target = User.query.filter_by(username=target_username).first()
    if not target:
        return jsonify({"error": "User not found"}), 404
    if target.id == me.id:
        return jsonify({"error": "Cannot add yourself"}), 400
    if me.is_friends_with(target.id):
        return jsonify({"error": "Already friends"}), 400
    if me.has_pending_request_with(target.id):
        return jsonify({"error": "Request already pending"}), 400

    friendship = Friendship(user1_id=me.id, user2_id=target.id, status="pending")
    db.session.add(friendship)
    db.session.commit()
    return jsonify({"status": "sent", "target": target.to_dict()}), 201


@app.route("/api/friends/requests/<int:request_id>/accept", methods=["POST"])
@login_required
def api_accept_friend(request_id):
    me = current_user()
    friendship = db.session.get(Friendship, request_id)
    if not friendship or friendship.user2_id != me.id:
        return jsonify({"error": "Request not found"}), 404
    friendship.status = "accepted"
    db.session.commit()
    return jsonify({"status": "accepted"})


@app.route("/api/friends/requests/<int:request_id>/decline", methods=["POST"])
@login_required
def api_decline_friend(request_id):
    me = current_user()
    friendship = db.session.get(Friendship, request_id)
    if not friendship or friendship.user2_id != me.id:
        return jsonify({"error": "Request not found"}), 404
    friendship.status = "declined"
    db.session.commit()
    return jsonify({"status": "declined"})


# --------------------------------------------------------------------------- #
# SocketIO events
# --------------------------------------------------------------------------- #
@socketio.on("connect")
def on_connect():
    uid = session.get("user_id")
    if uid:
        user = db.session.get(User, uid)
        if user:
            sid_to_user[request.sid] = user.id
            user.status = "online"
            db.session.commit()
            join_room(str(user.id))
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
        # Create universal channel for everyone
        if not Channel.query.filter_by(server_id=None, name=UNIVERSAL_CHANNEL_NAME).first():
            universal = Channel(name=UNIVERSAL_CHANNEL_NAME, type="text", server_id=None)
            db.session.add(universal)
            db.session.commit()
    socketio.run(app, host="127.0.0.1", port=5001, debug=True)
