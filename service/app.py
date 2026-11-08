"""service/app.py: FastAPI Inference Service for Command-Parsing Language Model.

Endpoints:
  - POST /parse: Extracts intent and slots from natural language command.
  - GET /healthz: Liveness probe endpoint.
  - GET /readyz: Readiness probe endpoint.
"""
import json
import os
import re
import socket
import sys
import time
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from pydantic import BaseModel
import torch

# Configuration from Environment Variables (strictly per specification)
MODEL_URI = os.environ.get("MODEL_URI", "models/v1")
MODEL_VERSION = os.environ.get("MODEL_VERSION", "v1")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://localhost:8333")
MAX_NEW_TOKENS = int(os.environ.get("MAX_NEW_TOKENS", "64"))
FAULT_INJECT = os.environ.get("FAULT_INJECT", "0")
POD_NAME = os.environ.get("HOSTNAME", socket.gethostname())

from service.validator import validate_and_extract_json, VALID_INTENTS, REQUIRED_KEYS

# Global model state
is_ready = False
model = None
tokenizer = None
device = "cpu"


def download_model_from_s3(model_uri: str, target_dir: str):
    """Downloads model files from SeaweedFS S3-compatible storage or copies local files."""
    os.makedirs(target_dir, exist_ok=True)
    
    # If model_uri is a local directory or relative path that exists
    if os.path.exists(model_uri) and any(os.scandir(model_uri)):
        print(f"Loading model directly from local directory: {model_uri}")
        return model_uri

    # Parse s3 URI: s3://bucket/path or bucket/path
    clean_uri = model_uri.replace("s3://", "")
    parts = clean_uri.split("/", 1)
    bucket = parts[0]
    prefix = parts[1] if len(parts) > 1 else ""

    try:
        import boto3
        from botocore.client import Config

        aws_key = os.environ.get("AWS_ACCESS_KEY_ID", "any")
        aws_secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "any")

        s3 = boto3.client(
            "s3",
            endpoint_url=S3_ENDPOINT,
            aws_access_key_id=aws_key,
            aws_secret_access_key=aws_secret,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1"
        )
        print(f"Connecting to S3 at {S3_ENDPOINT}, bucket={bucket}, prefix={prefix}")
        resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
        for obj in resp.get("Contents", []):
            key = obj["Key"]
            rel_path = os.path.relpath(key, prefix) if prefix else key
            dest = os.path.join(target_dir, rel_path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            print(f"Downloading {key} -> {dest}")
            s3.download_file(bucket, key, dest)
        return target_dir
    except Exception as e:
        print(f"S3 download encountered exception: {e}. Checking local fallback...", file=sys.stderr)
        if os.path.exists(model_uri):
            return model_uri
        return target_dir


@asynccontextmanager
async def lifespan(app: FastAPI):
    global is_ready, model, tokenizer
    print(f"Starting inference service pod {POD_NAME}, MODEL_VERSION={MODEL_VERSION}")
    target_dir = os.path.join("/tmp/model_cache", MODEL_VERSION)

    try:
        model_path = download_model_from_s3(MODEL_URI, target_dir)
        print(f"Loading PyTorch model and tokenizer from {model_path} on CPU...")

        from transformers import AutoModelForCausalLM, AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(model_path)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        model = AutoModelForCausalLM.from_pretrained(model_path)
        model.to(device)
        model.eval()

        # Warm up model
        test_input = tokenizer("Command: test\nJSON:", return_tensors="pt")
        with torch.no_grad():
            _ = model.generate(**test_input, max_new_tokens=10)

        is_ready = True
        print(f"Model successfully loaded and ready for inference!")
    except Exception as e:
        print(f"Failed to load model: {e}", file=sys.stderr)
        # Even if weights not yet available during test/mock, we keep is_ready=False until loaded
        is_ready = False

    yield
    print("Shutting down service.")


app = FastAPI(lifespan=lifespan)


class ParseRequest(BaseModel):
    text: str





@app.get("/healthz")
def healthz():
    """Liveness probe: returns HTTP 200 as long as the process is alive."""
    return Response(content="OK", status_code=status.HTTP_200_OK, media_type="text/plain")


@app.get("/readyz")
def readyz():
    """Readiness probe: returns HTTP 503 until model is loaded, HTTP 200 after that."""
    if is_ready:
        return Response(content="Ready", status_code=status.HTTP_200_OK, media_type="text/plain")
    return Response(content="Model Not Ready", status_code=status.HTTP_503_SERVICE_UNAVAILABLE, media_type="text/plain")


@app.post("/parse")
async def parse(request: ParseRequest):
    """POST /parse: Parses natural language text into 4-key JSON."""
    headers = {
        "X-Model-Version": MODEL_VERSION,
        "X-Served-By": POD_NAME,
        "Content-Type": "application/json"
    }

    # Check for FAULT_INJECT test mode
    current_fault_inject = os.environ.get("FAULT_INJECT", FAULT_INJECT)
    if str(current_fault_inject) == "1":
        raw_output = "not json"
    else:
        if not is_ready or model is None or tokenizer is None:
            return Response(
                content=json.dumps({"error": "model_not_ready"}),
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                headers=headers,
                media_type="application/json"
            )

        prompt = f"Command: {request.text}\nJSON:"
        inputs = tokenizer(prompt, return_tensors="pt").to(device)

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=MAX_NEW_TOKENS,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
                do_sample=False
            )

        generated_text = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
        raw_output = generated_text.strip()

    # Validate output against schema.json
    is_valid, parsed_obj = validate_and_extract_json(raw_output)

    if not is_valid:
        # Per specification: returns HTTP 500 with body {"error": "invalid_model_output"}
        return Response(
            content=json.dumps({"error": "invalid_model_output"}),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            headers=headers,
            media_type="application/json"
        )

    # Return exactly the 4-key JSON object and nothing else in the body
    output_body = {
        "intent": parsed_obj["intent"],
        "date": parsed_obj["date"],
        "time": parsed_obj["time"],
        "place": parsed_obj["place"],
    }

    return Response(
        content=json.dumps(output_body),
        status_code=status.HTTP_200_OK,
        headers=headers,
        media_type="application/json"
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
