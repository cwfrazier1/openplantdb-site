"""Social platform endpoints: plantings, comments, likes, follows, feed, requests."""
import re, math
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Request
from pydantic import BaseModel, constr
from typing import Optional
from db import q1, qall, execute
from auth import current_user, optional_user, public_user
import storage
import notify

router = APIRouter(tags=["social"])
MAX_PHOTO = 8 * 1024 * 1024  # 8 MB


# ---------- helpers ----------
def media_url(key):
    return f"/media/{key}" if key else None


def _photos_for(ids):
    if not ids:
        return {}
    rows = qall("SELECT planting_id, s3_key FROM planting_photos WHERE planting_id = ANY(%s) "
                "ORDER BY position, created_at", (list(ids),))
    out = {}
    for r in rows:
        out.setdefault(str(r["planting_id"]), []).append(media_url(r["s3_key"]))
    return out


def serialize_plantings(rows, me):
    ids = [r["id"] for r in rows]
    photos = _photos_for(ids)
    liked = set()
    if me and ids:
        lk = qall("SELECT planting_id FROM likes WHERE user_id=%s AND planting_id = ANY(%s)",
                  (me["id"], list(ids)))
        liked = {str(x["planting_id"]) for x in lk}
    out = []
    for r in rows:
        pid = str(r["id"])
        out.append({
            "id": pid, "plant_slug": r["plant_slug"], "plant_name": r["plant_name"],
            "note": r["note"], "zone": r.get("zone"),
            "lat": r.get("lat"), "lng": r.get("lng"),
            "planted_on": r["planted_on"].isoformat() if r.get("planted_on") else None,
            "created_at": r["created_at"].isoformat(),
            "like_count": r["like_count"], "comment_count": r["comment_count"],
            "liked_by_me": pid in liked,
            "distance_mi": round(r["distance_mi"], 1) if r.get("distance_mi") is not None else None,
            "photos": photos.get(pid, []),
            "author": public_user({
                "id": r["user_id"], "username": r["author_username"],
                "display_name": r.get("author_display"), "avatar_key": r.get("author_avatar"),
                "bio": "", "home_zone": r.get("author_zone"),
            }),
        })
    return out


PLANTING_SELECT = """
  SELECT p.*, u.username AS author_username, u.display_name AS author_display,
         u.avatar_key AS author_avatar, u.home_zone AS author_zone
  FROM plantings p JOIN users u ON u.id = p.user_id
"""


# ---------- create "I planted this!" ----------
class PlantingIn(BaseModel):
    plant_slug: constr(min_length=1, max_length=200)
    plant_name: str = ""
    note: str = ""
    zone: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    planted_on: Optional[str] = None


@router.post("/api/plantings")
def create_planting(body: PlantingIn, me=Depends(current_user)):
    lat = body.lat if body.lat is not None else me.get("lat")
    lng = body.lng if body.lng is not None else me.get("lng")
    zone = body.zone or me.get("home_zone")
    pdate = None
    if body.planted_on:
        try:
            pdate = date.fromisoformat(body.planted_on[:10])
        except ValueError:
            pdate = None
    row = execute(
        "INSERT INTO plantings (user_id, plant_slug, plant_name, note, zone, lat, lng, planted_on) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (me["id"], body.plant_slug, body.plant_name, body.note.strip(), zone, lat, lng, pdate),
    )
    return {"id": str(row["id"])}


@router.post("/api/plantings/{pid}/photos")
async def add_photo(pid: str, file: UploadFile = File(...), me=Depends(current_user)):
    own = q1("SELECT user_id FROM plantings WHERE id=%s", (pid,))
    if not own:
        raise HTTPException(404, "Planting not found")
    if str(own["user_id"]) != str(me["id"]):
        raise HTTPException(403, "Not your planting")
    data = await file.read()
    if len(data) > MAX_PHOTO:
        raise HTTPException(413, "Image too large (max 8 MB)")
    ct = file.content_type or "image/jpeg"
    # Whitelist raster types only. `image/*` accepts image/svg+xml, which
    # executes JS when the stored object is served inline from /media (stored
    # XSS -> token theft). storage._EXT is the single source of truth.
    if ct not in storage._EXT:
        raise HTTPException(400, "Only JPEG, PNG, WebP, or HEIC images are allowed")
    key = storage.put(data, ct)
    pos = q1("SELECT COALESCE(MAX(position)+1,0) AS n FROM planting_photos WHERE planting_id=%s", (pid,))["n"]
    execute("INSERT INTO planting_photos (planting_id, s3_key, position) VALUES (%s,%s,%s)",
            (pid, key, pos))
    return {"url": media_url(key)}


@router.get("/api/plantings/{pid}")
def get_planting(pid: str, me=Depends(optional_user)):
    row = q1(PLANTING_SELECT + " WHERE p.id=%s", (pid,))
    if not row:
        raise HTTPException(404, "Not found")
    row["distance_mi"] = None
    return serialize_plantings([row], me)[0]


@router.delete("/api/plantings/{pid}")
def delete_planting(pid: str, me=Depends(current_user)):
    own = q1("SELECT user_id FROM plantings WHERE id=%s", (pid,))
    if not own:
        raise HTTPException(404, "Not found")
    if str(own["user_id"]) != str(me["id"]):
        raise HTTPException(403, "Not your planting")
    execute("DELETE FROM plantings WHERE id=%s", (pid,))
    return {"ok": True}


@router.get("/api/plants/{slug}/plantings")
def plant_plantings(slug: str, me=Depends(optional_user), limit: int = 30, before: str = None):
    params = [slug]
    where = "WHERE p.plant_slug=%s"
    if before:
        where += " AND p.created_at < %s"
        params.append(before)
    params.append(min(limit, 100))
    rows = qall(PLANTING_SELECT + f" {where} ORDER BY p.created_at DESC LIMIT %s", tuple(params))
    for r in rows:
        r["distance_mi"] = None
    return {"plantings": serialize_plantings(rows, me)}


# ---------- comments ----------
class CommentIn(BaseModel):
    body: constr(min_length=1, max_length=2000)


@router.post("/api/plantings/{pid}/comments")
def add_comment(pid: str, body: CommentIn, me=Depends(current_user)):
    p = q1("SELECT user_id, plant_name FROM plantings WHERE id=%s", (pid,))
    if not p:
        raise HTTPException(404, "Planting not found")
    c = execute("INSERT INTO comments (planting_id, user_id, body) VALUES (%s,%s,%s) RETURNING id, created_at",
                (pid, me["id"], body.body.strip()))
    execute("UPDATE plantings SET comment_count = comment_count + 1 WHERE id=%s", (pid,))
    notify.notify(p["user_id"], me["id"], "comment",
                  f"{me['username']} commented on your {p['plant_name'] or 'planting'}",
                  planting_id=pid, comment_id=c["id"],
                  email_subject="New comment on your planting")
    return {"id": str(c["id"]), "created_at": c["created_at"].isoformat()}


@router.get("/api/plantings/{pid}/comments")
def list_comments(pid: str, limit: int = 100):
    rows = qall(
        "SELECT c.id, c.body, c.created_at, u.username, u.display_name, u.avatar_key "
        "FROM comments c JOIN users u ON u.id=c.user_id WHERE c.planting_id=%s "
        "ORDER BY c.created_at LIMIT %s", (pid, min(limit, 200)))
    return {"comments": [{
        "id": str(r["id"]), "body": r["body"], "created_at": r["created_at"].isoformat(),
        "author": public_user({"id": None, "username": r["username"],
                               "display_name": r["display_name"], "avatar_key": r["avatar_key"],
                               "bio": "", "home_zone": None}),
    } for r in rows]}


# ---------- likes ----------
@router.post("/api/plantings/{pid}/like")
def like(pid: str, me=Depends(current_user)):
    p = q1("SELECT user_id, plant_name FROM plantings WHERE id=%s", (pid,))
    if not p:
        raise HTTPException(404, "Not found")
    ins = execute("INSERT INTO likes (user_id, planting_id) VALUES (%s,%s) "
                  "ON CONFLICT DO NOTHING RETURNING user_id", (me["id"], pid))
    if ins:
        execute("UPDATE plantings SET like_count = like_count + 1 WHERE id=%s", (pid,))
        notify.notify(p["user_id"], me["id"], "like",
                      f"{me['username']} liked your {p['plant_name'] or 'planting'}",
                      planting_id=pid)
    return {"ok": True}


@router.delete("/api/plantings/{pid}/like")
def unlike(pid: str, me=Depends(current_user)):
    d = execute("DELETE FROM likes WHERE user_id=%s AND planting_id=%s RETURNING user_id", (me["id"], pid))
    if d:
        execute("UPDATE plantings SET like_count = GREATEST(like_count - 1, 0) WHERE id=%s", (pid,))
    return {"ok": True}


# ---------- follows ----------
@router.post("/api/users/{username}/follow")
def follow(username: str, me=Depends(current_user)):
    u = q1("SELECT id, username FROM users WHERE lower(username)=lower(%s)", (username,))
    if not u:
        raise HTTPException(404, "User not found")
    if str(u["id"]) == str(me["id"]):
        raise HTTPException(400, "You can't follow yourself")
    ins = execute("INSERT INTO follows (follower_id, followee_id) VALUES (%s,%s) "
                  "ON CONFLICT DO NOTHING RETURNING follower_id", (me["id"], u["id"]))
    if ins:
        notify.notify(u["id"], me["id"], "follow", f"{me['username']} started following you")
    return {"ok": True}


@router.delete("/api/users/{username}/follow")
def unfollow(username: str, me=Depends(current_user)):
    u = q1("SELECT id FROM users WHERE lower(username)=lower(%s)", (username,))
    if u:
        execute("DELETE FROM follows WHERE follower_id=%s AND followee_id=%s", (me["id"], u["id"]))
    return {"ok": True}


# ---------- feeds ----------
def _haversine_select(lat, lng):
    # distance in miles as a SQL expression using bound params (%s repeated)
    return ("(3959 * acos(LEAST(1.0, cos(radians(%s))*cos(radians(p.lat))*"
            "cos(radians(p.lng)-radians(%s)) + sin(radians(%s))*sin(radians(p.lat)))))")


@router.get("/api/feed")
def geo_feed(lat: float = Query(...), lng: float = Query(...),
             radius: float = Query(100, ge=1, le=3000),
             limit: int = 30, before: str = None, me=Depends(optional_user)):
    lat_d = radius / 69.0
    lng_d = radius / (69.0 * max(math.cos(math.radians(lat)), 0.01))
    dist = _haversine_select(lat, lng)
    params = [lat, lng, lat,                       # haversine
              lat - lat_d, lat + lat_d, lng - lng_d, lng + lng_d]  # bbox
    where = ("WHERE p.lat IS NOT NULL AND p.lat BETWEEN %s AND %s AND p.lng BETWEEN %s AND %s")
    if before:
        where += " AND p.created_at < %s"
        params.append(before)
    params += [lat, lng, lat, radius, min(limit, 100)]  # haversine again for HAVING + radius + limit
    sql = (PLANTING_SELECT.replace("SELECT p.*,", f"SELECT p.*, {dist} AS distance_mi,")
           + f" {where} AND {dist} <= %s ORDER BY p.created_at DESC LIMIT %s")
    rows = qall(sql, tuple(params))
    return {"plantings": serialize_plantings(rows, me)}


@router.get("/api/feed/following")
def following_feed(limit: int = 30, before: str = None, me=Depends(current_user)):
    params = [me["id"], me["id"]]
    where = ("WHERE (p.user_id = %s OR p.user_id IN "
             "(SELECT followee_id FROM follows WHERE follower_id=%s))")
    if before:
        where += " AND p.created_at < %s"
        params.append(before)
    params.append(min(limit, 100))
    rows = qall(PLANTING_SELECT + f" {where} ORDER BY p.created_at DESC LIMIT %s", tuple(params))
    for r in rows:
        r["distance_mi"] = None
    return {"plantings": serialize_plantings(rows, me)}


# ---------- notifications ----------
@router.get("/api/notifications")
def get_notifications(limit: int = 40, me=Depends(current_user)):
    rows = qall(
        "SELECT n.id, n.type, n.body, n.planting_id, n.read, n.created_at, "
        "u.username AS actor_username, u.avatar_key AS actor_avatar "
        "FROM notifications n LEFT JOIN users u ON u.id=n.actor_id "
        "WHERE n.user_id=%s ORDER BY n.created_at DESC LIMIT %s", (me["id"], min(limit, 100)))
    unread = q1("SELECT count(*) AS c FROM notifications WHERE user_id=%s AND read=false", (me["id"],))["c"]
    return {"unread": unread, "notifications": [{
        "id": str(r["id"]), "type": r["type"], "body": r["body"],
        "planting_id": str(r["planting_id"]) if r["planting_id"] else None,
        "read": r["read"], "created_at": r["created_at"].isoformat(),
        "actor": {"username": r["actor_username"], "avatar_key": r["actor_avatar"]} if r["actor_username"] else None,
    } for r in rows]}


@router.post("/api/notifications/read")
def mark_read(me=Depends(current_user)):
    execute("UPDATE notifications SET read=true WHERE user_id=%s AND read=false", (me["id"],))
    return {"ok": True}


# ---------- device registration (push) ----------
class DeviceIn(BaseModel):
    platform: str
    apns_token: Optional[str] = None
    web_sub: Optional[dict] = None


@router.post("/api/devices")
def register_device(body: DeviceIn, me=Depends(current_user)):
    if body.apns_token:
        execute("INSERT INTO devices (user_id, platform, apns_token) VALUES (%s,'ios',%s) "
                "ON CONFLICT (apns_token) DO UPDATE SET user_id=EXCLUDED.user_id, last_seen=now()",
                (me["id"], body.apns_token))
    elif body.web_sub:
        import json as _j
        execute("INSERT INTO devices (user_id, platform, web_sub) VALUES (%s,'web',%s)",
                (me["id"], _j.dumps(body.web_sub)))
    return {"ok": True}


# ---------- profile ----------
class ProfileIn(BaseModel):
    display_name: Optional[str] = None
    bio: Optional[str] = None
    zip: Optional[str] = None
    home_zone: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    notify_email: Optional[bool] = None
    notify_push: Optional[bool] = None


@router.get("/api/me")
def get_me(me=Depends(current_user)):
    counts = q1("SELECT "
                "(SELECT count(*) FROM plantings WHERE user_id=%s) AS plantings,"
                "(SELECT count(*) FROM follows WHERE followee_id=%s) AS followers,"
                "(SELECT count(*) FROM follows WHERE follower_id=%s) AS following",
                (me["id"], me["id"], me["id"]))
    return {**{k: (str(v) if k == "id" else v) for k, v in me.items()}, "counts": counts}


@router.patch("/api/me")
def update_me(body: ProfileIn, me=Depends(current_user)):
    fields, params = [], []
    for k in ("display_name", "bio", "zip", "home_zone", "lat", "lng", "notify_email", "notify_push"):
        v = getattr(body, k)
        if v is not None:
            fields.append(f"{k}=%s")
            params.append(v)
    # If the ZIP changed but the client didn't send coordinates, geocode it so
    # the account keeps a usable lat/lng/zone (community feed needs coordinates).
    if body.zip is not None and body.lat is None and body.lng is None:
        try:
            import app
            ll = app.zip_to_latlng(body.zip)
            if ll:
                fields += ["lat=%s", "lng=%s"]
                params += [ll[0], ll[1]]
            if body.home_zone is None:
                z = app.zip_to_zone(body.zip)
                if z:
                    fields.append("home_zone=%s")
                    params.append(z)
        except Exception:
            pass
    if fields:
        params.append(me["id"])
        execute(f"UPDATE users SET {', '.join(fields)}, updated_at=now() WHERE id=%s", tuple(params))
    return {"ok": True}


@router.get("/api/users/{username}")
def user_profile(username: str, me=Depends(optional_user)):
    u = q1("SELECT id, username, display_name, bio, avatar_key, home_zone, created_at "
           "FROM users WHERE lower(username)=lower(%s)", (username,))
    if not u:
        raise HTTPException(404, "User not found")
    counts = q1("SELECT "
                "(SELECT count(*) FROM plantings WHERE user_id=%s) AS plantings,"
                "(SELECT count(*) FROM follows WHERE followee_id=%s) AS followers,"
                "(SELECT count(*) FROM follows WHERE follower_id=%s) AS following",
                (u["id"], u["id"], u["id"]))
    following = False
    if me:
        following = bool(q1("SELECT 1 FROM follows WHERE follower_id=%s AND followee_id=%s",
                            (me["id"], u["id"])))
    rows = qall(PLANTING_SELECT + " WHERE p.user_id=%s ORDER BY p.created_at DESC LIMIT 30", (u["id"],))
    for r in rows:
        r["distance_mi"] = None
    return {"user": {**public_user(u), "created_at": u["created_at"].isoformat()},
            "counts": counts, "following": following,
            "plantings": serialize_plantings(rows, me)}


# ---------- plant requests ----------
class RequestIn(BaseModel):
    query: constr(min_length=2, max_length=200)


def _normalize(s):
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


@router.post("/api/requests")
def request_plant(body: RequestIn, me=Depends(optional_user)):
    norm = _normalize(body.query)
    if not norm:
        raise HTTPException(400, "Enter a plant name")
    existing = q1("SELECT id FROM plant_requests WHERE normalized=%s AND status IN ('pending','processing')",
                  (norm,))
    if existing:
        execute("UPDATE plant_requests SET votes = votes + 1 WHERE id=%s", (existing["id"],))
        return {"ok": True, "status": "voted"}
    execute("INSERT INTO plant_requests (user_id, query_text, normalized) VALUES (%s,%s,%s)",
            (me["id"] if me else None, body.query.strip(), norm))
    return {"ok": True, "status": "created"}


@router.get("/api/requests")
def list_requests(status: str = "pending", limit: int = 100):
    rows = qall("SELECT id, query_text, votes, status, created_at, fulfilled_slug "
                "FROM plant_requests WHERE status=%s ORDER BY votes DESC, created_at LIMIT %s",
                (status, min(limit, 500)))
    return {"requests": [{
        "id": str(r["id"]), "query": r["query_text"], "votes": r["votes"],
        "status": r["status"], "created_at": r["created_at"].isoformat(),
        "fulfilled_slug": r["fulfilled_slug"],
    } for r in rows]}
