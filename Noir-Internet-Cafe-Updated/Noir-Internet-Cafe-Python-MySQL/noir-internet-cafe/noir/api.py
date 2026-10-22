"""Authenticated JSON API. All authoritative state lives in MySQL."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from functools import wraps
from hashlib import sha256
from zoneinfo import ZoneInfo
import secrets

from flask import Blueprint, current_app, g, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from .db import execute, query, transaction
from .domain import Problem, booking_time, calculate_bill, email, hourly_rate, password, positive_id, session_duration, text, utcnow

api = Blueprint("api", __name__)


def serial(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc).isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: serial(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [serial(v) for v in value]
    return value


def result(value, status=200):
    return jsonify(serial(value)), status


def payload():
    value = request.get_json()
    if not isinstance(value, dict):
        raise Problem("Expected a JSON object.")
    return value


def public_user(user):
    return {key: user[key] for key in ("id", "name", "email", "role", "active", "created_at")}


def current_user():
    if "user" not in g:
        token = session.get("auth")
        g.user = query(
            "SELECT u.* FROM auth_sessions a JOIN users u ON u.id=a.user_id "
            "WHERE a.token_hash=%s AND a.expires_at>%s AND u.active=TRUE",
            (sha256(token.encode()).hexdigest(), utcnow()), one=True,
        ) if token else None
    return g.user


def require(role=None):
    def decorate(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                raise Problem("Please sign in to continue.", 401)
            if role and user["role"] != role:
                raise Problem("Administrator access is required.", 403)
            return func(*args, **kwargs)
        return wrapped
    return decorate


def admin():
    return current_user()["role"] == "administrator"


def audit(action, detail, actor_id=None):
    execute("INSERT INTO audit_log (actor_id,action,detail) VALUES (%s,%s,%s)",
            (actor_id if actor_id is not None else current_user()["id"], action, detail))


def rate_limit(scope, identity, limit, seconds):
    now = utcnow()
    bucket = int(now.replace(tzinfo=timezone.utc).timestamp()) // seconds
    key = sha256(f"{scope}:{identity}:{bucket}".encode()).hexdigest()
    with transaction():
        execute("INSERT INTO rate_limits (bucket_hash,attempts,expires_at) VALUES (%s,1,%s) "
                "ON DUPLICATE KEY UPDATE attempts=attempts+1", (key, now + timedelta(seconds=seconds)))
        row = query("SELECT attempts FROM rate_limits WHERE bucket_hash=%s FOR UPDATE", (key,), one=True)
    if row["attempts"] > limit:
        raise Problem("Too many attempts. Please try again later.", 429)


def establish_login(user):
    old_token = session.get("auth")
    if old_token:
        execute("DELETE FROM auth_sessions WHERE token_hash=%s", (sha256(old_token.encode()).hexdigest(),))
    session.clear()
    token = secrets.token_urlsafe(48)
    execute("INSERT INTO auth_sessions (token_hash,user_id,expires_at) VALUES (%s,%s,%s)",
            (sha256(token.encode()).hexdigest(), user["id"], utcnow() + timedelta(hours=12)))
    session.permanent = True
    session["auth"] = token
    session["csrf"] = secrets.token_urlsafe(32)


def customer(data):
    if not admin():
        return current_user()["id"], current_user()["name"]
    if data.get("user_id"):
        user = query("SELECT id,name FROM users WHERE id=%s AND active=TRUE", (positive_id(data["user_id"], "account"),), one=True)
        if not user:
            raise Problem("Choose an active customer account.")
        return user["id"], user["name"]
    return None, text(data.get("customer_name"), "customer name", 2, 80)


def station_lock(station_id, include_deleted=False):
    station = query("SELECT * FROM stations WHERE id=%s FOR UPDATE", (station_id,), one=True)
    if not station or (station["deleted_at"] and not include_deleted):
        raise Problem("Station not found.", 404)
    return station


def station_occupants(station_id):
    active = query("SELECT * FROM cafe_sessions WHERE active_station_id=%s FOR UPDATE", (station_id,), one=True)
    if active and active["planned_end_at"] and active["planned_end_at"] <= utcnow():
        finish_session(active, active["planned_end_at"], active["started_by"])
        active = None
    booking = query("SELECT * FROM bookings WHERE reserved_station_id=%s FOR UPDATE", (station_id,), one=True)
    return active, booking


def finish_session(live, ended, actor_id):
    """Caller holds the station/session lock; invoice creation is atomic."""
    minutes, amount = calculate_bill(live["started_at"], ended, live["hourly_rate"])
    execute("UPDATE cafe_sessions SET ended_at=%s WHERE id=%s", (ended, live["id"]))
    invoice_id = execute("INSERT INTO invoices (session_id,minutes,amount,created_at,created_by) VALUES (%s,%s,%s,%s,%s)",
                         (live["id"], minutes, amount, ended, actor_id))
    execute("INSERT INTO audit_log (actor_id,action,detail) VALUES (%s,'session.end',%s)",
            (actor_id, f"Ended session #{live['id']}; invoice #{invoice_id}"))
    return {"invoice_id": invoice_id, "amount": amount, "minutes": minutes}


def expire_sessions():
    # Dashboard polling settles due sessions at their deadline, even after downtime.
    due = query("SELECT station_id FROM cafe_sessions WHERE ended_at IS NULL "
                "AND planned_end_at<=%s ORDER BY station_id", (utcnow(),))
    for row in due:
        with transaction():
            station_lock(row["station_id"], include_deleted=True)
            station_occupants(row["station_id"])


@api.get("/health")
def health():
    query("SELECT 1 AS ready", one=True)
    return result({"status": "ok"})


@api.get("/auth/me")
def me():
    user = current_user()
    return result({"user": public_user(user) if user else None, "csrf_token": session["csrf"],
                   "allow_registration": current_app.config["ALLOW_REGISTRATION"],
                   "timezone": current_app.config["CAFE_TIMEZONE"], "server_time": utcnow()})


@api.post("/auth/register")
def register():
    if not current_app.config["ALLOW_REGISTRATION"]:
        raise Problem("Public registration is disabled. Ask the Administrator for an account.", 403)
    rate_limit("register", request.remote_addr, 10, 3600)
    data = payload()
    name, address, secret = text(data.get("name"), "name", 2, 80), email(data.get("email")), password(data.get("password"))
    with transaction():
        uid = execute("INSERT INTO users (name,email,password_hash,role) VALUES (%s,%s,%s,'member')",
                      (name, address, generate_password_hash(secret)))
        audit("account.register", f"Member account #{uid} registered", uid)
    return result({"message": "Account created. You can now sign in."}, 201)


@api.post("/auth/login")
def login():
    rate_limit("login-ip", request.remote_addr, 60, 900)
    data = payload()
    address = email(data.get("email"))
    rate_limit("login-email", address, 12, 900)
    secret = data.get("password", "")
    if not isinstance(secret, str) or len(secret) > 128:
        raise Problem("Invalid email or password.", 401)
    user = query("SELECT * FROM users WHERE email=%s", (address,), one=True)
    # Perform password work for unknown email addresses as well.
    if not user:
        generate_password_hash(secret or secrets.token_urlsafe(12))
        raise Problem("Invalid email or password.", 401)
    if not check_password_hash(user["password_hash"], secret) or not user["active"]:
        raise Problem("Invalid email or password.", 401)
    with transaction():
        establish_login(user)
        audit("account.login", "Signed in", user["id"])
    return result({"user": public_user(user), "csrf_token": session["csrf"]})


@api.post("/auth/logout")
@require()
def logout():
    with transaction():
        execute("DELETE FROM auth_sessions WHERE token_hash=%s", (sha256(session["auth"].encode()).hexdigest(),))
        audit("account.logout", "Signed out")
    session.clear()
    session["csrf"] = secrets.token_urlsafe(32)
    return result({"message": "Signed out.", "csrf_token": session["csrf"]})


@api.post("/auth/password")
@require()
def change_password():
    rate_limit("change-password", current_user()["id"], 12, 3600)
    data = payload()
    old = data.get("current_password", "")
    if not isinstance(old, str) or len(old) > 128 or not check_password_hash(current_user()["password_hash"], old):
        raise Problem("The current password is incorrect.")
    new = password(data.get("new_password"))
    with transaction():
        execute("UPDATE users SET password_hash=%s WHERE id=%s", (generate_password_hash(new), current_user()["id"]))
        execute("DELETE FROM auth_sessions WHERE user_id=%s", (current_user()["id"],))
        audit("account.password", "Changed password; all sessions signed out")
    session.clear()
    session["csrf"] = secrets.token_urlsafe(32)
    return result({"message": "Password updated. Sign in again.", "csrf_token": session["csrf"]})


@api.get("/accounts")
@require("administrator")
def accounts():
    return result({"accounts": query("SELECT id,name,email,role,active,created_at FROM users ORDER BY name,id")})


@api.post("/accounts")
@require("administrator")
def create_account():
    data = payload()
    role = data.get("role", "member")
    if role not in ("administrator", "member"):
        raise Problem("Choose Administrator or Member.")
    name, address, secret = text(data.get("name"), "name", 2, 80), email(data.get("email")), password(data.get("password"))
    with transaction():
        uid = execute("INSERT INTO users (name,email,password_hash,role) VALUES (%s,%s,%s,%s)",
                      (name, address, generate_password_hash(secret), role))
        audit("account.create", f"Created {role} account #{uid}")
    return result({"id": uid}, 201)


@api.patch("/accounts/<int:uid>")
@require("administrator")
def edit_account(uid):
    data = payload()
    role = data.get("role")
    active = data.get("active")
    if role not in ("administrator", "member") or not isinstance(active, bool):
        raise Problem("Choose a valid role and account status.")
    name, address = text(data.get("name"), "name", 2, 80), email(data.get("email"))
    with transaction():
        administrators = query("SELECT id FROM users WHERE role='administrator' AND active=TRUE ORDER BY id FOR UPDATE")
        target = query("SELECT * FROM users WHERE id=%s FOR UPDATE", (uid,), one=True)
        if not target:
            raise Problem("Account not found.", 404)
        if uid == current_user()["id"] and (not active or role != "administrator"):
            raise Problem("You cannot disable or demote your own Administrator account.")
        if target["role"] == "administrator" and target["active"] and (not active or role != "administrator") and len(administrators) <= 1:
            raise Problem("Keep at least one active Administrator.")
        execute("UPDATE users SET name=%s,email=%s,role=%s,active=%s WHERE id=%s", (name, address, role, active, uid))
        if not active or role != target["role"]:
            execute("DELETE FROM auth_sessions WHERE user_id=%s", (uid,))
        audit("account.update", f"Updated account #{uid}: {role}, {'active' if active else 'disabled'}")
    return result({"message": "Account updated."})


@api.get("/dashboard")
@require()
def dashboard():
    expire_sessions()
    is_admin, uid = admin(), current_user()["id"]
    stations = query("SELECT * FROM stations WHERE deleted_at IS NULL ORDER BY name,id")
    sessions = query("SELECT s.*,p.name AS station_name FROM cafe_sessions s JOIN stations p ON p.id=s.station_id WHERE s.ended_at IS NULL ORDER BY s.started_at")
    bookings = query("SELECT b.*,p.name AS station_name FROM bookings b JOIN stations p ON p.id=b.station_id WHERE b.status='reserved' ORDER BY b.scheduled_at")
    for station in stations:
        live = next((s for s in sessions if s["station_id"] == station["id"]), None)
        held = next((b for b in bookings if b["station_id"] == station["id"]), None)
        station["status"] = "occupied" if live else "reserved" if held else "maintenance" if station["maintenance"] else "available"
        station["session"] = live if live and (is_admin or live["user_id"] == uid) else None
        station["booking"] = held if held and is_admin else None
    local = datetime.now(ZoneInfo(current_app.config["CAFE_TIMEZONE"]))
    start = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).replace(tzinfo=None)
    end = (local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).astimezone(timezone.utc).replace(tzinfo=None)
    if is_admin:
        finances = query("SELECT COALESCE(SUM(amount),0) AS revenue,COUNT(*) AS payments FROM payments WHERE paid_at>=%s AND paid_at<%s", (start, end), one=True)
        outstanding = query("SELECT COALESCE(SUM(i.amount),0) AS amount FROM invoices i LEFT JOIN payments p ON p.invoice_id=i.id WHERE p.id IS NULL", one=True)
    else:
        finances = query("SELECT COALESCE(SUM(p.amount),0) AS revenue,COUNT(*) AS payments FROM payments p JOIN invoices i ON i.id=p.invoice_id JOIN cafe_sessions s ON s.id=i.session_id WHERE s.user_id=%s AND p.paid_at>=%s AND p.paid_at<%s", (uid, start, end), one=True)
        outstanding = query("SELECT COALESCE(SUM(i.amount),0) AS amount FROM invoices i JOIN cafe_sessions s ON s.id=i.session_id LEFT JOIN payments p ON p.invoice_id=i.id WHERE p.id IS NULL AND s.user_id=%s", (uid,), one=True)
    return result({"stations": stations, "sessions": [s for s in sessions if is_admin or s["user_id"] == uid],
                   "bookings": bookings if is_admin else [],
                   "finances": {**finances, "outstanding": outstanding["amount"]}, "server_time": utcnow()})


@api.post("/stations")
@require("administrator")
def create_station():
    data = payload()
    name, rate = text(data.get("name"), "station name", 1, 40), hourly_rate(data.get("hourly_rate"))
    with transaction():
        sid = execute("INSERT INTO stations (name,hourly_rate) VALUES (%s,%s)", (name, rate))
        audit("station.create", f"Added station #{sid} ({name})")
    return result({"id": sid}, 201)


@api.patch("/stations/<int:sid>")
@require("administrator")
def edit_station(sid):
    data = payload()
    name, rate = text(data.get("name"), "station name", 1, 40), hourly_rate(data.get("hourly_rate"))
    maintenance = data.get("maintenance")
    if not isinstance(maintenance, bool):
        raise Problem("Choose a valid station status.")
    with transaction():
        station_lock(sid)
        live, booking = station_occupants(sid)
        if maintenance and (live or booking):
            raise Problem("End the session or cancel the reservation before maintenance.", 409)
        execute("UPDATE stations SET name=%s,hourly_rate=%s,maintenance=%s WHERE id=%s", (name, rate, maintenance, sid))
        audit("station.update", f"Updated station #{sid} ({name})")
    return result({"message": "Station updated. Active sessions keep their original rate."})


@api.delete("/stations/<int:sid>")
@require("administrator")
def delete_station(sid):
    with transaction():
        station = station_lock(sid, include_deleted=True)
        if station["deleted_at"]:
            return result({"message": "Station already removed."})
        live, booking = station_occupants(sid)
        if live or booking:
            raise Problem("End the active session or cancel the booking before deleting this station.", 409)
        execute("UPDATE stations SET deleted_at=%s WHERE id=%s", (utcnow(), sid))
        audit("station.delete", f"Removed station #{sid} ({station['name']}); history preserved")
    return result({"message": "Station removed. Previous invoices and payments are preserved."})


@api.post("/bookings")
@require("administrator")
def create_booking():
    data = payload()
    sid, scheduled = positive_id(data.get("station_id"), "station"), booking_time(data.get("scheduled_at"))
    uid, name = customer(data)
    with transaction():
        station = station_lock(sid)
        live, booking = station_occupants(sid)
        if station["maintenance"] or live or booking:
            raise Problem("This station is no longer available. Choose another station.", 409)
        bid = execute("INSERT INTO bookings (station_id,user_id,customer_name,scheduled_at,created_by) VALUES (%s,%s,%s,%s,%s)",
                      (sid, uid, name, scheduled, current_user()["id"]))
        audit("booking.create", f"Reserved station #{sid}; booking #{bid}")
    return result({"id": bid}, 201)


@api.post("/bookings/<int:bid>/cancel")
@require("administrator")
def cancel_booking(bid):
    original = query("SELECT * FROM bookings WHERE id=%s", (bid,), one=True)
    if not original:
        raise Problem("Booking not found.", 404)
    with transaction():
        station_lock(original["station_id"])
        booking = query("SELECT * FROM bookings WHERE id=%s FOR UPDATE", (bid,), one=True)
        if booking["status"] == "checked_in":
            raise Problem("This booking has already checked in.", 409)
        if booking["status"] == "reserved":
            execute("UPDATE bookings SET status='cancelled' WHERE id=%s", (bid,))
            audit("booking.cancel", f"Cancelled booking #{bid}")
    return result({"message": "Booking cancelled."})


@api.post("/sessions")
@require("administrator")
def start_session():
    data = payload()
    sid = positive_id(data.get("station_id"), "station")
    bid = positive_id(data["booking_id"], "booking") if data.get("booking_id") else None
    uid, name = (None, None) if bid else customer(data)
    minutes = session_duration(data.get("duration_minutes", 60))
    with transaction():
        station = station_lock(sid)
        live, booking = station_occupants(sid)
        if live or station["maintenance"]:
            raise Problem("This station cannot start another session.", 409)
        if booking and bid != booking["id"]:
            raise Problem("Check in the existing booking before starting this station.", 409)
        if bid:
            if not booking or booking["id"] != bid:
                raise Problem("This reservation is no longer available.", 409)
            uid, name = booking["user_id"], booking["customer_name"]
            execute("UPDATE bookings SET status='checked_in' WHERE id=%s", (bid,))
        started = utcnow()
        session_id = execute("INSERT INTO cafe_sessions (station_id,user_id,customer_name,booking_id,hourly_rate,started_at,planned_end_at,started_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                             (sid, uid, name, bid, station["hourly_rate"], started, started + timedelta(minutes=minutes), current_user()["id"]))
        audit("session.start", f"Started session #{session_id} on station #{sid}")
    return result({"id": session_id}, 201)


@api.post("/sessions/<int:session_id>/end")
@require("administrator")
def end_session(session_id):
    original = query("SELECT station_id FROM cafe_sessions WHERE id=%s", (session_id,), one=True)
    if not original:
        raise Problem("Session not found.", 404)
    with transaction():
        station_lock(original["station_id"], include_deleted=True)
        live = query("SELECT * FROM cafe_sessions WHERE id=%s FOR UPDATE", (session_id,), one=True)
        if live["ended_at"]:
            invoice = query("SELECT id FROM invoices WHERE session_id=%s", (session_id,), one=True)
            return result({"invoice_id": invoice["id"], "message": "Session already completed."})
        ended = min(utcnow(), live["planned_end_at"]) if live["planned_end_at"] else utcnow()
        invoice = finish_session(live, ended, current_user()["id"])
    return result(invoice)


@api.patch("/sessions/<int:session_id>/time")
@require("administrator")
def set_session_time(session_id):
    minutes = session_duration(payload().get("remaining_minutes"))
    original = query("SELECT station_id FROM cafe_sessions WHERE id=%s", (session_id,), one=True)
    if not original:
        raise Problem("Session not found.", 404)
    with transaction():
        station_lock(original["station_id"])
        live, _ = station_occupants(original["station_id"])
        if not live or live["id"] != session_id:
            raise Problem("This session has ended. Start a new session instead.", 409)
        deadline = utcnow() + timedelta(minutes=minutes)
        execute("UPDATE cafe_sessions SET planned_end_at=%s WHERE id=%s", (deadline, session_id))
        audit("session.time", f"Set remaining time for session #{session_id} to {minutes} minutes")
    return result({"message": "Remaining time updated.", "planned_end_at": deadline})


INVOICE_SELECT = ("SELECT i.*,s.customer_name,s.user_id,s.hourly_rate,s.started_at,s.ended_at,"
                  "t.name AS station_name,p.id AS payment_id,p.method,p.reference,p.paid_at "
                  "FROM invoices i JOIN cafe_sessions s ON s.id=i.session_id "
                  "JOIN stations t ON t.id=s.station_id LEFT JOIN payments p ON p.invoice_id=i.id ")


@api.get("/invoices")
@require()
def invoices():
    try:
        page = max(1, min(1000000, int(request.args.get("page", "1"))))
    except ValueError:
        raise Problem("Invalid page number.")
    status = request.args.get("status", "all")
    if status not in ("all", "unpaid", "paid"):
        raise Problem("Invalid invoice filter.")
    conditions, args = [], []
    if not admin():
        conditions.append("s.user_id=%s")
        args.append(current_user()["id"])
    if status != "all":
        conditions.append("p.id IS NULL" if status == "unpaid" else "p.id IS NOT NULL")
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    rows = query(INVOICE_SELECT + where + " ORDER BY i.id DESC LIMIT 51 OFFSET %s", (*args, (page - 1) * 50))
    return result({"invoices": rows[:50], "has_more": len(rows) > 50, "page": page})


@api.get("/invoices/<int:iid>")
@require()
def invoice_detail(iid):
    invoice = query(INVOICE_SELECT + "WHERE i.id=%s", (iid,), one=True)
    if not invoice or (not admin() and invoice["user_id"] != current_user()["id"]):
        raise Problem("Invoice not found.", 404)
    return result({"invoice": invoice})


@api.post("/invoices/<int:iid>/pay")
@require("administrator")
def pay(iid):
    data = payload()
    method = data.get("method")
    if method not in ("cash", "ewallet", "bank"):
        raise Problem("Choose Cash, E-wallet, or Bank transfer.")
    reference = text(data.get("reference", ""), "reference", 0 if method == "cash" else 1, 100)
    with transaction():
        invoice = query("SELECT * FROM invoices WHERE id=%s FOR UPDATE", (iid,), one=True)
        if not invoice:
            raise Problem("Invoice not found.", 404)
        existing = query("SELECT id FROM payments WHERE invoice_id=%s", (iid,), one=True)
        if existing:
            return result({"id": existing["id"], "message": "Payment already recorded."})
        pid = execute("INSERT INTO payments (invoice_id,amount,method,reference,paid_at,received_by) VALUES (%s,%s,%s,%s,%s,%s)",
                      (iid, invoice["amount"], method, reference or None, utcnow(), current_user()["id"]))
        audit("payment.record", f"Recorded {method} payment #{pid} for invoice #{iid}")
    return result({"id": pid, "message": "Payment recorded."}, 201)


@api.get("/activity")
@require("administrator")
def activity():
    return result({"activity": query("SELECT a.*,u.name AS actor_name FROM audit_log a LEFT JOIN users u ON u.id=a.actor_id ORDER BY a.id DESC LIMIT 100")})
