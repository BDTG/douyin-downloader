# Douyin Downloader — Desktop App (Windows)

Tải video / ảnh Douyin chất lượng gốc, không watermark — app Windows chạy độc lập.

100% code bởi BDTG: UI Qt (PySide6) + engine Python nội bộ (`engine/core` + `engine/api`).
Dán link share → nhận diện → tải.

![Platform](https://img.shields.io/badge/platform-Windows-blue)
![Python](https://img.shields.io/badge/python-3.11-blue)
![UI](https://img.shields.io/badge/UI-PySide6-green)

## ✨ Tính năng

- **Dán cả đoạn share-text** → tự tách link, resolve ra tên / mô tả / độ phân giải /
  thời lượng / ngày đăng / nhạc / lượt xem-like-share
- **Nhãn chất lượng:** `4K / QHD / FHD / HD / SD` (theo cạnh ngắn) + thumbnail
- **Post ảnh:** dải ảnh `‹ ›` + checkbox → tải ảnh đang xem / đã chọn / tất cả (bản gốc)
- **Tải video gốc** — progress + tốc độ MB/s
- **Quét 1 acc:** liệt kê video, tick chọn từng video để tải
- **Tự quản stack:** mở app tự bật `api:8000 + gallery:8001 + web:8080`, thoát tự tắt
- **Nhật ký tải** giữ lại sau crash, mất job báo rõ để bấm Tải lại

## 🚀 Cài đặt (người dùng cuối)

Yêu cầu: Windows 10/11 64-bit. Không cần admin, không cần Python.

```bat
iscc installer.iss
installer\DouyinDownloader-Setup-1.0.0.exe
```

1. Chạy file Setup → Next → Finish
2. Lần đầu: điền cookie vào `<chỗ cài>\engine\api\config.native.yml` (mẫu tự tạo sẵn)
3. Mở lại app là dùng

> Nâng cấp / gỡ giữ nguyên `cookie + downloads`.

## 🛠 Chạy dev

```bat
:: 1. venv app Qt
uv venv --python 3.11 .venv
uv pip install --python .venv/Scripts/python.exe -r requirements.txt

:: 2. venv engine (1 lần)
uv venv --python 3.11 engine/.venv
uv pip install --python engine/.venv/Scripts/python.exe -r engine/api/requirements.txt

:: 3. cookie
copy engine\api\config.native.example.yml engine\api\config.native.yml

:: 4. chạy
.venv\Scripts\python.exe -m app
```

Build portable:

```bat
.venv\Scripts\pyinstaller.exe app.spec --noconfirm
dist\DouyinDownloader\DouyinDownloader.exe
```

## ⚙️ Cookie Douyin

Khi tải báo `FAILED` là do hết cookie:

1. Đăng nhập `douyin.com` → `F12 → Application → Cookies`
2. Copy `ttwid`, `msToken`, `odin_tt`, `passport_csrf_token`
3. Dán vào `engine/api/config.native.yml` → restart app

> Cookie là acc chính chủ, nằm ở stack dir, **không commit**.

## 🧭 Cách dùng

1. Copy đoạn share từ Douyin → dán vào app → **Nhận diện**
2. Xem thông tin + thumbnail → **Tải video** / **Tải ảnh**
3. Duyệt lại ở Gallery: http://localhost:8080/gallery/

| Service | Port | Chức năng |
|---------|------|-----------|
| api | `:8000` | resolve / download / jobs / images / user_posts |
| gallery | `:8001` | xem lại theo user |
| web | `:8080` | `/gallery/` + `/files/` |

## 🏗 Kiến trúc (100% BDTG)

```
app/ (PySide6)
 ├─ main.py      → UI trang duy nhất
 ├─ stackman.py  → bật/tắt stack local
 ├─ localapi.py  → gọi HTTP tới api:8000
 └─ views/       → DouyinPage (resolve/preview/tải)

engine/ (Python, không vendor ngoài)
 ├─ api/server.py  → FastAPI: resolve/download/jobs/images/user_posts/health
 ├─ core/douyin.py → client Douyin: tách link, resolve short, đọc detail, chọn bản gốc
 ├─ core/storage.py→ lưu downloads/<sec_uid>/<date>_<desc>_<aweme>/ + manifest.jsonl
 ├─ core/hanviet.py→ tên Hán-Việt offline
 ├─ gallery/       → xem lại theo user
 └─ web/           → reverse-proxy + files browser
```

Nguyên tắc core: chỉ dùng HTTP công khai + cookie người dùng, không dùng
chữ ký phức tạp, ưu tiên bản gốc không watermark.

## ✅ Test

```bat
.venv\Scripts\python.exe -m pytest tests/ -q
```

## ⚠️ Lưu ý

- Chỉ tải video **của chính bạn / được phép**.
- Tải lẻ vài link/ngày thì ổn, tải batch phải giãn cách 2-5s/trang tránh checkpoint.
- Tool phục vụ nghiên cứu, bạn tự chịu trách nhiệm bản quyền.
