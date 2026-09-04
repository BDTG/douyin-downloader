FROM python:3.12-slim
WORKDIR /app
COPY downloader/requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends gcc ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt fastapi "uvicorn[standard]"
COPY downloader/ .
RUN mkdir -p /app/Downloaded
EXPOSE 8000
ENTRYPOINT ["python", "run.py"]
CMD ["-c", "/app/config.yml", "--serve", "--serve-host", "0.0.0.0", "--serve-port", "8000"]
