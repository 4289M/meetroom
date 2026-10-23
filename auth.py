"""เข้าสู่ระบบ / ออกจากระบบ / ตรวจสิทธิ์ / CSRF"""
import functools
import hmac
import secrets

from flask import (
    Blueprint, abort, flash, g, redirect, render_template, request, session, url_for,
)
from werkzeug.security import check_password_hash

from db import get_db

bp = Blueprint("auth", __name__)

# endpoint ที่เข้าได้โดยไม่ต้อง login
PUBLIC_ENDPOINTS = {"auth.login", "static"}


def _next_path():
    return request.full_path.rstrip("?")


def login_required(view):
    @functools.wraps(view)
    def wrapped(**kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=_next_path()))
        return view(**kwargs)
    return wrapped


def admin_required(view):
    @functools.wraps(view)
    def wrapped(**kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=_next_path()))
        if g.user["role"] != "admin":
            abort(403)
        return view(**kwargs)
    return wrapped


# ---------- CSRF (เก็บ token ใน session) ----------
def csrf_token():
    token = session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf"] = token
    return token


def check_csrf():
    if request.method != "POST":
        return
    sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token", "")
    token = session.get("_csrf", "")
    if not token or not hmac.compare_digest(sent, token):
        abort(400, description="CSRF token ไม่ถูกต้อง กรุณาโหลดหน้าใหม่แล้วลองอีกครั้ง")


def load_user():
    user_id = session.get("user_id")
    g.user = None
    if user_id is not None:
        user = get_db().execute(
            "SELECT * FROM users WHERE id = ? AND is_active = 1", (user_id,)
        ).fetchone()
        if user is None:
            session.clear()
        g.user = user


def init_app(app):
    @app.before_request
    def before():
        load_user()
        check_csrf()
        # ทุกหน้าต้อง login ยกเว้นหน้า login/static
        if g.user is None and request.endpoint not in PUBLIC_ENDPOINTS:
            if request.path.startswith("/api/"):
                return {"error": "กรุณาเข้าสู่ระบบ"}, 401
            return redirect(url_for("auth.login", next=_next_path()))

    @app.context_processor
    def inject():
        pending_count = 0
        if g.get("user") is not None and g.user["role"] == "admin":
            pending_count = get_db().execute(
                "SELECT COUNT(*) FROM bookings WHERE status = 'pending' AND booking_date >= date('now','localtime')"
            ).fetchone()[0]
        return {"csrf_token": csrf_token, "admin_pending_count": pending_count}

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    def error_page(e):
        messages = {
            400: "คำขอไม่ถูกต้อง",
            403: "คุณไม่มีสิทธิ์เข้าถึงหน้านี้",
            404: "ไม่พบหน้าที่ต้องการ",
        }
        detail = e.description if e.code == 400 else ""
        return render_template(
            "error.html", code=e.code, message=messages.get(e.code, "เกิดข้อผิดพลาด"), detail=detail
        ), e.code


def safe_next(target, default="bookings.index"):
    # ป้องกัน open redirect: อนุญาตเฉพาะ path ภายในเว็บ
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return url_for(default)


@bp.route("/login", methods=("GET", "POST"))
def login():
    if g.user is not None:
        return redirect(url_for("bookings.index"))

    error = None
    username = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

        if not username or not password:
            error = "กรุณากรอกชื่อผู้ใช้และรหัสผ่าน"
        elif user is None or not check_password_hash(user["password_hash"], password):
            error = "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"
        elif not user["is_active"]:
            error = "บัญชีนี้ถูกปิดใช้งาน กรุณาติดต่อผู้ดูแลระบบ"

        if error is None:
            next_url = request.args.get("next")
            session.clear()
            session["user_id"] = user["id"]
            flash(f"ยินดีต้อนรับ {user['full_name']}", "success")
            return redirect(safe_next(next_url))

    return render_template("login.html", error=error, username=username)


@bp.route("/logout", methods=("POST",))
def logout():
    session.clear()
    flash("ออกจากระบบแล้ว", "success")
    return redirect(url_for("auth.login"))
