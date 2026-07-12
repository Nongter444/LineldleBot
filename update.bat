@echo off
chcp 65001 >nul
color 0a
title GitHub Sync - Line Idle Manager

:MENU
cls
echo ==================================================
echo         ระบบจัดการโค้ด GitHub (Git Sync)
echo ==================================================
echo [1] เครื่องรอง : ดึงอัปเดตล่าสุดจาก GitHub (Git Pull)
echo [2] เครื่องหลัก : อัปโหลดโค้ดขึ้น GitHub (Git Push)
echo [3] ออกจากโปรแกรม
echo ==================================================
set /p choice="เลือกเมนูที่ต้องการ (1/2/3): "

if "%choice%"=="1" goto PULL
if "%choice%"=="2" goto PUSH
if "%choice%"=="3" goto END

echo เลือกผิด กรุณาลองใหม่...
timeout /t 2 >nul
goto MENU

:PULL
echo.
echo ⏳ กำลังดึงข้อมูลล่าสุดจาก GitHub...
git pull
echo.
echo ✅ อัปเดตไฟล์ในเครื่องเรียบร้อยแล้ว!
pause
goto MENU

:PUSH
echo.
set /p msg="พิมพ์รายละเอียดการอัปเดต (กด Enter เพื่อข้าม): "
if "%msg%"=="" set msg="Auto update from bat file"
echo.
echo ⏳ กำลังเตรียมไฟล์และอัปโหลดขึ้น GitHub...
git add .
git commit -m "%msg%"
git push
echo.
echo ✅ อัปโหลดโค้ดขึ้น GitHub เรียบร้อยแล้ว!
pause
goto MENU

:END
exit