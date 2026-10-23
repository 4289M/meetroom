from conftest import booking_data, day

from db import get_db


def count_bookings(app, **where):
    sql = "SELECT COUNT(*) FROM bookings WHERE 1=1"
    params = []
    for k, v in where.items():
        sql += f" AND {k} = ?"
        params.append(v)
    with app.app_context():
        return get_db().execute(sql, params).fetchone()[0]


def test_timeline_renders(client, auth):
    auth.login()
    r = client.get("/")
    text = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "ห้องประชุมใหญ่" in text
    assert "tl-block" in text
    assert client.get(f"/?date={day(3)}").status_code == 200


def test_booking_success(app, auth):
    auth.login()
    r = auth.post("/bookings/new", booking_data(equipment=["โปรเจคเตอร์", "อาหารว่าง"]))
    assert r.status_code == 302
    with app.app_context():
        b = get_db().execute("SELECT * FROM bookings WHERE title = 'ประชุมทดสอบ'").fetchone()
    assert b["status"] == "confirmed"
    assert b["equipment"] == "โปรเจคเตอร์, อาหารว่าง"
    assert b["user_id"] == 2


def test_booking_conflict(app, auth):
    auth.login()
    assert auth.post("/bookings/new", booking_data()).status_code == 302
    # ซ้อนช่วง 13:30–14:30 ในห้องเดียวกัน
    r = auth.post("/bookings/new", booking_data(title="ชน", start_time="13:30", end_time="14:30"))
    assert r.status_code == 400
    assert "ห้องไม่ว่าง" in r.get_data(as_text=True)
    assert count_bookings(app, title="ชน") == 0


def test_adjacent_booking_is_not_conflict(auth):
    auth.login()
    assert auth.post("/bookings/new", booking_data()).status_code == 302
    r = auth.post("/bookings/new", booking_data(title="ต่อกัน", start_time="14:00", end_time="15:00"))
    assert r.status_code == 302


def test_cancelled_booking_frees_slot(app, auth):
    auth.login()
    auth.post("/bookings/new", booking_data())
    with app.app_context():
        bid = get_db().execute("SELECT id FROM bookings WHERE title = 'ประชุมทดสอบ'").fetchone()[0]
    auth.post(f"/bookings/{bid}/cancel", {"scope": "one"})
    assert auth.post("/bookings/new", booking_data(title="ใหม่")).status_code == 302


def test_over_capacity(app, auth):
    auth.login()
    r = auth.post("/bookings/new", booking_data(room_id=2, attendees=7))  # ห้องประชุม 2 จุ 6 คน
    assert r.status_code == 400
    assert "เกินความจุ" in r.get_data(as_text=True)
    assert count_bookings(app, title="ประชุมทดสอบ") == 0


def test_time_rules(auth):
    auth.login()
    cases = [
        dict(start_time="14:00", end_time="13:00"),          # end <= start
        dict(start_time="07:00", end_time="08:30"),          # ก่อน 08:00
        dict(start_time="17:00", end_time="18:30"),          # หลัง 18:00
        dict(start_time="09:00", end_time="13:30"),          # เกิน 4 ชม.
        dict(start_time="09:15", end_time="10:00"),          # ไม่ลงช่วง 30 นาที
        dict(booking_date=day(-1)),                          # ย้อนหลัง
        dict(booking_date=day(31)),                          # เกิน 30 วัน
    ]
    for c in cases:
        r = auth.post("/bookings/new", booking_data(**c))
        assert r.status_code == 400, c


def test_require_approval_room_is_pending(app, auth):
    auth.login()
    auth.post("/bookings/new", booking_data(room_id=3, attendees=20))
    assert count_bookings(app, title="ประชุมทดสอบ", status="pending") == 1


def test_recurring_booking_and_conflict(app, auth):
    auth.login()
    r = auth.post("/bookings/new", booking_data(repeat="daily", repeat_count=3, booking_date=day(5)))
    assert r.status_code == 302
    assert count_bookings(app, title="ประชุมทดสอบ") == 3

    # ชุดใหม่ที่ชนแค่ 1 ครั้ง -> ไม่บันทึกทั้งชุด
    r = auth.post("/bookings/new", booking_data(
        title="ชุดชน", repeat="daily", repeat_count=3, booking_date=day(7)))
    assert r.status_code == 400
    assert "ไม่ได้บันทึกทั้งชุด" in r.get_data(as_text=True)
    assert count_bookings(app, title="ชุดชน") == 0


def test_availability_api(auth):
    auth.login()
    auth.post("/bookings/new", booking_data())
    r = auth.client.get(f"/api/availability?room_id=1&date={day(2)}&start=13:30&end=14:30&attendees=5")
    data = r.get_json()
    assert data["available"] is False
    assert data["conflicts"][0]["title"] == "ประชุมทดสอบ"
    names = [s["name"] for s in data["suggestions"]]
    assert "ห้องประชุม 2" in names and "ห้อง Online/Zoom" not in names  # Zoom จุ 4 < 5

    r = auth.client.get(f"/api/availability?room_id=1&date={day(2)}&start=15:00&end=16:00")
    assert r.get_json()["available"] is True
    assert auth.client.get("/api/availability?room_id=1").status_code == 400


def test_edit_own_booking_excludes_self(app, auth):
    auth.login()
    auth.post("/bookings/new", booking_data())
    with app.app_context():
        bid = get_db().execute("SELECT id FROM bookings WHERE title = 'ประชุมทดสอบ'").fetchone()[0]
    # ขยายเวลาทับช่วงเดิมของตัวเองได้
    r = auth.post(f"/bookings/{bid}/edit", booking_data(title="แก้แล้ว", end_time="15:00"))
    assert r.status_code == 302
    assert count_bookings(app, title="แก้แล้ว", end_time="15:00") == 1


def test_cancel_booking(app, auth):
    auth.login()
    auth.post("/bookings/new", booking_data())
    with app.app_context():
        bid = get_db().execute("SELECT id FROM bookings WHERE title = 'ประชุมทดสอบ'").fetchone()[0]
    r = auth.post(f"/bookings/{bid}/cancel", {"scope": "one"})
    assert r.status_code == 302
    # soft delete: ยังอยู่ในตาราง แต่สถานะเป็น cancelled
    assert count_bookings(app, id=bid, status="cancelled") == 1
    r = auth.client.get("/my-bookings?tab=cancelled")
    assert "ประชุมทดสอบ" in r.get_data(as_text=True)


def test_cancel_requires_post(app, auth):
    auth.login()
    auth.post("/bookings/new", booking_data())
    with app.app_context():
        bid = get_db().execute("SELECT id FROM bookings WHERE title = 'ประชุมทดสอบ'").fetchone()[0]
    assert auth.client.get(f"/bookings/{bid}/cancel").status_code == 405


def test_cancel_recurring_series(app, auth):
    auth.login()
    auth.post("/bookings/new", booking_data(repeat="weekly", repeat_count=3, booking_date=day(1)))
    with app.app_context():
        ids = [r[0] for r in get_db().execute(
            "SELECT id FROM bookings WHERE title = 'ประชุมทดสอบ' ORDER BY booking_date")]
    auth.post(f"/bookings/{ids[0]}/cancel", {"scope": "one"})
    assert count_bookings(app, title="ประชุมทดสอบ", status="cancelled") == 1
    auth.post(f"/bookings/{ids[1]}/cancel", {"scope": "series"})
    assert count_bookings(app, title="ประชุมทดสอบ", status="cancelled") == 3


def test_cannot_touch_other_users_booking(app, client, auth):
    auth.login("suda", "user123")
    auth.post("/bookings/new", booking_data(title="ของสุดา"))
    with app.app_context():
        bid = get_db().execute("SELECT id FROM bookings WHERE title = 'ของสุดา'").fetchone()[0]
    auth.post("/logout")

    auth.login("somchai", "user123")
    assert client.get(f"/bookings/{bid}/edit").status_code == 403
    assert auth.post(f"/bookings/{bid}/cancel", {"scope": "one"}).status_code == 403
    assert count_bookings(app, id=bid, status="confirmed") == 1


def test_my_bookings_tabs_and_search(auth):
    auth.login()
    auth.post("/bookings/new", booking_data(title="Sprint Review"))
    r = auth.client.get("/my-bookings?q=Sprint")
    text = r.get_data(as_text=True)
    assert "Sprint Review" in text
    r = auth.client.get("/my-bookings?q=ไม่มีแน่นอน")
    assert "Sprint Review" not in r.get_data(as_text=True)
    assert auth.client.get("/my-bookings?tab=past").status_code == 200
