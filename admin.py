"""ส่วนผู้ดูแลระบบ: จัดการห้อง, อนุมัติการจอง, จัดการผู้ใช้"""
import sqlite3

from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from auth import admin_required
from bookings import find_conflicts, now
from db import get_db, transaction

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.before_request
@admin_required
def guard():
    """ทุก route ใน /admin ต้องเป็น admin"""
    return None


# ---------------------------------------------------------------- rooms
def read_room_form():
    f = request.form
    try:
        capacity = int(f.get("capacity") or 0)
    except ValueError:
        capacity = 0
    return {
        "name": f.get("name", "").strip(),
        "location": f.get("location", "").strip(),
        "capacity": capacity,
        "equipment": f.get("equipment", "").strip(),
        "require_approval": 1 if f.get("require_approval") else 0,
        "is_active": 1 if f.get("is_active") else 0,
    }


def render_rooms(form=None, edit_room=None, errors=None):
    db = get_db()
    today = now().date().isoformat()
    rooms = db.execute(
        "SELECT r.*, (SELECT COUNT(*) FROM bookings b WHERE b.room_id = r.id"
        "  AND b.booking_date >= ? AND b.status IN ('pending','confirmed')) AS future_count"
        " FROM rooms r ORDER BY r.id",
        (today,),
    ).fetchall()
    pending = db.execute(
        "SELECT b.*, r.name AS room_name, r.capacity, u.full_name AS user_name, u.department"
        " FROM bookings b JOIN rooms r ON r.id = b.room_id JOIN users u ON u.id = b.user_id"
        " WHERE b.status = 'pending' AND b.booking_date >= ?"
        " ORDER BY b.booking_date, b.start_time",
        (today,),
    ).fetchall()
    if form is None:
        form = dict(edit_room) if edit_room else {
            "name": "", "location": "", "capacity": 10, "equipment": "",
            "require_approval": 0, "is_active": 1,
        }
    return render_template(
        "admin_rooms.html", rooms=rooms, pending=pending, form=form,
        edit_room=edit_room, errors=errors or [],
    ), (400 if errors else 200)


@bp.route("/rooms")
def rooms():
    edit_room = None
    edit_id = request.args.get("edit", type=int)
    if edit_id:
        edit_room = get_db().execute("SELECT * FROM rooms WHERE id = ?", (edit_id,)).fetchone()
    return render_rooms(edit_room=edit_room)


@bp.route("/rooms/save", methods=("POST",))
def save_room():
    db = get_db()
    room_id = request.form.get("id", type=int)
    edit_room = db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone() if room_id else None
    data = read_room_form()

    errors = []
    if not data["name"]:
        errors.append("กรุณากรอกชื่อห้อง")
    if data["capacity"] < 1 or data["capacity"] > 500:
        errors.append("ความจุต้องอยู่ระหว่าง 1–500 คน")
    if errors:
        return render_rooms(form=data, edit_room=edit_room, errors=errors)

    try:
        if edit_room:
            db.execute(
                "UPDATE rooms SET name=?, location=?, capacity=?, equipment=?, require_approval=?,"
                " is_active=? WHERE id=?",
                (data["name"], data["location"], data["capacity"], data["equipment"],
                 data["require_approval"], data["is_active"], edit_room["id"]),
            )
            flash(f"บันทึกข้อมูลห้อง “{data['name']}” แล้ว", "success")
        else:
            db.execute(
                "INSERT INTO rooms (name, location, capacity, equipment, require_approval, is_active)"
                " VALUES (?,?,?,?,?,?)",
                (data["name"], data["location"], data["capacity"], data["equipment"],
                 data["require_approval"], data["is_active"]),
            )
            flash(f"เพิ่มห้อง “{data['name']}” แล้ว", "success")
    except sqlite3.IntegrityError:
        return render_rooms(form=data, edit_room=edit_room, errors=["มีห้องชื่อนี้อยู่แล้ว"])
    return redirect(url_for("admin.rooms"))


@bp.route("/rooms/<int:room_id>/delete", methods=("POST",))
def delete_room(room_id):
    db = get_db()
    room = db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    if room is None:
        flash("ไม่พบห้องที่ต้องการลบ", "error")
        return redirect(url_for("admin.rooms"))
    future = db.execute(
        "SELECT COUNT(*) FROM bookings WHERE room_id = ? AND booking_date >= ?"
        " AND status IN ('pending','confirmed')",
        (room_id, now().date().isoformat()),
    ).fetchone()[0]
    if future:
        flash(f"ลบห้อง “{room['name']}” ไม่ได้ เพราะมีการจองในอนาคต {future} รายการ — ให้ปิดใช้งานแทน", "error")
        return redirect(url_for("admin.rooms"))
    history = db.execute("SELECT COUNT(*) FROM bookings WHERE room_id = ?", (room_id,)).fetchone()[0]
    if history:
        flash(f"ห้อง “{room['name']}” มีประวัติการจอง จึงลบไม่ได้ — ให้ปิดใช้งานแทนเพื่อเก็บประวัติ", "error")
        return redirect(url_for("admin.rooms"))
    db.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
    flash(f"ลบห้อง “{room['name']}” แล้ว", "success")
    return redirect(url_for("admin.rooms"))


# ---------------------------------------------------------------- approvals
@bp.route("/bookings/<int:booking_id>/approve", methods=("POST",))
def approve(booking_id):
    with transaction() as db:
        b = db.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
        if b is None or b["status"] != "pending":
            flash("ไม่พบคำขอที่รออนุมัติ", "error")
            return redirect(url_for("admin.rooms"))
        # เช็คชนเวลาอีกครั้งก่อนอนุมัติ
        conflicts = find_conflicts(db, b["room_id"], b["booking_date"], b["start_time"],
                                   b["end_time"], exclude_id=b["id"])
        if conflicts:
            c = conflicts[0]
            flash(f"อนุมัติไม่ได้: เวลาชนกับ “{c['title']}” ({c['start_time']}–{c['end_time']})", "error")
            return redirect(url_for("admin.rooms"))
        db.execute(
            "UPDATE bookings SET status='confirmed', approved_by=?, updated_at=datetime('now','localtime')"
            " WHERE id=?",
            (g.user["id"], b["id"]),
        )
    flash(f"อนุมัติ “{b['title']}” แล้ว", "success")
    return redirect(url_for("admin.rooms"))


@bp.route("/bookings/<int:booking_id>/reject", methods=("POST",))
def reject(booking_id):
    db = get_db()
    cur = db.execute(
        "UPDATE bookings SET status='rejected', approved_by=?, updated_at=datetime('now','localtime')"
        " WHERE id=? AND status='pending'",
        (g.user["id"], booking_id),
    )
    if cur.rowcount:
        flash("ไม่อนุมัติคำขอแล้ว", "success")
    else:
        flash("ไม่พบคำขอที่รออนุมัติ", "error")
    return redirect(url_for("admin.rooms"))


# ---------------------------------------------------------------- users
def render_users(form=None, errors=None):
    users = get_db().execute("SELECT * FROM users ORDER BY role, username").fetchall()
    form = form or {"username": "", "full_name": "", "department": "", "role": "user"}
    return render_template("admin_users.html", users=users, form=form, errors=errors or []), (
        400 if errors else 200
    )


@bp.route("/users")
def users():
    return render_users()


@bp.route("/users/add", methods=("POST",))
def add_user():
    f = request.form
    form = {
        "username": f.get("username", "").strip(),
        "full_name": f.get("full_name", "").strip(),
        "department": f.get("department", "").strip(),
        "role": f.get("role", "user"),
    }
    password = f.get("password", "")
    errors = []
    if not form["username"] or not form["username"].replace("_", "").replace(".", "").isalnum():
        errors.append("ชื่อผู้ใช้ต้องเป็นตัวอักษร/ตัวเลข (ใช้ _ หรือ . ได้)")
    if not form["full_name"]:
        errors.append("กรุณากรอกชื่อ-นามสกุล")
    if len(password) < 6:
        errors.append("รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร")
    if form["role"] not in ("user", "admin"):
        errors.append("สิทธิ์ไม่ถูกต้อง")
    if errors:
        return render_users(form, errors)
    try:
        get_db().execute(
            "INSERT INTO users (username, password_hash, full_name, department, role) VALUES (?,?,?,?,?)",
            (form["username"], generate_password_hash(password), form["full_name"],
             form["department"], form["role"]),
        )
    except sqlite3.IntegrityError:
        return render_users(form, ["มีชื่อผู้ใช้นี้อยู่แล้ว"])
    flash(f"เพิ่มผู้ใช้ “{form['username']}” แล้ว", "success")
    return redirect(url_for("admin.users"))


def _target_user(user_id):
    return get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


@bp.route("/users/<int:user_id>/reset-password", methods=("POST",))
def reset_password(user_id):
    user = _target_user(user_id)
    password = request.form.get("password", "")
    if user is None:
        flash("ไม่พบผู้ใช้", "error")
    elif len(password) < 6:
        flash("รหัสผ่านใหม่ต้องมีอย่างน้อย 6 ตัวอักษร", "error")
    else:
        get_db().execute("UPDATE users SET password_hash = ? WHERE id = ?",
                         (generate_password_hash(password), user_id))
        flash(f"รีเซ็ตรหัสผ่านของ “{user['username']}” แล้ว", "success")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/role", methods=("POST",))
def change_role(user_id):
    user = _target_user(user_id)
    role = request.form.get("role")
    if user is None or role not in ("user", "admin"):
        flash("ข้อมูลไม่ถูกต้อง", "error")
    elif user["id"] == g.user["id"]:
        flash("ไม่สามารถเปลี่ยนสิทธิ์ของตัวเองได้", "error")
    else:
        get_db().execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        flash(f"เปลี่ยนสิทธิ์ของ “{user['username']}” เป็น {'ผู้ดูแลระบบ' if role == 'admin' else 'ผู้ใช้ทั่วไป'} แล้ว", "success")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/toggle-active", methods=("POST",))
def toggle_active(user_id):
    user = _target_user(user_id)
    if user is None:
        flash("ไม่พบผู้ใช้", "error")
    elif user["id"] == g.user["id"]:
        flash("ไม่สามารถปิดใช้งานบัญชีของตัวเองได้", "error")
    else:
        new_state = 0 if user["is_active"] else 1
        get_db().execute("UPDATE users SET is_active = ? WHERE id = ?", (new_state, user_id))
        flash(f"{'เปิด' if new_state else 'ปิด'}ใช้งานบัญชี “{user['username']}” แล้ว", "success")
    return redirect(url_for("admin.users"))
