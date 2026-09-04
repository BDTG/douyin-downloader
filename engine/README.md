# Douyin Tracker — Docker stack

Chạy trang tracker + API tải video Douyin (không watermark, chất lượng cao nhất) trong Docker.

## 1. Kiến trúc

```
web  (nginx, :8080)  →  tracker.html (DB + quét link + nút ⬇ Tải)
  ├─ /api/*  → proxy sang api:8000 (tránh lỗi CORS)
  └─ /files/ → duyệt file đã tải
gallery (python FastAPI, nội bộ) → grid xem video/ảnh theo user
  (lọc + tìm kiếm, đọc metadata từ SQLite dy_downloader.db)
  Code name: sửa `aliases.json` (key = sec_uid) rồi `docker compose restart gallery`.
  Thư mục downloads đặt theo sec_uid nên không vỡ khi tác giả đổi nickname.
api  (python + jiji262/douyin-downloader, :8000)
  ├─ POST /api/v1/download {"url":"..."} → {job_id}
  ├─ GET  /api/v1/jobs/{job_id}          → {status, success, failed, ...}
  └─ file tải về nằm ở ./downloads/ (mount chung cho cả 2 container)
```

## 2. Chạy

Double-click **`start.bat`** (hoặc `docker compose up -d --build`), rồi mở:

- Web tracker: http://localhost:8080
- Gallery xem video: http://localhost:8080/gallery/
- Files đã tải: http://localhost:8080/files/
- API trực tiếp: http://localhost:8000/api/v1/health

Tắt: double-click **`stop.bat`**.

## 3. Cookie Douyin (khi tải báo FAILED / chỉ tải được ~20 video)

Douyin chặn bot bằng `msToken`/`ttwid`. Lấy cookie từ trình duyệt đã đăng nhập Douyin:

1. Mở douyin.com → F12 → tab Application → Cookies → `https://www.douyin.com`
2. Copy giá trị `ttwid`, `msToken`, `odin_tt`, `passport_csrf_token`
3. Dán vào `api/config.yml` mục `cookies:`, rồi `docker compose restart api`

## 4. Vì sao ttget.com tải được chất lượng cao? (cơ chế, không phải phép màu)

Douyin trả về cho chính app/web của nó một JSON mô tả video (`aweme detail API`), trong đó có:

- `video.play_addr.url_list` — link MP4 **sạch, không watermark**
- `video.bit_rate[]` — thang chất lượng (bitrate thấp → cao)

Các trang như ttget và tool open source trong stack này (`downloader/`, MIT license)
làm đúng 3 bước đó: gọi aweme API → chọn bitrate cao nhất → tải file MP4 từ CDN
của Douyin về. Điểm khác nhau giữa các tool chỉ là cách vượt kiểm soát bot
(cookie/signature) và độ ổn định khi Douyin đổi API.

Tool open source đã khảo sát:

| Tool | Nhận xét |
|---|---|
| `jiji262/douyin-downloader` (đang dùng) | Còn maintain (2026), video/note/collection/user-batch, server mode, SQLite, có Dockerfile |
| `Evil0ctal/Douyin_TikTok_Download_API` | Phổ biến, FastAPI + web portal — phương án dự phòng |
| `yt-dlp` | Hỗ trợ Douyin chập chờn (issue #9557), không nên làm nguồn chính |
| `lzdyes/douyin-downloader` | App Tauri, ngừng update từ 2023 |

## 5. Giới hạn thật

- Link video **giả/mẫu** (như `.../video/7123456789...`) tải sẽ FAILED — phải dùng link thật.
- Không cookie thì vẫn tải được video public đơn lẻ, nhưng batch user dễ bị chặn phân trang.
- Chỉ tải video **của chính bạn / được phép** — tool ghi rõ mục đích nghiên cứu, tự chịu trách nhiệm bản quyền.
