"""User accounts: registration, login, sessions.

Passwords are never stored: only a salted PBKDF2-SHA256 hash. A session is a random token kept in an
HttpOnly cookie; the database stores only the SHA-256 of that token.
"""
import hashlib
import hmac
import re
import secrets
import time

from .services import ApiError

PBKDF2_ROUNDS = 200_000
SESSION_DAYS = 7
SESSION_SECONDS = SESSION_DAYS * 24 * 3600
MIN_PASSWORD = 8
MAX_FAILED = 5            # failed logins per email ...
LOCK_SECONDS = 5 * 60     # ... within this window, then the email is locked for the rest of it
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_failed = {}              # email -> [timestamps of recent failed logins]


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ROUNDS)
    return digest.hex(), salt


def _token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _public(row):
    return {"id": row["id"], "name": row["name"], "email": row["email"], "role": row["role"]}


def create_session(con, user_id):
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    con.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
    con.execute("INSERT INTO sessions (token_hash,user_id,created_at,expires_at) VALUES (?,?,?,?)",
                (_token_hash(token), user_id, now, now + SESSION_SECONDS))
    return token


def register(con, body):
    name = str(body.get("name") or "").strip()
    email = str(body.get("email") or "").strip().lower()
    password = str(body.get("password") or "")
    if not 2 <= len(name) <= 80:
        raise ApiError("Enter your full name")
    if not EMAIL_RE.match(email) or len(email) > 254:
        raise ApiError("Enter a valid email address")
    if len(password) < MIN_PASSWORD:
        raise ApiError(f"Password must be at least {MIN_PASSWORD} characters")
    if len(password) > 200:
        raise ApiError("Password is too long")
    if con.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
        raise ApiError("An account with this email already exists", 409)
    first = con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    pw_hash, salt = hash_password(password)
    cur = con.execute("INSERT INTO users (name,email,role,pw_hash,salt,created_at) VALUES (?,?,?,?,?,?)",
                      (name, email, "Admin" if first else "Dispatcher", pw_hash, salt, int(time.time())))
    user = con.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
    return _public(user), create_session(con, user["id"])


def login(con, body):
    email = str(body.get("email") or "").strip().lower()
    password = str(body.get("password") or "")
    now = time.time()
    recent = [t for t in _failed.get(email, []) if now - t < LOCK_SECONDS]
    if len(recent) >= MAX_FAILED:
        raise ApiError("Too many failed attempts. Try again in a few minutes.", 429)
    user = con.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    # Hash even when the email is unknown so both cases take the same time and give the same message.
    attempt, _ = hash_password(password, user["salt"] if user else "00" * 16)
    if not user or not hmac.compare_digest(attempt, user["pw_hash"]):
        _failed[email] = recent + [now]
        raise ApiError("Incorrect email or password", 401)
    _failed.pop(email, None)
    return _public(user), create_session(con, user["id"])


def logout(con, token):
    con.execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token),))


def current_user(con, token):
    """Return the signed-in user for a session token, or None."""
    if not token:
        return None
    row = con.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?",
                      (_token_hash(token), int(time.time()))).fetchone()
    return _public(row) if row else None
