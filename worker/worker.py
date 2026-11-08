#!/usr/bin/env python3
"""worker/worker.py: Distributed shard worker for teacher labelling.

Processes commands where line_index % SHARD_COUNT == SHARD_INDEX.
Sends each command to the teacher model (phi3.5 via Ollama) and writes
{"id": "...", "text": "...", "teacher_raw": "<the teacher's exact reply>"}
to datasets/teacher/shard-<SHARD_INDEX>.jsonl.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

SHARD_INDEX = int(os.environ.get("SHARD_INDEX", "0"))
SHARD_COUNT = int(os.environ.get("SHARD_COUNT", "2"))
INPUT_FILE = os.environ.get("INPUT_FILE", "data/commands_pool.jsonl")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "datasets/teacher")
OUTPUT_FILE = os.environ.get("OUTPUT_FILE", os.path.join(OUTPUT_DIR, f"shard-{SHARD_INDEX}.jsonl"))
PROMPT_FILE = os.environ.get("PROMPT_FILE", "prompts/teacher_prompt.txt")
TEACHER_ENDPOINT = os.environ.get("TEACHER_ENDPOINT", "http://localhost:11434/api/generate")
MODEL_NAME = os.environ.get("TEACHER_MODEL", "phi3.5")


def load_prompt_template():
    if os.path.exists(PROMPT_FILE):
        with open(PROMPT_FILE, "r", encoding="utf-8") as f:
            return f.read()
    return "You are a command parser. Return valid JSON with intent, date, time, place.\nCommand: {command}"


def call_teacher(prompt_text):
    """Calls Ollama API with temperature 0 and seed 42 as required by specification."""
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt_text,
        "stream": False,
        "options": {
            "temperature": 0.0,
            "seed": 42
        }
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(TEACHER_ENDPOINT, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            res_obj = json.loads(resp.read().decode("utf-8"))
            return res_obj.get("response", "").strip()
    except Exception as e:
        print(f"Error querying teacher: {e}", file=sys.stderr)
        return ""


def main():
    print(f"Starting worker: SHARD_INDEX={SHARD_INDEX}, SHARD_COUNT={SHARD_COUNT}")
    prompt_template = load_prompt_template()

    if not os.path.exists(INPUT_FILE):
        print(f"Input file {INPUT_FILE} not found!", file=sys.stderr)
        sys.exit(1)

    os.makedirs(os.path.dirname(OUTPUT_FILE) or ".", exist_ok=True)

    with open(INPUT_FILE, "r", encoding="utf-8") as in_f:
        lines = in_f.readlines()

    my_commands = []
    for line_idx, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        if line_idx % SHARD_COUNT == SHARD_INDEX:
            rec = json.loads(line)
            my_commands.append((line_idx, rec))

    print(f"Assigned {len(my_commands)} commands out of {len(lines)} total lines.")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out_f:
        for idx, (line_idx, cmd) in enumerate(my_commands):
            cmd_id = cmd["id"]
            cmd_text = cmd["text"]
            full_prompt = prompt_template.replace("{command}", cmd_text)
            
            teacher_raw = call_teacher(full_prompt)
            
            output_entry = {
                "id": cmd_id,
                "text": cmd_text,
                "teacher_raw": teacher_raw
            }
            out_f.write(json.dumps(output_entry) + "\n")
            out_f.flush()

            if (idx + 1) % 50 == 0 or idx == len(my_commands) - 1:
                print(f"Worker {SHARD_INDEX}: Processed {idx + 1}/{len(my_commands)} commands.")

    print(f"Worker {SHARD_INDEX} complete. Results written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

