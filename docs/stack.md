# Stack engine noi bo (BDTG) — khong phu thuoc vendor ngoai.

Mac dinh: `engine/` trong repo (truyen `--stack-dir` de doi).

## Services (do `app/stackman.py` bat)

| Service | Port | Lenh | Env |
|---|---|---|---|
| api | 8000 | `api/server.py -c api/config.native.yml --host 127.0.0.1 --port 8000` | PYTHONIOENCODING=utf-8, PYTHONUTF8=1 |
| gallery | 8001 | `uvicorn app:app` (trong `gallery/`) | DL_DIR, ALIAS_PATH, SUBJECTS_PATH |
| web | 8080 | `web/server.py` | PYTHONIOENCODING=utf-8 |

Core tai nam o `engine/core/douyin.py` (viet moi 100%): HTTP cong khai +
cookie nguoi dung, khong dung chu ky phuc tap.

## Endpoints api dung trong app

- `POST /api/v1/resolve` {url} → aweme_id, author, desc, duration, WxH,
  quality (4K/QHD/FHD/HD/SD), date, play/tim/bl/share, music, cover_url,
  images[] (tối đa 35, bản gốc không watermark). Tự tách link từ share text.
- `POST /api/v1/download` {url} → {job_id} (tải bản gốc)
- `GET /api/v1/jobs/{id}` → status + downloaded_bytes/total_bytes/current_aweme + error
- `POST /api/v1/download_images` {aweme_id, indices[]} → {saved[], failed[]}
- `POST /api/v1/localinfo` {path} → thong tin file local (ffprobe neu co)
- `POST /api/v1/user_posts` {sec_uid, cursor, count} → danh sach video 1 acc
- `POST /api/v1/mix_posts` {mix_id|url, cursor, count} → danh sach video 1 collection
- `GET /api/v1/videsc?text=` → dich Trung-Viet (Gemini, co cache)
- `GET /api/v1/viname?name=` → ten Han-Viet offline
- `GET /api/v1/health` → {"status":"ok"}

## Files quan trọng trong stack dir

- `api/config.native.yml` — path Windows + cookie (KHÔNG commit)
- `aliases.json` — code name (sec_uid -> code hien thi o gallery)
- `subjects.json` — chinh chu: mac dinh theo acc + rieng theo aweme
- `downloads/<sec_uid>/<date>_<desc>_<aweme>/` + `download_manifest.jsonl`
- Tier gallery: 1đ/file + 1đ/50MB (F0…SSSSS250, +100đ = +1S vô hạn)
