"""Notifications: DB records + APNs push + email (all best-effort)."""
import os, json, time, logging
from db import execute, qall, q1

log = logging.getLogger("opdb.notify")

SITE_URL = os.environ.get("OPDB_SITE_URL", "https://whatcaniplantnow.com")

# ---- APNs (token auth, team-scoped key) --------------------------------------
_apns_jwt = {"tok": None, "iat": 0}


def _apns_token():
    import jwt as _jwt
    key_id = os.environ.get("OPDB_APNS_KEY_ID")
    team_id = os.environ.get("OPDB_APNS_TEAM_ID")
    p8 = os.environ.get("OPDB_APNS_P8_PATH")
    if not (key_id and team_id and p8):
        return None
    now = int(time.time())
    if _apns_jwt["tok"] and now - _apns_jwt["iat"] < 3000:
        return _apns_jwt["tok"]
    with open(p8) as f:
        key = f.read()
    tok = _jwt.encode({"iss": team_id, "iat": now}, key, algorithm="ES256",
                      headers={"kid": key_id})
    _apns_jwt.update(tok=tok, iat=now)
    return tok


def send_push(user_id, title, body, data=None):
    tok = _apns_token()
    if not tok:
        return
    topic = os.environ.get("OPDB_APNS_TOPIC", "org.fairbrook.plantnow")
    host = "api.push.apple.com" if os.environ.get("OPDB_APNS_PRODUCTION", "1") == "1" \
        else "api.sandbox.push.apple.com"
    devices = qall("SELECT apns_token FROM devices WHERE user_id=%s AND platform='ios' "
                   "AND apns_token IS NOT NULL", (user_id,))
    if not devices:
        return
    payload = {"aps": {"alert": {"title": title, "body": body}, "sound": "default",
                       "badge": 1}, "data": data or {}}
    try:
        import httpx
        with httpx.Client(http2=True, timeout=8) as client:
            for d in devices:
                try:
                    r = client.post(
                        f"https://{host}/3/device/{d['apns_token']}",
                        headers={"authorization": f"bearer {tok}", "apns-topic": topic,
                                 "apns-push-type": "alert"},
                        content=json.dumps(payload),
                    )
                    if r.status_code == 410:  # unregistered
                        execute("DELETE FROM devices WHERE apns_token=%s", (d["apns_token"],))
                except Exception as e:
                    log.warning("apns send failed: %s", e)
    except Exception as e:
        log.warning("apns client failed: %s", e)


# ---- Email (AWS SES, best-effort) --------------------------------------------
def _ses():
    frm = os.environ.get("OPDB_SES_FROM")
    if not frm:
        return None, None
    import boto3
    return boto3.client("ses", region_name=os.environ.get("OPDB_SES_REGION", "us-east-1")), frm


def send_email(to, subject, html, text=None):
    client, frm = _ses()
    if not client:
        log.info("email suppressed (no SES configured): %s -> %s", subject, to)
        return
    try:
        client.send_email(
            Source=frm, Destination={"ToAddresses": [to]},
            Message={"Subject": {"Data": subject},
                     "Body": {"Html": {"Data": html},
                              "Text": {"Data": text or subject}}},
        )
    except Exception as e:
        log.warning("ses send failed: %s", e)


def send_verification_email(to, username, token):
    link = f"{SITE_URL}/verify?token={token}"
    html = (f"<p>Welcome to What Can I Plant Now, {username}!</p>"
            f"<p>Confirm your email: <a href='{link}'>{link}</a></p>")
    send_email(to, "Confirm your email", html, f"Confirm your email: {link}")


# ---- Combined create + deliver ----------------------------------------------
def notify(recipient_id, actor_id, ntype, body, planting_id=None, comment_id=None,
           payload=None, push_title=None, email_subject=None, email_html=None):
    if actor_id and str(actor_id) == str(recipient_id):
        return  # don't notify yourself
    execute(
        "INSERT INTO notifications (user_id, actor_id, type, planting_id, comment_id, body, payload) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (recipient_id, actor_id, ntype, planting_id, comment_id, body,
         json.dumps(payload) if payload else None),
    )
    prefs = q1("SELECT email, notify_email, notify_push FROM users WHERE id=%s", (recipient_id,))
    if not prefs:
        return
    if prefs["notify_push"]:
        try:
            send_push(recipient_id, push_title or "What Can I Plant Now", body,
                      {"type": ntype, "planting_id": str(planting_id) if planting_id else None})
        except Exception as e:
            log.warning("push failed: %s", e)
    if prefs["notify_email"] and email_subject:
        try:
            send_email(prefs["email"], email_subject, email_html or body, body)
        except Exception as e:
            log.warning("email failed: %s", e)
