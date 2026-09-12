FROM python:3.12-slim
WORKDIR /app
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY api/server.py ./server.py
COPY core/ ./core/
RUN mkdir -p /app/Downloaded
EXPOSE 8000
CMD ["python", "server.py", "-c", "/app/config.yml", "--host", "0.0.0.0", "--port", "8000"]
