@echo off
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000,8001,8080 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"
echo Da dung stack native (8000/8001/8080).
pause
