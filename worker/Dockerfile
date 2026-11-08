# worker/Dockerfile: Lightweight container for pipeline shard workers
FROM python:3.11-slim

WORKDIR /app

COPY worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY prompts/ /app/prompts/
COPY data/ /app/data/
COPY worker/ /app/worker/

ENV PYTHONUNBUFFERED=1

CMD ["python", "/app/worker/worker.py"]

