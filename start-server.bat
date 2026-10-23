@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
set SECRET_KEY=เปลี่ยนเป็นค่าสุ่มยาวๆ
.venv\Scripts\python.exe -m waitress --host 0.0.0.0 --port 5000 --call app:create_app
pause