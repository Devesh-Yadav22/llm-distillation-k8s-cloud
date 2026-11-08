#!/usr/bin/env python3
"""training/train.py: Fine-tunes EleutherAI/pythia-70m using Sequence-Level Knowledge Distillation on CPU.

Reads hyperparameters from training/config.yaml.
Supports SUBSET flag (e.g. SUBSET=50 for quick verification).
Saves per-epoch training loss to training/loss.csv.
Saves model artifacts and generates model.sha256.
"""
import argparse
import csv
import hashlib
import json
import os
import random
import sys
import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset

try:
    import yaml
except ImportError:
    # Minimal fallback parser if pyyaml not installed
    class MinimalYaml:
        @staticmethod
        def safe_load(f):
            cfg = {}
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line:
                    k, v = line.split(":", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    try:
                        if "." in v:
                            v = float(v)
                        else:
                            v = int(v)
                    except ValueError:
                        pass
                    cfg[k] = v
            return cfg
    yaml = MinimalYaml()


def set_seed(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


class CommandDataset(Dataset):
    def __init__(self, records, tokenizer, max_length=128):
        self.examples = []
        for r in records:
            text = r["text"]
            # teacher_raw can be a dict or json string
            teacher_raw = r.get("teacher_raw", "")
            if isinstance(teacher_raw, dict):
                teacher_json = json.dumps(teacher_raw)
            else:
                teacher_json = str(teacher_raw).strip()

            formatted = f"Command: {text}\nJSON: {teacher_json}"
            enc = tokenizer(
                formatted,
                truncation=True,
                max_length=max_length,
                padding="max_length",
                return_tensors="pt"
            )
            input_ids = enc["input_ids"].squeeze(0)
            attention_mask = enc["attention_mask"].squeeze(0)
            labels = input_ids.clone()
            # Mask padding tokens in loss calculation
            labels[labels == tokenizer.pad_token_id] = -100

            self.examples.append({
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "labels": labels
            })

    def __len__(self):
        return len(self.examples)

    def __getitem__(self, idx):
        return self.examples[idx]


def compute_sha256_of_dir(dir_path: str, output_file: str):
    """Computes SHA256 checksums of all model files in directory."""
    records = []
    for root, _, files in os.walk(dir_path):
        for f in sorted(files):
            if f.endswith(".sha256"):
                continue
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, dir_path)
            h = hashlib.sha256()
            with open(full_path, "rb") as fh:
                while chunk := fh.read(65536):
                    h.update(chunk)
            records.append(f"{h.hexdigest()}  {rel_path}")

    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as out:
        out.write("\n".join(records) + "\n")
    print(f"Saved model checksums to {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Train Pythia-70M student model")
    parser.add_argument("--config", default="training/config.yaml", help="Path to config.yaml")
    parser.add_argument("--subset", type=int, default=None, help="Subset of training records to train on")
    parser.add_argument("--data", default="datasets/v1/train.jsonl", help="Path to train.jsonl")
    parser.add_argument("--output-dir", default=None, help="Output directory for trained model")
    parser.add_argument("--version", default="v1", help="Model version (v1 or v2)")
    args = parser.parse_args()

    # Check SUBSET env variable if not provided via CLI
    subset = args.subset
    if subset is None and "SUBSET" in os.environ:
        try:
            subset = int(os.environ["SUBSET"])
        except ValueError:
            pass

    with open(args.config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    seed = int(config.get("random_seed", 42))
    lr = float(config.get("learning_rate", 5e-4))
    batch_size = int(config.get("batch_size", 16))
    epochs = int(config.get("epochs", 3))
    max_seq_len = int(config.get("max_seq_length", 128))
    model_name = config.get("model_name", "EleutherAI/pythia-70m")

    # If training v2, optionally modify epoch or seed per specification
    if args.version == "v2":
        epochs = epochs + 1
        output_dir = "models/v2"
    else:
        output_dir = args.output_dir or config.get("output_dir", "models/v1")

    set_seed(seed)
    print(f"--- Training Configuration ---")
    print(f"Model: {model_name}, Seed: {seed}, Epochs: {epochs}, Batch size: {batch_size}, LR: {lr}")
    print(f"Version: {args.version}, Output Dir: {output_dir}, Subset: {subset}")

    # Load data
    if not os.path.exists(args.data):
        print(f"Error: {args.data} does not exist. Run worker/clean.py first.", file=sys.stderr)
        sys.exit(1)

    records = []
    with open(args.data, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    # Task rule: "Use no more than 1,500 training examples"
    records = records[:1500]
    if subset is not None:
        records = records[:subset]
        print(f"Running on SUBSET of {len(records)} examples for verification.")
    else:
        print(f"Training on {len(records)} examples.")

    from transformers import AutoModelForCausalLM, AutoTokenizer
    from torch.optim import AdamW

    print(f"Loading {model_name}...")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(model_name)
    model.train()

    dataset = CommandDataset(records, tokenizer, max_length=max_seq_len)
    dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

    optimizer = AdamW(model.parameters(), lr=lr, weight_decay=0.01)

    loss_history = []
    loss_csv_path = "training/loss.csv"
    os.makedirs(os.path.dirname(loss_csv_path) or ".", exist_ok=True)

    print("Beginning training on CPU...")
    for epoch in range(1, epochs + 1):
        total_loss = 0.0
        steps = 0
        for step, batch in enumerate(dataloader):
            input_ids = batch["input_ids"]
            attention_mask = batch["attention_mask"]
            labels = batch["labels"]

            outputs = model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                labels=labels
            )
            loss = outputs.loss
            loss.backward()

            optimizer.step()
            optimizer.zero_grad()

            total_loss += loss.item()
            steps += 1

        avg_loss = total_loss / max(1, steps)
        loss_history.append((epoch, avg_loss))
        print(f"Epoch {epoch}/{epochs} - Training Loss: {avg_loss:.4f}")

    # Save training loss to training/loss.csv per specification
    with open(loss_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["epoch", "loss"])
        for ep, l in loss_history:
            writer.writerow([ep, f"{l:.6f}"])
    print(f"Saved loss history to {loss_csv_path}")

    # Save model and tokenizer
    os.makedirs(output_dir, exist_ok=True)
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    print(f"Model and tokenizer saved to {output_dir}")

    # Checksum
    checksum_file = os.path.join(output_dir, "model.sha256")
    compute_sha256_of_dir(output_dir, checksum_file)


if __name__ == "__main__":
    main()

