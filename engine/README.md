# Douyin Downloader — engine noi bo

Stack chay local 3 services (do `app/stackman.py` quan ly):

```
api (:8000)      engine/api/server.py  — resolve / download / jobs / images / user_posts
gallery (:8001)  engine/gallery/app.py — xem lai file da tai theo user
web (:8080)      engine/web/server.py  — reverse-proxy /api + /gallery + /files
```

Core tai: `engine/core/douyin.py` — viet moi 100% boi BDTG, chi dung
HTTP cong khai + cookie nguoi dung, khong phu thuoc tool ngoai.

## 1. Chay

Double-click **`start.bat`**, roi mo:

- Web: http://localhost:8080
- Gallery: http://localhost:8080/gallery/
- Files: http://localhost:8080/files/
- API: http://localhost:8000/api/v1/health

Tat: double-click **`stop.bat`**.

Venv engine (1 lan):

```bat
uv venv --python 3.11 engine\.venv
uv pip install --python engine\.venv\Scripts\python.exe -r engine\api\requirements.txt
```

## 2. Cookie Douyin (khi tai bao FAILED)

Douyin chan bot bang `msToken`/`ttwid`. Lay tu trinh duyet da dang nhap:

1. Mo douyin.com → F12 → Application → Cookies → `https://www.douyin.com`
2. Copy `ttwid`, `msToken`, `odin_tt`, `passport_csrf_token`
3. Dan vao `api/config.native.yml` muc `cookies:`, restart app

## 3. Gioi han that

- Link gia/mau (nhu `.../video/7123456789...`) se FAILED — phai dung link that.
- Khong cookie van resolve duoc mot so link public, nhung tai batch de bi chan.
- Chi tai video **cua chinh ban / duoc phep** — tu chiu trach nhiem ban quyen.
