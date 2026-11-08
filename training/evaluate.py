#!/usr/bin/env python3
"""training/evaluate.py: Evaluates models on data/validation.jsonl and generates score reports.

Supported models:
  - teacher: Calls teacher model (or uses pre-computed teacher responses)
  - untrained: EleutherAI/pythia-70m base model
  - student: Fine-tuned student checkpoint (models/v1)
"""
import argparse
import json
import os
import subprocess
import sys
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

VALIDATION_FILE = "data/validation.jsonl"
SCHEMA_FILE = "data/schema.json"


def evaluate_causal_lm(model_path: str, val_records, output_raw: str, max_new_tokens=64):
    print(f"Loading model and tokenizer from {model_path}...")
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(model_path)
    model.eval()

    predictions = []
    print(f"Generating predictions for {len(val_records)} validation samples...")
    for idx, rec in enumerate(val_records):
        prompt = f"Command: {rec['text']}\nJSON:"
        inputs = tokenizer(prompt, return_tensors="pt")

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
                do_sample=False
            )

        gen_text = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()
        predictions.append({
            "id": rec["id"],
            "prediction": gen_text
        })

        if (idx + 1) % 25 == 0:
            print(f"Progress: {idx + 1}/{len(val_records)}")

    os.makedirs(os.path.dirname(output_raw) or ".", exist_ok=True)
    with open(output_raw, "w", encoding="utf-8") as f:
        for p in predictions:
            f.write(json.dumps(p) + "\n")
    print(f"Saved raw predictions to {output_raw}")


def run_score(predictions_path: str, report_out: str, min_validity=None):
    cmd = [
        sys.executable,
        "tools/score.py",
        predictions_path,
        VALIDATION_FILE,
        "--out",
        report_out
    ]
    if min_validity is not None:
        cmd.extend(["--min-validity", str(min_validity)])

    print(f"Running score: {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True)
    print(res.stdout)
    if res.stderr:
        print(res.stderr, file=sys.stderr)
    return res.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="Evaluate model on validation.jsonl")
    parser.add_argument("--mode", choices=["student", "untrained", "teacher"], required=True)
    parser.add_argument("--model-path", default=None)
    parser.add_argument("--out-raw", default=None)
    parser.add_argument("--out-report", default=None)
    parser.add_argument("--min-validity", type=float, default=None)
    args = parser.parse_args()

    with open(VALIDATION_FILE, "r", encoding="utf-8") as f:
        val_records = [json.loads(line) for line in f if line.strip()]

    if args.mode == "student":
        model_path = args.model_path or "models/v1"
        out_raw = args.out_raw or "results/student_raw.jsonl"
        out_report = args.out_report or "results/student_validation.json"
        evaluate_causal_lm(model_path, val_records, out_raw)
        run_score(out_raw, out_report, args.min_validity)

    elif args.mode == "untrained":
        model_path = args.model_path or "EleutherAI/pythia-70m"
        out_raw = args.out_raw or "results/untrained_raw.jsonl"
        out_report = args.out_report or "results/untrained_validation.json"
        evaluate_causal_lm(model_path, val_records, out_raw)
        run_score(out_raw, out_report)

    elif args.mode == "teacher":
        out_raw = args.out_raw or "results/teacher_raw.jsonl"
        out_report = args.out_report or "results/teacher_validation.json"
        # If raw predictions already exist, score them
        if os.path.exists(out_raw):
            run_score(out_raw, out_report)
        else:
            print("Generating teacher predictions requires Ollama with phi3.5 running.", file=sys.stderr)


if __name__ == "__main__":
    main()

