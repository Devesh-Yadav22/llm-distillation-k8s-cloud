# service/Dockerfile: Lightweight container for inference service (< 2 GB)
FROM python:3.11-slim

WORKDIR /app

# Install pinned dependencies using CPU-only PyTorch to avoid bulky CUDA binaries
COPY service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip==24.0 && \
    pip install --no-cache-dir -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu

# Copy application code without any model weights
COPY service/app.py /app/app.py

EXPOSE 8000

ENV MODEL_URI=models/v1 \
    MODEL_VERSION=v1 \
    S3_ENDPOINT=http://seaweedfs.data.svc.cluster.local:8333 \
    MAX_NEW_TOKENS=64 \
    FAULT_INJECT=0 \
    PYTHONUNBUFFERED=1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

