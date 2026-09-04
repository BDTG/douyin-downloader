@echo off
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
  echo Chua co .venv. Chay: uv venv --python 3.11 .venv ^&^& uv pip install --python .venv\Scripts\python.exe -r downloader\requirements.txt fastapi "uvicorn[standard]"
  pause
  exit /b 1
)
set DL_DIR=%~dp0downloads
set ALIAS_PATH=%~dp0aliases.json
start "douyin-api" .venv\Scripts\python.exe downloader\run.py -c api\config.native.yml --serve --serve-host 127.0.0.1 --serve-port 8000
start "douyin-gallery" /d gallery .venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8001
start "douyin-web" .venv\Scripts\python.exe web\server.py
echo.
echo  Web tracker : http://localhost:8080
echo  Gallery     : http://localhost:8080/gallery/
echo  File da tai : http://localhost:8080/files/
echo  API truc tiep: http://localhost:8000/api/v1/health
pause
