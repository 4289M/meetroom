"""ตัวช่วยเรื่องวันที่/เวลาแบบไทย"""
from datetime import date, datetime

THAI_DAYS = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
THAI_MONTHS = [
    "", "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
]
THAI_MONTHS_SHORT = [
    "", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
]

STATUS_LABELS = {
    "pending": "รออนุมัติ",
    "confirmed": "ยืนยันแล้ว",
    "rejected": "ไม่อนุมัติ",
    "cancelled": "ยกเลิกแล้ว",
}

# ช่วงเวลาที่เปิดให้จอง
DAY_START = "08:00"
DAY_END = "18:00"


def to_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def thai_date(value, weekday=True):
    """'2026-10-22' -> 'พฤหัสบดี 22 ตุลาคม 2569'"""
    if not value:
        return ""
    d = to_date(value)
    text = f"{d.day} {THAI_MONTHS[d.month]} {d.year + 543}"
    return f"{THAI_DAYS[d.weekday()]} {text}" if weekday else text


def thai_date_short(value):
    """'2026-10-22' -> '22 ต.ค. 69'"""
    if not value:
        return ""
    d = to_date(value)
    return f"{d.day} {THAI_MONTHS_SHORT[d.month]} {str(d.year + 543)[-2:]}"


def to_minutes(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def from_minutes(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def parse_time(value):
    """คืน 'HH:MM' ถ้ารูปแบบถูกต้อง ไม่งั้น None"""
    try:
        return datetime.strptime((value or "").strip()[:5], "%H:%M").strftime("%H:%M")
    except ValueError:
        return None


def parse_date(value):
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError:
        return None


def register_filters(app):
    app.jinja_env.filters["thai_date"] = thai_date
    app.jinja_env.filters["thai_date_short"] = thai_date_short
    app.jinja_env.filters["status_label"] = lambda s: STATUS_LABELS.get(s, s)
