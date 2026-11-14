FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    HEALTHMON_AUTH_DB=/tmp/healthmon/astronaut_badges.sqlite3

WORKDIR /app

RUN groupadd --system healthmon \
    && useradd --system --gid healthmon --home-dir /app healthmon \
    && mkdir -p /tmp/healthmon \
    && chown healthmon:healthmon /tmp/healthmon

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY scripts/ ./scripts/
COPY src/ ./src/
COPY app/ ./app/
COPY models/ ./models/
COPY data/crew_profiles.json ./data/crew_profiles.json
COPY data/synthetic/crew_vitals_simulated.csv ./data/synthetic/crew_vitals_simulated.csv

RUN chown -R healthmon:healthmon /app
USER healthmon

EXPOSE 8000

CMD ["sh", "-c", "python scripts/serve_api.py --public-demo --host 0.0.0.0 --port \"${PORT:-8000}\" --secure-cookies"]
