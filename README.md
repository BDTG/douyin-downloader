# Douyin Downloader (standalone)

App tải video/ảnh Douyin chất lượng gốc theo user — chạy độc lập,
không cần framework. Engine Python trong `--stack-dir`,
UI Qt (PySide6) gọi thẳng HTTP, Gallery/Tracker/Files vẫn là web.

## Cài đặt (khuyên dùng)

```bat
iscc installer.iss
installer\DouyinDownloader-Setup-1.0.0.exe
```

Không cần admin. Installer gồm app Qt + engine Python + venv đóng gói sẵn
(khỏi pip install). Lần đầu: điền cookie vào
`<chỗ cài>\engine\api\config.native.yml` (mẫu tự tạo sẵn).
Nâng cấp giữ nguyên cookie + downloads. Đã test: cài lặng → api/web 200,
resolve ra Tiểu Nguyệt Nguyệt [QHD] → gỡ sạch.

## Chạy dev (không cài)

```bat
.venv\Scripts\pyinstaller.exe app.spec --noconfirm
dist\DouyinDownloader\DouyinDownloader.exe
```

Nháy đúp là chạy (tự bật stack, lỗi hiện hộp thoại). Lần đầu vẫn cần
2 venv + cookie như dưới.

```bat
:: 1. venv app
uv venv --python 3.11 .venv && uv pip install --python .venv/Scripts/python.exe -r requirements.txt
:: 2. venv engine (1 lần)
uv venv --python 3.11 engine/.venv && uv pip install --python engine/.venv/Scripts/python.exe -r engine/downloader/requirements.txt fastapi "uvicorn[standard]"
:: 3. cookie: copy engine/api/config.native.example.yml -> engine/api/config.native.yml, điền 5 keys
:: 4. chạy
.venv\Scripts\python.exe -m app
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
