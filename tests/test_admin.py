from conftest import booking_data, day

from db import get_db


def query_one(app, sql, params=()):
    with app.app_context():
        return get_db().execute(sql, params).fetchone()


def test_user_cannot_access_admin(client, auth):
    auth.login()
    assert client.get("/admin/rooms").status_code == 403
    assert client.get("/admin/users").status_code == 403
    assert auth.post("/admin/rooms/save", {"name": "แฮก", "capacity": 5}).status_code == 403
    assert auth.post("/admin/users/add", {"username": "x", "full_name": "x",
                                          "password": "123456"}).status_code == 403


def test_admin_menu_visibility(client, auth):
    auth.login()
    assert "จัดการห้อง" not in client.get("/").get_data(as_text=True)
    auth.post("/logout")
    auth.login("admin", "admin123")
    assert "จัดการห้อง" in client.get("/").get_data(as_text=True)


def test_admin_can_add_and_edit_room(app, client, auth):
    auth.login("admin", "admin123")
    assert client.get("/admin/rooms").status_code == 200
    r = auth.post("/admin/rooms/save", {"name": "ห้องใหม่", "location": "ชั้น 7", "capacity": 8,
                                        "is_active": "1"})
    assert r.status_code == 302
    room = query_one(app, "SELECT * FROM rooms WHERE name = 'ห้องใหม่'")
    assert room["capacity"] == 8 and room["is_active"] == 1

    r = auth.post("/admin/rooms/save", {"id": room["id"], "name": "ห้องใหม่", "capacity": 12})
    room = query_one(app, "SELECT * FROM rooms WHERE id = ?", (room["id"],))
    assert room["capacity"] == 12 and room["is_active"] == 0

    r = auth.post("/admin/rooms/save", {"name": "ห้องประชุม 1", "capacity": 5})
    assert r.status_code == 400  # ชื่อซ้ำ


def test_cannot_delete_room_with_future_bookings(app, auth):
    auth.login("admin", "admin123")
    auth.post("/admin/rooms/save", {"name": "ห้องลบได้", "capacity": 4, "is_active": "1"})
    rid = query_one(app, "SELECT id FROM rooms WHERE name = 'ห้องลบได้'")[0]
    auth.post("/bookings/new", booking_data(room_id=rid, attendees=2))

    auth.post(f"/admin/rooms/{rid}/delete")
    assert query_one(app, "SELECT COUNT(*) FROM rooms WHERE id = ?", (rid,))[0] == 1

    auth.post("/admin/rooms/save", {"name": "ห้องว่างเปล่า", "capacity": 4})
    rid2 = query_one(app, "SELECT id FROM rooms WHERE name = 'ห้องว่างเปล่า'")[0]
    auth.post(f"/admin/rooms/{rid2}/delete")
    assert query_one(app, "SELECT COUNT(*) FROM rooms WHERE id = ?", (rid2,))[0] == 0


def test_approve_and_reject(app, auth):
    auth.login()
    auth.post("/bookings/new", booking_data(room_id=3, attendees=10, title="ขออนุมัติ 1"))
    auth.post("/bookings/new", booking_data(room_id=3, attendees=10, title="ขออนุมัติ 2",
                                            start_time="15:00", end_time="16:00"))
    auth.post("/logout")

    auth.login("admin", "admin123")
    b1 = query_one(app, "SELECT id FROM bookings WHERE title = 'ขออนุมัติ 1'")[0]
    b2 = query_one(app, "SELECT id FROM bookings WHERE title = 'ขออนุมัติ 2'")[0]
    auth.post(f"/admin/bookings/{b1}/approve")
    auth.post(f"/admin/bookings/{b2}/reject")
    r1 = query_one(app, "SELECT status, approved_by FROM bookings WHERE id = ?", (b1,))
    r2 = query_one(app, "SELECT status FROM bookings WHERE id = ?", (b2,))
    assert r1["status"] == "confirmed" and r1["approved_by"] == 1
    assert r2["status"] == "rejected"


def test_approve_rechecks_conflict(app, auth):
    auth.login()
    auth.post("/bookings/new", booking_data(room_id=3, attendees=10, title="คำขอ"))
    bid = query_one(app, "SELECT id FROM bookings WHERE title = 'คำขอ'")[0]
    # จำลองว่ามีการจองที่ยืนยันแล้วเข้ามาทับ (เช่นแก้ข้อมูลตรงในฐานข้อมูล)
    with app.app_context():
        get_db().execute(
            "INSERT INTO bookings (room_id, user_id, title, booking_date, start_time, end_time, status)"
            " VALUES (3, 1, 'ทับ', ?, '13:00', '14:00', 'confirmed')", (day(2),))
    auth.post("/logout")
    auth.login("admin", "admin123")
    r = auth.post(f"/admin/bookings/{bid}/approve", follow_redirects=True)
    assert "อนุมัติไม่ได้" in r.get_data(as_text=True)
    assert query_one(app, "SELECT status FROM bookings WHERE id = ?", (bid,))[0] == "pending"


def test_admin_user_management(app, client, auth):
    auth.login("admin", "admin123")
    assert client.get("/admin/users").status_code == 200
    r = auth.post("/admin/users/add", {"username": "newbie", "full_name": "พนักงานใหม่",
                                       "department": "ฝ่ายขาย", "password": "secret1", "role": "user"})
    assert r.status_code == 302
    uid = query_one(app, "SELECT id FROM users WHERE username = 'newbie'")[0]

    auth.post(f"/admin/users/{uid}/role", {"role": "admin"})
    assert query_one(app, "SELECT role FROM users WHERE id = ?", (uid,))[0] == "admin"

    auth.post(f"/admin/users/{uid}/reset-password", {"password": "changed1"})
    auth.post(f"/admin/users/{uid}/toggle-active")
    assert query_one(app, "SELECT is_active FROM users WHERE id = ?", (uid,))[0] == 0

    # admin ปิดใช้งาน/ลดสิทธิ์ตัวเองไม่ได้
    auth.post("/admin/users/1/toggle-active")
    auth.post("/admin/users/1/role", {"role": "user"})
    me = query_one(app, "SELECT role, is_active FROM users WHERE id = 1")
    assert me["role"] == "admin" and me["is_active"] == 1

    # ผู้ใช้ใหม่ login ด้วยรหัสที่รีเซ็ตได้หลังเปิดใช้งาน
    auth.post(f"/admin/users/{uid}/toggle-active")
    auth.post("/logout")
    r = auth.login("newbie", "changed1")
    assert r.status_code == 302
