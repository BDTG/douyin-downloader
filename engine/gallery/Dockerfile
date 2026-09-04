FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn
COPY app.py gallery.html .
ENV DL_DIR=/downloads DB_PATH=/downloads/dy_downloader.db
EXPOSE 8001
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
