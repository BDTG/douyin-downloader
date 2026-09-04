# Stack engine (nằm ngoài repo này)

Mặc định: `D:/ThucTap/douyin-docker` (truyền `--stack-dir` để đổi).
Engine tách từ `jiji262/douyin-downloader`, vá thêm resolve/localinfo/ảnh chọn.

## Services (do `app/stackman.py` bật)

| Service | Port | Lệnh | Env |
|---|---|---|---|
| api | 8000 | `downloader/run.py -c api/config.native.yml --serve` | PYTHONIOENCODING=utf-8, PYTHONUTF8=1 |
| gallery | 8001 | `uvicorn app:app` (trong `gallery/`) | DL_DIR, ALIAS_PATH, SUBJECTS_PATH |
| web | 8080 | `web/server.py` | PYTHONIOENCODING=utf-8 |

## Endpoints api dùng trong app

- `POST /api/v1/resolve` {url} → aweme_id, author, desc, duration, WxH,
  quality (4K/QHD/FHD/HD/SD), date, play/tim/bl/share, music, cover_url,
  images[] (tối đa 35, bản gốc không watermark). Tự tách link từ share text.
- `POST /api/v1/download` {url} → {job_id} (tải bản gốc `original`)
- `GET /api/v1/jobs/{id}` → status + downloaded_bytes/total_bytes/current_aweme + error
- `POST /api/v1/download_images` {aweme_id, indices[]} → {saved[], failed[]}
- `POST /api/v1/localinfo` {path} → ffprobe file local
- `GET /api/v1/health` → {"status":"ok"}

## Files quan trọng trong stack dir

- `api/config.native.yml` — path Windows + db (KHÔNG commit)
- `api/config.yml` — cookie acc chính chủ (KHÔNG commit, KHÔNG share)
- `aliases.json` — code name (101739344, 1066193134, littlekycap)
- `subjects.json` — chính chủ: mặc định theo acc + riêng theo aweme
- `downloads/<sec_uid>/<date>_<desc>_<aweme>/` + `download_manifest.jsonl`
- Tier gallery: 1đ/file + 1đ/50MB (F0…SSSSS250, +100đ = +1S vô hạn)
