def test_redirects_to_login_when_anonymous(client):
    for url in ("/", "/bookings/new", "/my-bookings", "/admin/rooms"):
        r = client.get(url)
        assert r.status_code == 302
        assert "/login" in r.headers["Location"]


def test_api_requires_login(client):
    r = client.get("/api/availability?room_id=1&date=2030-01-01&start=09:00&end=10:00")
    assert r.status_code == 401


def test_login_success(client, auth):
    r = auth.login()
    assert r.status_code == 302
    r = client.get("/")
    assert r.status_code == 200
    assert "สมชาย ใจดี" in r.get_data(as_text=True)


def test_login_wrong_password(client, auth):
    r = auth.login(password="wrong")
    assert r.status_code == 200
    assert "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง" in r.get_data(as_text=True)
    assert client.get("/").status_code == 302


def test_login_rejects_missing_csrf(client):
    client.get("/login")
    r = client.post("/login", data={"username": "somchai", "password": "user123"})
    assert r.status_code == 400


def test_login_blocks_open_redirect(auth):
    auth.client.get("/login")
    r = auth.client.post(
        "/login?next=//evil.example.com",
        data={"username": "somchai", "password": "user123", "_csrf": auth.csrf()},
    )
    assert r.headers["Location"] == "/"


def test_logout(client, auth):
    auth.login()
    r = auth.post("/logout")
    assert r.status_code == 302
    assert client.get("/").status_code == 302


def test_inactive_user_cannot_login(app, auth):
    from db import get_db
    with app.app_context():
        get_db().execute("UPDATE users SET is_active = 0 WHERE username = 'somchai'")
    r = auth.login()
    assert "ถูกปิดใช้งาน" in r.get_data(as_text=True)
