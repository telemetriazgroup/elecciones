FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BASE_PATH=/elecciones \
    POLL_INTERVAL_SECONDS=60 \
    DATA_DIR=/app/data \
    VOTO_EXTRANJERO_ESTIMADO=350000 \
    VOTO_EXTRANJERO_KEIKO_PCT=65 \
    VOTO_EXTRANJERO_SANCHEZ_PCT=35

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY fetcher.py analysis.py history.py elecciones_2021.py app.py ./
COPY static/ ./static/

RUN mkdir -p /app/data

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/elecciones/api/health')" || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
