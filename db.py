"""การเชื่อมต่อฐานข้อมูล SQLite3 (ไม่ใช้ ORM)"""
import sqlite3
import sys
import uuid
from contextlib import contextmanager
from datetime import date, timedelta

import click
from flask import current_app, g
from werkzeug.security import generate_password_hash


def get_db():
    """คืน connection ของ request ปัจจุบัน (สร้างใหม่ถ้ายังไม่มี)"""
    if "db" not in g:
        # isolation_level=None = autocommit; เราควบคุม transaction เองด้วย BEGIN IMMEDIATE
        conn = sqlite3.connect(
            current_app.config["DATABASE"],
            isolation_level=None,
            timeout=10,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@contextmanager
def transaction():
    """เปิด transaction แบบ BEGIN IMMEDIATE (ล็อกการเขียนทันที กันจองชนพร้อมกัน)"""
    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    try:
        yield db
    except BaseException:
        db.execute("ROLLBACK")
        raise
    else:
        db.execute("COMMIT")


def init_db():
    db = get_db()
    with current_app.open_resource("schema.sql", mode="r", encoding="utf-8") as f:
        db.executescript(f.read())


def seed_db():
    db = get_db()
    users = [
        ("admin", "admin123", "ผู้ดูแลระบบ", "ฝ่ายธุรการ", "admin"),
        ("somchai", "user123", "สมชาย ใจดี", "ฝ่าย IT", "user"),
        ("suda", "user123", "สุดา รักงาน", "ฝ่ายบัญชี", "user"),
    ]
    for username, pw, full_name, dept, role in users:
        db.execute(
            "INSERT INTO users (username, password_hash, full_name, department, role)"
            " VALUES (?, ?, ?, ?, ?)",
            (username, generate_password_hash(pw), full_name, dept, role),
        )

    rooms = [
        ("ห้องประชุม 1", "ชั้น 3", 10, "โปรเจคเตอร์, ไวท์บอร์ด", 0),
        ("ห้องประชุม 2", "ชั้น 3", 6, "จอทีวี 55 นิ้ว, ไวท์บอร์ด", 0),
        ("ห้องประชุมใหญ่", "ชั้น 5", 30, "โปรเจคเตอร์, ไมโครโฟน, ระบบเสียง", 1),
        ("ห้อง Online/Zoom", "ชั้น 2", 4, "กล้อง VDO Conference, ลำโพง", 0),
    ]
    for name, loc, cap, equip, approval in rooms:
        db.execute(
            "INSERT INTO rooms (name, location, capacity, equipment, require_approval)"
            " VALUES (?, ?, ?, ?, ?)",
            (name, loc, cap, equip, approval),
        )

    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    # (room_id, user_id, title, date, start, end, attendees, equipment, status)
    bookings = [
        (1, 2, "ประชุมทีม IT ประจำสัปดาห์", today, "09:00", "10:30", 8, "โปรเจคเตอร์", "confirmed"),
        (1, 3, "ปิดงบประมาณไตรมาส", today, "13:00", "14:30", 6, "", "confirmed"),
        (2, 3, "สัมภาษณ์พนักงานใหม่", today, "10:00", "11:00", 3, "", "confirmed"),
        (2, 2, "Code Review", today, "15:00", "16:00", 5, "", "confirmed"),
        (3, 1, "ประชุมผู้บริหารประจำเดือน", today, "08:30", "11:30", 25, "โปรเจคเตอร์, ไมโครโฟน", "confirmed"),
        (3, 2, "อบรมระบบใหม่", today, "14:00", "17:00", 20, "โปรเจคเตอร์, ไมโครโฟน", "pending"),
        (4, 2, "คุยงานกับลูกค้า (Zoom)", today, "11:00", "12:00", 3, "กล้อง VDO Conference", "confirmed"),
        (1, 2, "วางแผน Sprint", tomorrow, "09:00", "10:00", 7, "", "confirmed"),
    ]
    for b in bookings:
        db.execute(
            "INSERT INTO bookings (room_id, user_id, title, booking_date, start_time, end_time,"
            " attendees, equipment, status, approved_by) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (*b, 1 if b[8] == "confirmed" and b[0] == 3 else None),
        )


def new_group_id():
    return uuid.uuid4().hex


@click.command("init-db")
@click.option("--no-seed", is_flag=True, help="สร้างตารางเปล่าโดยไม่ใส่ข้อมูลตัวอย่าง")
def init_db_command(no_seed):
    """ลบและสร้างตารางใหม่ + ใส่ข้อมูลตัวอย่าง"""
    # คอนโซล Windows บางตัวใช้ cp1252/cp874 — บังคับ UTF-8 กันข้อความไทย error
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    init_db()
    if not no_seed:
        seed_db()
    click.echo("สร้างฐานข้อมูลเรียบร้อย: " + current_app.config["DATABASE"])


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
