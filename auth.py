"""Authentication: signup, login, JWT sessions, current-user dependency."""
import os, re, time, secrets
import bcrypt, jwt
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, EmailStr, constr
from db import q1, execute

router = APIRouter(prefix="/api/auth", tags=["auth"])

JWT_SECRET = os.environ.get("OPDB_JWT_SECRET", "dev-insecure-change-me")
JWT_ALG = "HS256"
JWT_TTL = 60 * 60 * 24 * 90  # 90 days

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.]{3,24}$")


def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_pw(pw: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), h.encode())
    except Exception:
        return False


def make_token(user_id: str) -> str:
    now = int(time.time())
    return jwt.encode({"sub": str(user_id), "iat": now, "exp": now + JWT_TTL}, JWT_SECRET, algorithm=JWT_ALG)


def _decode(token: str):
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except Exception:
        return None


def current_user(authorization: str = Header(default="")):
    """Required auth. Returns the user row dict."""
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing bearer token")
    payload = _decode(authorization.split(" ", 1)[1].strip())
    if not payload:
        raise HTTPException(401, "Invalid or expired token")
    row = q1("SELECT id, email, username, display_name, bio, avatar_key, zip, home_zone, "
             "lat, lng, email_verified, notify_email, notify_push FROM users WHERE id=%s", (payload["sub"],))
    if not row:
        raise HTTPException(401, "User not found")
    execute("UPDATE users SET last_active=now() WHERE id=%s", (row["id"],))
    return row


def optional_user(authorization: str = Header(default="")):
    """Optional auth. Returns user row or None (never raises)."""
    if not authorization.lower().startswith("bearer "):
        return None
    payload = _decode(authorization.split(" ", 1)[1].strip())
    if not payload:
        return None
    return q1("SELECT id, email, username, display_name, avatar_key, zip, home_zone, lat, lng "
              "FROM users WHERE id=%s", (payload["sub"],))


def public_user(row) -> dict:
    if not row:
        return None
    return {
        "id": str(row["id"]), "username": row["username"],
        "display_name": row.get("display_name") or row["username"],
        "avatar_key": row.get("avatar_key"), "bio": row.get("bio", ""),
        "home_zone": row.get("home_zone"),
    }


class SignupIn(BaseModel):
    email: EmailStr
    username: constr(min_length=3, max_length=24)
    password: constr(min_length=8, max_length=200)
    display_name: str = ""
    zip: str = ""


class LoginIn(BaseModel):
    email: str
    password: str


def _me_payload(row) -> dict:
    return {
        "id": str(row["id"]), "email": row["email"], "username": row["username"],
        "display_name": row.get("display_name") or row["username"],
        "bio": row.get("bio", ""), "avatar_key": row.get("avatar_key"),
        "zip": row.get("zip"), "home_zone": row.get("home_zone"),
        "lat": row.get("lat"), "lng": row.get("lng"),
        "email_verified": row.get("email_verified", False),
        "notify_email": row.get("notify_email", True),
        "notify_push": row.get("notify_push", True),
    }


@router.post("/signup")
def signup(body: SignupIn):
    if not USERNAME_RE.match(body.username):
        raise HTTPException(400, "Username must be 3-24 chars: letters, numbers, _ or .")
    if q1("SELECT 1 FROM users WHERE lower(email)=lower(%s)", (body.email,)):
        raise HTTPException(409, "An account with that email already exists")
    if q1("SELECT 1 FROM users WHERE lower(username)=lower(%s)", (body.username,)):
        raise HTTPException(409, "That username is taken")
    verify_token = secrets.token_urlsafe(24)
    # Geocode the ZIP up-front so the account has coordinates + zone from the
    # start; without this every planting inherits NULL lat/lng and vanishes
    # from the geo-filtered community feed.
    lat = lng = home_zone = None
    if body.zip:
        try:
            import app
            ll = app.zip_to_latlng(body.zip)
            if ll:
                lat, lng = ll
            home_zone = app.zip_to_zone(body.zip)
        except Exception:
            pass
    row = execute(
        "INSERT INTO users (email, username, password_hash, display_name, zip, "
        "home_zone, lat, lng, verify_token) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id, email, username, display_name, bio, "
        "avatar_key, zip, home_zone, lat, lng, email_verified, notify_email, notify_push",
        (str(body.email), body.username, hash_pw(body.password),
         body.display_name or body.username, body.zip or None,
         home_zone, lat, lng, verify_token),
    )
    # Fire a verification email (best-effort, non-blocking failure).
    try:
        import notify
        notify.send_verification_email(row["email"], row["username"], verify_token)
    except Exception:
        pass
    return {"token": make_token(row["id"]), "user": _me_payload(row)}


@router.post("/login")
def login(body: LoginIn):
    row = q1("SELECT * FROM users WHERE lower(email)=lower(%s) OR lower(username)=lower(%s)",
             (body.email, body.email))
    if not row or not verify_pw(body.password, row["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    return {"token": make_token(row["id"]), "user": _me_payload(row)}


@router.get("/verify")
def verify(token: str):
    row = execute("UPDATE users SET email_verified=true, verify_token=NULL WHERE verify_token=%s "
                  "RETURNING username", (token,))
    if not row:
        raise HTTPException(400, "Invalid or already-used verification link")
    return {"ok": True, "username": row["username"]}
