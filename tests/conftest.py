import os
import sys
from datetime import date, timedelta

import pytest

# ให้ import โมดูลของโปรเจค (app, db, ...) ได้เมื่อรัน pytest จากโฟลเดอร์ไหนก็ได้
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from db import init_db, seed_db  # noqa: E402


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path / "test.db"),
        "SECRET_KEY": "test",
    })
    with app.app_context():
        init_db()
        seed_db()
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def day(n):
    """วันที่ล่วงหน้า n วันจากวันนี้ (YYYY-MM-DD)"""
    return (date.today() + timedelta(days=n)).isoformat()


class Auth:
    def __init__(self, client):
        self.client = client

    def csrf(self):
        with self.client.session_transaction() as s:
            token = s.get("_csrf")
        if not token:
            # หน้าใดก็ได้ที่ render template จะสร้าง token ให้ (login แล้ว /login จะ redirect)
            self.client.get("/login", follow_redirects=True)
            with self.client.session_transaction() as s:
                token = s["_csrf"]
        return token

    def login(self, username="somchai", password="user123"):
        return self.client.post(
            "/login", data={"username": username, "password": password, "_csrf": self.csrf()}
        )

    def post(self, url, data=None, **kw):
        data = dict(data or {})
        data.setdefault("_csrf", self.csrf())
        return self.client.post(url, data=data, **kw)


@pytest.fixture
def auth(client):
    return Auth(client)


def booking_data(**overrides):
    data = {
        "title": "ประชุมทดสอบ",
        "room_id": 1,
        "booking_date": day(2),
        "start_time": "13:00",
        "end_time": "14:00",
        "attendees": 4,
        "repeat": "none",
        "repeat_count": 2,
        "note": "",
    }
    data.update(overrides)
    return data
