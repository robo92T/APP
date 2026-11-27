FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 1001 app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY frontend ./frontend
COPY deploy/start.py ./start.py
RUN mkdir -p /app/data && chown -R app:app /app/data
ENV BID_DB=/app/data/dochadzka.db \
    TZ=Europe/Bratislava \
    PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK CMD python -c "import os, urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/api/health')"
CMD ["python", "/app/start.py"]
