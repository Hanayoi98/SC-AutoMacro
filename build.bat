@echo off
echo 기본패키지.exe 빌드 시작...
python -m PyInstaller --onefile --noconsole --name 기본패키지 setup_installer.py
echo.
echo 완료: dist\기본패키지.exe
pause
