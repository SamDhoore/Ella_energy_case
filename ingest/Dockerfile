FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY weather_ingest ./weather_ingest
# One-shot batch run by default; the `cron` compose service overrides this
# with `python -m weather_ingest.scheduler`.
CMD ["python", "-m", "weather_ingest.run"]
