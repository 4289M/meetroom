# MeetRoom – ระบบจองห้องประชุม

เว็บแอปจองห้องประชุม พัฒนาด้วย **Python Flask + SQLite3** (ใช้โมดูล `sqlite3` ของ Python โดยตรง ไม่ใช้ ORM)
หน้าจอเป็นภาษาไทยทั้งหมด แสดงวันที่แบบ พ.ศ. และรองรับมือถือ

## ความต้องการของระบบ

- Windows 10/11 (รันบน macOS/Linux ได้เช่นกัน)
- Python 3.10 ขึ้นไป

## การติดตั้งและรันบน Windows

เปิด **PowerShell** แล้ว `cd` เข้าโฟลเดอร์ `meetroom` (โฟลเดอร์ที่มี `app.py`)

```powershell
cd "D:\โปรเจ็ค\จองห้องประชุม\meetroom"

# 1) สร้าง virtual environment (แนะนำ)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2) ติดตั้งแพ็กเกจ
pip install -r requirements.txt

# 3) สร้างฐานข้อมูล + ข้อมูลตัวอย่าง (instance\meetroom.db)
flask --app app init-db

# 4) รันเซิร์ฟเวอร์
flask --app app run --debug
```

เปิดเบราว์เซอร์ที่ <http://127.0.0.1:5000>

> **หมายเหตุสำหรับ Windows**
> - ถ้า PowerShell ไม่ยอมรัน `Activate.ps1` ให้รัน `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` ครั้งเดียว
>   หรือใช้ `cmd` แล้วรัน `.venv\Scripts\activate.bat` แทน
> - ทุกไฟล์ในโปรเจคเป็น UTF-8 และโปรแกรมอ่าน/เขียนไฟล์ด้วย `encoding="utf-8"` เสมอ
>   จึงวางโปรเจคในโฟลเดอร์ชื่อภาษาไทยได้
> - ถ้าข้อความภาษาไทยในคอนโซลแสดงผลเพี้ยน ให้ตั้ง `$env:PYTHONUTF8 = "1"` ก่อนรันคำสั่ง
> - `flask --app app init-db` จะ **ลบข้อมูลเดิมทั้งหมด** แล้วสร้างใหม่ ใช้ `--no-seed` ถ้าต้องการตารางเปล่า

### ตั้งค่า SECRET_KEY (สำหรับใช้งานจริง)

```powershell
$env:SECRET_KEY = "ค่าสุ่มยาวๆ-ที่เดาไม่ได้"
flask --app app run
```

ถ้าไม่ตั้ง ระบบจะใช้ค่า default สำหรับ dev เท่านั้น

## บัญชีทดสอบ

| ชื่อผู้ใช้ | รหัสผ่าน | สิทธิ์ | แผนก |
|-----------|----------|--------|------|
| `admin`   | `admin123` | ผู้ดูแลระบบ | ฝ่ายธุรการ |
| `somchai` | `user123`  | ผู้ใช้ทั่วไป | ฝ่าย IT |
| `suda`    | `user123`  | ผู้ใช้ทั่วไป | ฝ่ายบัญชี |

ห้องตัวอย่าง: ห้องประชุม 1 (ชั้น 3, 10 ที่), ห้องประชุม 2 (ชั้น 3, 6 ที่),
ห้องประชุมใหญ่ (ชั้น 5, 30 ที่, **ต้องอนุมัติ**), ห้อง Online/Zoom (ชั้น 2, 4 ที่)
พร้อมการจองตัวอย่างของวันนี้ 7 รายการ (คำนวณจากวันที่ที่รัน `init-db`)

## การรันเทสต์

```powershell
python -m pytest -q
```

เทสต์ใช้ฐานข้อมูลชั่วคราวแยกต่างหาก ไม่กระทบ `instance\meetroom.db`
ครอบคลุม: login/logout, CSRF, จองสำเร็จ, จองชน, เกินความจุ, กฎเวลา, จองซ้ำ, API ตรวจห้องว่าง,
แก้ไข/ยกเลิก (รายครั้ง/ทั้งชุด), สิทธิ์ผู้ใช้/แอดมิน, อนุมัติ/ไม่อนุมัติ, จัดการห้องและผู้ใช้

## ฟีเจอร์

| หน้า | URL | รายละเอียด |
|------|-----|-----------|
| เข้าสู่ระบบ | `/login` | session-based, ข้อความผิดพลาดภาษาไทย |
| ภาพรวม | `/` | การ์ดสรุป 4 ใบ + timeline ห้อง × เวลา 08:00–18:00, เส้นเวลาปัจจุบัน, คลิกช่องว่างเพื่อจอง |
| จองห้อง | `/bookings/new` | ฟอร์มจอง + จองซ้ำ (ทุกวัน/ทุกสัปดาห์ สูงสุด 12 ครั้ง) + แผงช่วงเวลาว่าง/ไม่ว่าง |
| แก้ไขการจอง | `/bookings/<id>/edit` | แก้ได้เฉพาะของตัวเองที่ยังไม่ถึงเวลา |
| การจองของฉัน | `/my-bookings` | แท็บ กำลังจะถึง/ที่ผ่านมา/ยกเลิกแล้ว + ค้นหา, ยกเลิกเฉพาะครั้งนี้หรือทั้งชุด |
| จัดการห้อง (Admin) | `/admin/rooms` | เพิ่ม/แก้ไข/ลบห้อง (ลบไม่ได้ถ้ามีการจองในอนาคต), อนุมัติ/ไม่อนุมัติคำขอ |
| จัดการผู้ใช้ (Admin) | `/admin/users` | เพิ่มผู้ใช้, รีเซ็ตรหัสผ่าน, เปลี่ยนสิทธิ์, เปิด/ปิดใช้งาน |
| API | `GET /api/availability?room_id=&date=&start=&end=&exclude_id=&attendees=` | คืน `{available, conflicts[], suggestions[]}` |
| API | `GET /api/schedule?room_id=&date=&exclude_id=` | ช่วงเวลาว่าง/ไม่ว่างของห้องในวันนั้น |

### กฎทางธุรกิจ (ตรวจฝั่ง server ทุกครั้ง)

- เวลาสิ้นสุด > เวลาเริ่ม, อยู่ในช่วง 08:00–18:00, ทีละ 30 นาที, ยาวไม่เกิน 4 ชั่วโมง
- จองย้อนหลังไม่ได้ และจองล่วงหน้าได้ไม่เกิน 30 วัน (ทุกครั้งของการจองซ้ำ)
- จำนวนผู้เข้าร่วมต้องไม่เกินความจุห้อง
- เวลาชนกันเมื่อ `new_start < exist_end AND new_end > exist_start` (นับเฉพาะ `pending`/`confirmed`)
- การจองซ้ำ: ถ้ามีครั้งใดชน จะแจ้งวันที่ที่ชนและไม่บันทึกทั้งชุด
- ตรวจชน + บันทึกอยู่ใน transaction เดียว (`BEGIN IMMEDIATE`) กันการจองชนพร้อมกัน
- ห้องที่ต้องอนุมัติ → สถานะ `pending` จนกว่าแอดมินอนุมัติ (ตรวจชนอีกครั้งตอนอนุมัติ)
- ยกเลิก = soft delete (`status = 'cancelled'`)

### ความปลอดภัย

- รหัสผ่านเก็บแบบ hash (`werkzeug.security`)
- CSRF token ในทุกฟอร์ม POST (เก็บใน session, ตรวจด้วย `hmac.compare_digest`)
- ใช้ parameterized query ทุกคำสั่ง SQL, Jinja autoescape ป้องกัน XSS
- ตรวจสิทธิ์ทุก route: ผู้ใช้แก้/ยกเลิกได้เฉพาะของตัวเอง, `/admin/*` เฉพาะแอดมิน
- ป้องกัน open redirect ในพารามิเตอร์ `next`

## โครงสร้างไฟล์

```
meetroom/
├── app.py              # create_app() ลงทะเบียน blueprint, filter, CLI
├── db.py               # get_db(), close_db(), transaction(), init_db(), seed, คำสั่ง init-db
├── schema.sql          # ตาราง users / rooms / bookings + index
├── auth.py             # login/logout, login_required, admin_required, CSRF, error pages
├── bookings.py         # timeline, ฟอร์มจอง, การจองของฉัน, API ตรวจห้องว่าง
├── admin.py            # จัดการห้อง, อนุมัติการจอง, จัดการผู้ใช้
├── utils.py            # วันที่ไทย (พ.ศ.), แปลงเวลา, Jinja filters
├── templates/
│   ├── base.html           # layout + header + flash message
│   ├── _macros.html        # ไอคอน, badge สถานะ
│   ├── _admin_tabs.html    # แท็บเมนูแอดมิน
│   ├── login.html
│   ├── index.html          # ภาพรวม / timeline
│   ├── booking_form.html   # จอง / แก้ไข
│   ├── my_bookings.html
│   ├── admin_rooms.html
│   ├── admin_users.html
│   └── error.html          # 400 / 403 / 404
├── static/
│   ├── css/style.css
│   └── js/app.js           # vanilla JS: timeline click, ตรวจห้องว่าง, ยืนยันก่อนยกเลิก
├── tests/              # pytest
│   ├── conftest.py
│   ├── test_auth.py
│   ├── test_bookings.py
│   └── test_admin.py
├── instance/meetroom.db   # สร้างโดย init-db (ไม่ต้อง commit)
├── requirements.txt
└── README.md
```
