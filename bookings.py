"""Timeline, ฟอร์มจอง, การจองของฉัน และ API ตรวจห้องว่าง"""
from datetime import date, datetime, timedelta

from flask import (
    Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for,
)

from auth import safe_next
from db import get_db, new_group_id, transaction
from utils import (
    DAY_END, DAY_START, from_minutes, parse_date, parse_time, thai_date_short, to_minutes,
)

bp = Blueprint("bookings", __name__)

EQUIPMENT_OPTIONS = ["โปรเจคเตอร์", "ไมโครโฟน", "กล้อง VDO Conference", "อาหารว่าง"]
MAX_DURATION_MIN = 4 * 60
MAX_DAYS_AHEAD = 30
MAX_REPEAT = 12
ACTIVE_STATUSES = ("pending", "confirmed")


def now():
    """แยกออกมาเพื่อให้ test แทนค่าเวลาได้"""
    return datetime.now()


# ---------------------------------------------------------------- helpers
def get_room(room_id, active_only=False):
    sql = "SELECT * FROM rooms WHERE id = ?"
    if active_only:
        sql += " AND is_active = 1"
    return get_db().execute(sql, (room_id,)).fetchone()


def active_rooms():
    return get_db().execute(
        "SELECT * FROM rooms WHERE is_active = 1 ORDER BY id"
    ).fetchall()


def find_conflicts(db, room_id, booking_date, start, end, exclude_id=None):
    """ชนเมื่อ new_start < exist_end AND new_end > exist_start (เฉพาะ pending/confirmed)"""
    sql = (
        "SELECT b.*, u.full_name AS user_name FROM bookings b JOIN users u ON u.id = b.user_id"
        " WHERE b.room_id = ? AND b.booking_date = ? AND b.status IN ('pending','confirmed')"
        " AND ? < b.end_time AND ? > b.start_time"
    )
    params = [room_id, booking_date, start, end]
    if exclude_id:
        sql += " AND b.id != ?"
        params.append(exclude_id)
    return db.execute(sql + " ORDER BY b.start_time", params).fetchall()


def suggest_rooms(db, booking_date, start, end, attendees, exclude_room_id, exclude_id=None):
    """ห้องอื่นที่ว่างช่วงเดียวกันและจุคนพอ"""
    rooms = db.execute(
        "SELECT * FROM rooms WHERE is_active = 1 AND id != ? AND capacity >= ? ORDER BY capacity, id",
        (exclude_room_id or 0, attendees or 1),
    ).fetchall()
    return [
        r for r in rooms
        if not find_conflicts(db, r["id"], booking_date, start, end, exclude_id)
    ]


def day_schedule(db, room_id, booking_date, exclude_id=None):
    """คืน (busy, free) ของห้องในวันนั้น สำหรับแผงข้าง"""
    params = [room_id, booking_date]
    sql = (
        "SELECT b.id, b.title, b.start_time, b.end_time, b.status, b.user_id, u.full_name AS user_name"
        " FROM bookings b JOIN users u ON u.id = b.user_id"
        " WHERE b.room_id = ? AND b.booking_date = ? AND b.status IN ('pending','confirmed')"
    )
    if exclude_id:
        sql += " AND b.id != ?"
        params.append(exclude_id)
    busy = [dict(r) for r in db.execute(sql + " ORDER BY b.start_time", params)]
    free, cursor = [], to_minutes(DAY_START)
    for b in busy:
        s, e = to_minutes(b["start_time"]), to_minutes(b["end_time"])
        if s > cursor:
            free.append({"start": from_minutes(cursor), "end": from_minutes(s)})
        cursor = max(cursor, e)
    if cursor < to_minutes(DAY_END):
        free.append({"start": from_minutes(cursor), "end": DAY_END})
    return busy, free


def occurrence_dates(first, repeat, count):
    if repeat == "daily":
        step = timedelta(days=1)
    elif repeat == "weekly":
        step = timedelta(weeks=1)
    else:
        return [first]
    return [first + step * i for i in range(count)]


def can_modify(booking):
    """แก้ไข/ยกเลิกได้เฉพาะการจองที่ยังไม่เริ่ม ของตัวเอง (หรือ admin)"""
    if booking is None or booking["status"] not in ACTIVE_STATUSES:
        return False
    if booking["user_id"] != g.user["id"] and g.user["role"] != "admin":
        return False
    start = datetime.fromisoformat(f"{booking['booking_date']} {booking['start_time']}")
    return start > now()


def read_form():
    f = request.form
    try:
        attendees = int(f.get("attendees") or 1)
    except ValueError:
        attendees = None
    try:
        repeat_count = int(f.get("repeat_count") or 1)
    except ValueError:
        repeat_count = None
    try:
        room_id = int(f.get("room_id") or 0)
    except ValueError:
        room_id = 0
    return {
        "title": f.get("title", "").strip(),
        "room_id": room_id,
        "booking_date": f.get("booking_date", "").strip(),
        "start_time": f.get("start_time", "").strip(),
        "end_time": f.get("end_time", "").strip(),
        "attendees": attendees,
        "repeat": f.get("repeat", "none"),
        "repeat_count": repeat_count,
        "equipment": [e for e in f.getlist("equipment") if e in EQUIPMENT_OPTIONS],
        "note": f.get("note", "").strip(),
    }


def validate(data, editing=False):
    """ตรวจกฎทางธุรกิจทั้งหมดฝั่ง server คืน (errors, room, dates)"""
    errors = []
    if not data["title"]:
        errors.append("กรุณากรอกหัวข้อการประชุม")
    elif len(data["title"]) > 200:
        errors.append("หัวข้อยาวเกิน 200 ตัวอักษร")

    room = get_room(data["room_id"], active_only=True) if data["room_id"] else None
    if room is None:
        errors.append("กรุณาเลือกห้องประชุมที่เปิดให้จอง")

    first = parse_date(data["booking_date"])
    start = parse_time(data["start_time"])
    end = parse_time(data["end_time"])
    if first is None:
        errors.append("รูปแบบวันที่ไม่ถูกต้อง")
    if start is None or end is None:
        errors.append("กรุณาระบุเวลาเริ่มและเวลาสิ้นสุด")
    else:
        data["start_time"], data["end_time"] = start, end
        s, e = to_minutes(start), to_minutes(end)
        if s % 30 or e % 30:
            errors.append("เวลาต้องเป็นช่วงละ 30 นาที (เช่น 09:00, 09:30)")
        if e <= s:
            errors.append("เวลาสิ้นสุดต้องมากกว่าเวลาเริ่ม")
        elif e - s > MAX_DURATION_MIN:
            errors.append("จองได้ครั้งละไม่เกิน 4 ชั่วโมง")
        if s < to_minutes(DAY_START) or e > to_minutes(DAY_END):
            errors.append(f"จองได้เฉพาะช่วง {DAY_START}–{DAY_END} น.")

    if data["attendees"] is None or data["attendees"] < 1:
        errors.append("จำนวนผู้เข้าร่วมต้องเป็นตัวเลขตั้งแต่ 1 คนขึ้นไป")
    elif room is not None and data["attendees"] > room["capacity"]:
        errors.append(
            f"จำนวนผู้เข้าร่วม ({data['attendees']} คน) เกินความจุของห้อง {room['name']} ({room['capacity']} คน)"
        )

    if editing:
        data["repeat"], data["repeat_count"] = "none", 1
    if data["repeat"] not in ("none", "daily", "weekly"):
        errors.append("รูปแบบการจองซ้ำไม่ถูกต้อง")
    if data["repeat"] != "none" and (
        data["repeat_count"] is None or not 2 <= data["repeat_count"] <= MAX_REPEAT
    ):
        errors.append(f"จำนวนครั้งของการจองซ้ำต้องอยู่ระหว่าง 2–{MAX_REPEAT} ครั้ง")

    dates = []
    if first is not None and start is not None and not errors:
        count = data["repeat_count"] if data["repeat"] != "none" else 1
        dates = occurrence_dates(first, data["repeat"], count)
        current = now()
        limit = current.date() + timedelta(days=MAX_DAYS_AHEAD)
        if datetime.fromisoformat(f"{first.isoformat()} {start}") <= current:
            errors.append("ไม่สามารถจองย้อนหลังได้")
        too_far = [d for d in dates if d > limit]
        if too_far:
            errors.append(
                f"จองล่วงหน้าได้ไม่เกิน {MAX_DAYS_AHEAD} วัน (ถึง {thai_date_short(limit)}) — วันที่เกิน: "
                + ", ".join(thai_date_short(d) for d in too_far)
            )
    return errors, room, dates


# ---------------------------------------------------------------- timeline
@bp.route("/")
def index():
    db = get_db()
    today = now().date()
    selected = parse_date(request.args.get("date", "")) or today
    sel = selected.isoformat()

    rooms = active_rooms()
    rows = db.execute(
        "SELECT b.*, u.full_name AS user_name, u.department FROM bookings b"
        " JOIN users u ON u.id = b.user_id JOIN rooms r ON r.id = b.room_id"
        " WHERE b.booking_date = ? AND b.status IN ('pending','confirmed') AND r.is_active = 1"
        " ORDER BY b.start_time",
        (sel,),
    ).fetchall()

    day_start, day_len = to_minutes(DAY_START), to_minutes(DAY_END) - to_minutes(DAY_START)
    by_room = {r["id"]: [] for r in rooms}
    for b in rows:
        s = max(to_minutes(b["start_time"]), day_start)
        e = min(to_minutes(b["end_time"]), day_start + day_len)
        by_room.setdefault(b["room_id"], []).append({
            "b": b,
            "left": round((s - day_start) / day_len * 100, 3),
            "width": round((e - s) / day_len * 100, 3),
            "mine": b["user_id"] == g.user["id"],
        })

    # การ์ดสรุป
    current = now()
    now_hm = current.strftime("%H:%M")
    busy_now = {
        r[0] for r in db.execute(
            "SELECT DISTINCT room_id FROM bookings WHERE booking_date = ?"
            " AND status IN ('pending','confirmed') AND start_time <= ? AND end_time > ?",
            (today.isoformat(), now_hm, now_hm),
        )
    }
    in_hours = DAY_START <= now_hm < DAY_END
    free_now = sum(1 for r in rooms if r["id"] not in busy_now) if in_hours else 0
    next_mine = db.execute(
        "SELECT b.*, r.name AS room_name FROM bookings b JOIN rooms r ON r.id = b.room_id"
        " WHERE b.user_id = ? AND b.status IN ('pending','confirmed')"
        " AND (b.booking_date > ? OR (b.booking_date = ? AND b.end_time > ?))"
        " ORDER BY b.booking_date, b.start_time LIMIT 1",
        (g.user["id"], today.isoformat(), today.isoformat(), now_hm),
    ).fetchone()
    if g.user["role"] == "admin":
        pending = db.execute(
            "SELECT COUNT(*) FROM bookings WHERE status = 'pending' AND booking_date >= ?",
            (today.isoformat(),),
        ).fetchone()[0]
    else:
        pending = db.execute(
            "SELECT COUNT(*) FROM bookings WHERE status = 'pending' AND user_id = ? AND booking_date >= ?",
            (g.user["id"], today.isoformat()),
        ).fetchone()[0]

    now_left = None
    if selected == today and day_start <= to_minutes(now_hm) <= day_start + day_len:
        now_left = round((current.hour * 60 + current.minute - day_start) / day_len * 100, 3)

    return render_template(
        "index.html",
        selected=selected,
        is_today=selected == today,
        prev_date=(selected - timedelta(days=1)).isoformat(),
        next_date=(selected + timedelta(days=1)).isoformat(),
        today=today.isoformat(),
        rooms=rooms,
        by_room=by_room,
        hours=list(range(to_minutes(DAY_START) // 60, to_minutes(DAY_END) // 60)),
        total_bookings=len(rows),
        free_now=free_now,
        in_hours=in_hours,
        next_mine=next_mine,
        pending=pending,
        now_left=now_left,
    )


# ---------------------------------------------------------------- form
def render_form(data, booking=None, errors=None, conflicts=None):
    db = get_db()
    rooms = active_rooms()
    room = get_room(data.get("room_id")) if data.get("room_id") else None
    busy, free = [], []
    d = parse_date(data.get("booking_date", ""))
    if room is not None and d is not None:
        busy, free = day_schedule(db, room["id"], d.isoformat(), booking["id"] if booking else None)
    return render_template(
        "booking_form.html",
        data=data,
        booking=booking,
        rooms=rooms,
        room=room,
        busy=busy,
        free=free,
        errors=errors or [],
        conflicts=conflicts or [],
        equipment_options=EQUIPMENT_OPTIONS,
        min_date=now().date().isoformat(),
        max_date=(now().date() + timedelta(days=MAX_DAYS_AHEAD)).isoformat(),
        max_repeat=MAX_REPEAT,
    ), (400 if errors else 200)


def status_for(room):
    if room["require_approval"] and g.user["role"] != "admin":
        return "pending", None
    return "confirmed", (g.user["id"] if room["require_approval"] else None)


@bp.route("/bookings/new", methods=("GET", "POST"))
def new():
    if request.method == "GET":
        a = request.args
        start = parse_time(a.get("start", "")) or "09:00"
        end = parse_time(a.get("end", "")) or from_minutes(min(to_minutes(start) + 60, to_minutes(DAY_END)))
        data = {
            "title": "", "room_id": a.get("room_id", type=int) or (active_rooms() or [{"id": 0}])[0]["id"],
            "booking_date": (parse_date(a.get("date", "")) or now().date()).isoformat(),
            "start_time": start, "end_time": end, "attendees": 1,
            "repeat": "none", "repeat_count": 2, "equipment": [], "note": "",
        }
        return render_form(data)

    data = read_form()
    errors, room, dates = validate(data)
    if errors:
        return render_form(data, errors=errors)

    status, approved_by = status_for(room)
    group = new_group_id() if len(dates) > 1 else None
    conflict_rows = []
    with transaction() as db:
        for d in dates:
            for c in find_conflicts(db, room["id"], d.isoformat(), data["start_time"], data["end_time"]):
                conflict_rows.append(c)
        if not conflict_rows:
            for d in dates:
                db.execute(
                    "INSERT INTO bookings (room_id, user_id, title, booking_date, start_time, end_time,"
                    " attendees, equipment, note, status, recurring_group, approved_by)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (room["id"], g.user["id"], data["title"], d.isoformat(), data["start_time"],
                     data["end_time"], data["attendees"], ", ".join(data["equipment"]), data["note"],
                     status, group, approved_by),
                )

    if conflict_rows:
        msg = "ห้องไม่ว่างในช่วงเวลาที่เลือก — ไม่ได้บันทึกการจอง" if len(dates) == 1 else (
            "มีบางครั้งที่ห้องไม่ว่าง จึงไม่ได้บันทึกทั้งชุด — วันที่ชน: "
            + ", ".join(sorted({thai_date_short(c["booking_date"]) for c in conflict_rows}))
        )
        return render_form(data, errors=[msg], conflicts=conflict_rows)

    count = f" ({len(dates)} ครั้ง)" if len(dates) > 1 else ""
    if status == "pending":
        flash(f"ส่งคำขอจอง “{data['title']}”{count} แล้ว — รอผู้ดูแลอนุมัติ", "success")
    else:
        flash(f"จอง “{data['title']}”{count} สำเร็จ", "success")
    return redirect(url_for("bookings.index", date=dates[0].isoformat()))


def get_booking_or_404(booking_id):
    b = get_db().execute(
        "SELECT b.*, r.name AS room_name FROM bookings b JOIN rooms r ON r.id = b.room_id WHERE b.id = ?",
        (booking_id,),
    ).fetchone()
    if b is None:
        abort(404)
    return b


@bp.route("/bookings/<int:booking_id>/edit", methods=("GET", "POST"))
def edit(booking_id):
    booking = get_booking_or_404(booking_id)
    if booking["user_id"] != g.user["id"] and g.user["role"] != "admin":
        abort(403)
    if not can_modify(booking):
        flash("แก้ไขได้เฉพาะการจองที่ยังไม่ถึงเวลาและยังไม่ถูกยกเลิก", "error")
        return redirect(url_for("bookings.my_bookings"))

    if request.method == "GET":
        data = dict(booking)
        data["equipment"] = [e.strip() for e in booking["equipment"].split(",") if e.strip()]
        data["repeat"], data["repeat_count"] = "none", 2
        return render_form(data, booking=booking)

    data = read_form()
    errors, room, dates = validate(data, editing=True)
    if errors:
        return render_form(data, booking=booking, errors=errors)

    status, approved_by = status_for(room)
    # ถ้าไม่ได้เปลี่ยนห้อง/วัน/เวลา และเคยอนุมัติแล้ว ให้คงสถานะเดิม
    unchanged = (room["id"] == booking["room_id"] and data["booking_date"] == booking["booking_date"]
                 and data["start_time"] == booking["start_time"] and data["end_time"] == booking["end_time"])
    if unchanged and booking["status"] == "confirmed":
        status, approved_by = "confirmed", booking["approved_by"]

    with transaction() as db:
        conflicts = find_conflicts(db, room["id"], data["booking_date"], data["start_time"],
                                   data["end_time"], exclude_id=booking_id)
        if not conflicts:
            db.execute(
                "UPDATE bookings SET room_id=?, title=?, booking_date=?, start_time=?, end_time=?,"
                " attendees=?, equipment=?, note=?, status=?, approved_by=?,"
                " updated_at=datetime('now','localtime') WHERE id=?",
                (room["id"], data["title"], data["booking_date"], data["start_time"], data["end_time"],
                 data["attendees"], ", ".join(data["equipment"]), data["note"], status, approved_by,
                 booking_id),
            )
    if conflicts:
        return render_form(data, booking=booking,
                           errors=["ห้องไม่ว่างในช่วงเวลาที่เลือก — ไม่ได้บันทึกการแก้ไข"],
                           conflicts=conflicts)
    flash("บันทึกการแก้ไขเรียบร้อย" + (" — รอผู้ดูแลอนุมัติใหม่" if status == "pending" else ""), "success")
    return redirect(url_for("bookings.my_bookings"))


@bp.route("/bookings/<int:booking_id>/cancel", methods=("POST",))
def cancel(booking_id):
    booking = get_booking_or_404(booking_id)
    if booking["user_id"] != g.user["id"] and g.user["role"] != "admin":
        abort(403)
    if not can_modify(booking):
        flash("ยกเลิกได้เฉพาะการจองที่ยังไม่ถึงเวลา", "error")
        return redirect(url_for("bookings.my_bookings"))

    current = now()
    with transaction() as db:
        if request.form.get("scope") == "series" and booking["recurring_group"]:
            cur = db.execute(
                "UPDATE bookings SET status='cancelled', updated_at=datetime('now','localtime')"
                " WHERE recurring_group = ? AND user_id = ? AND status IN ('pending','confirmed')"
                " AND (booking_date > ? OR (booking_date = ? AND start_time > ?))",
                (booking["recurring_group"], booking["user_id"], current.date().isoformat(),
                 current.date().isoformat(), current.strftime("%H:%M")),
            )
            flash(f"ยกเลิกการจองทั้งชุดแล้ว ({cur.rowcount} ครั้ง)", "success")
        else:
            db.execute(
                "UPDATE bookings SET status='cancelled', updated_at=datetime('now','localtime') WHERE id = ?",
                (booking_id,),
            )
            flash(f"ยกเลิกการจอง “{booking['title']}” แล้ว", "success")
    return redirect(safe_next(request.form.get("next"), "bookings.my_bookings"))


# ---------------------------------------------------------------- my bookings
@bp.route("/my-bookings")
def my_bookings():
    tab = request.args.get("tab", "upcoming")
    if tab not in ("upcoming", "past", "cancelled"):
        tab = "upcoming"
    q = request.args.get("q", "").strip()
    current = now()
    today, hm = current.date().isoformat(), current.strftime("%H:%M")

    base = (
        "SELECT b.*, r.name AS room_name, r.location FROM bookings b JOIN rooms r ON r.id = b.room_id"
        " WHERE b.user_id = ?"
    )
    upcoming_cond = "(b.booking_date > ? OR (b.booking_date = ? AND b.end_time > ?))"
    conds = {
        "upcoming": (f" AND b.status IN ('pending','confirmed') AND {upcoming_cond}", [today, today, hm]),
        "past": (f" AND b.status IN ('pending','confirmed') AND NOT {upcoming_cond}", [today, today, hm]),
        "cancelled": (" AND b.status IN ('cancelled','rejected')", []),
    }
    counts = {}
    db = get_db()
    for key, (cond, params) in conds.items():
        counts[key] = db.execute(
            "SELECT COUNT(*) FROM bookings b WHERE b.user_id = ?" + cond, [g.user["id"], *params]
        ).fetchone()[0]

    cond, params = conds[tab]
    sql, args = base + cond, [g.user["id"], *params]
    if q:
        sql += " AND (b.title LIKE ? OR r.name LIKE ?)"
        like = f"%{q}%"
        args += [like, like]
    order = "ASC" if tab == "upcoming" else "DESC"
    sql += f" ORDER BY b.booking_date {order}, b.start_time {order}"
    rows = db.execute(sql, args).fetchall()
    items = [{"b": r, "editable": can_modify(r)} for r in rows]
    return render_template("my_bookings.html", items=items, tab=tab, q=q, counts=counts)


# ---------------------------------------------------------------- API
@bp.route("/api/availability")
def api_availability():
    a = request.args
    room = get_room(a.get("room_id", type=int) or 0)
    d = parse_date(a.get("date", ""))
    start, end = parse_time(a.get("start", "")), parse_time(a.get("end", ""))
    if room is None or d is None or start is None or end is None:
        return jsonify(error="พารามิเตอร์ไม่ครบหรือไม่ถูกต้อง (room_id, date, start, end)"), 400
    if end <= start:
        return jsonify(error="เวลาสิ้นสุดต้องมากกว่าเวลาเริ่ม"), 400
    exclude_id = a.get("exclude_id", type=int)
    attendees = a.get("attendees", type=int) or 1

    db = get_db()
    conflicts = find_conflicts(db, room["id"], d.isoformat(), start, end, exclude_id)
    suggestions = suggest_rooms(db, d.isoformat(), start, end, attendees, room["id"], exclude_id) if conflicts else []
    return jsonify(
        available=not conflicts and bool(room["is_active"]),
        room={"id": room["id"], "name": room["name"], "capacity": room["capacity"],
              "is_active": bool(room["is_active"])},
        conflicts=[
            {"id": c["id"], "title": c["title"], "start": c["start_time"], "end": c["end_time"],
             "status": c["status"], "user": c["user_name"]}
            for c in conflicts
        ],
        suggestions=[
            {"id": r["id"], "name": r["name"], "location": r["location"], "capacity": r["capacity"]}
            for r in suggestions
        ],
    )


@bp.route("/api/schedule")
def api_schedule():
    room = get_room(request.args.get("room_id", type=int) or 0)
    d = parse_date(request.args.get("date", ""))
    if room is None or d is None:
        return jsonify(error="พารามิเตอร์ไม่ถูกต้อง"), 400
    busy, free = day_schedule(get_db(), room["id"], d.isoformat(), request.args.get("exclude_id", type=int))
    for b in busy:
        b["mine"] = b.pop("user_id") == g.user["id"]
    return jsonify(
        room={"id": room["id"], "name": room["name"], "location": room["location"],
              "capacity": room["capacity"], "equipment": room["equipment"],
              "require_approval": bool(room["require_approval"])},
        busy=busy,
        free=free,
    )
