# Douyin Downloader (standalone)

App tải video/ảnh Douyin chất lượng gốc theo user — chạy độc lập,
không cần framework. Engine Python trong `--stack-dir`,
UI Qt (PySide6) gọi thẳng HTTP, Gallery/Tracker/Files vẫn là web.

## Chạy

```bat
:: venv: uv venv --python 3.11 .venv && uv pip install --python .venv/Scripts/python.exe -r requirements.txt
.venv\Scripts\python.exe -m app --stack-dir D:\ThucTap\douyin-docker
```

Mở app là tự bật stack (api:8000/gallery:8001/web:8080, port bận thì dùng luôn),
thoát app là dừng process mình bật. Gallery: http://localhost:8080/gallery/

## Tính năng (trang duy nhất)

- Dán cả đoạn share text → Nhận diện: tên/code/mô tả/spec + nhãn quality
  (4K/QHD/FHD/HD/SD) + thumbnail + dải ảnh post gallery (‹ › + checkbox)
- Tải video (thanh bar + MB/s), tải ảnh này / đã chọn / tất cả ảnh gốc
- Job mất (api restart) thì báo bấm Tải lại, không đơ

## Test

```bat
.venv\Scripts\python.exe -m pytest tests/ -q
```

## Ghi chú

- Cookie acc chính chủ nằm ở stack dir (`api/config.yml`), không commit.
- Tải lẻ vài link/ngày; tải hàng loạt phải cách quãng tránh checkpoint.
