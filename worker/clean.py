#!/usr/bin/env python3
"""worker/clean.py: Clean teacher-generated shards and generate datasets/v1/train.jsonl.

Cleaning rules:
  (a) replies that are not valid JSON
  (b) replies whose keys are not exactly intent, date, time, and place
  (c) replies whose intent is not one of the eight valid intents
  (d) replies with a slot value that is neither null nor text that appears in the command
  (e) duplicate commands (keep the one with the smallest id)

Satisfies: input = (a) + (b) + (c) + (d) + duplicates + kept
Saves SHA-256 checksum in datasets/v1/train.sha256
"""
import argparse
import glob
import hashlib
import json
import os
import sys

VALID_INTENTS = {
    "alarm_set",
    "alarm_query",
    "calendar_set",
    "calendar_query",
    "calendar_remove",
    "weather_query",
    "datetime_query",
    "recommendation_events",
}
REQUIRED_KEYS = {"intent", "date", "time", "place"}


def parse_args():
    parser = argparse.ArgumentParser(description="Clean teacher outputs and generate train.jsonl")
    parser.add_argument("--input-dir", default="datasets/teacher", help="Directory containing shard-*.jsonl files")
    parser.add_argument("--output-file", default="datasets/v1/train.jsonl", help="Output train.jsonl path")
    parser.add_argument("--checksum-file", default="datasets/v1/train.sha256", help="Output sha256 checksum path")
    parser.add_argument("--stats-file", default="results/cleaning_stats.json", help="Output cleaning stats JSON")
    return parser.parse_args()


def check_record(record):
    """Inspects a record. Returns (status, parsed_obj or None).
    status in ('ok', 'a', 'b', 'c', 'd')
    """
    raw = record.get("teacher_raw")
    if raw is None:
        return 'a', None

    if isinstance(raw, dict):
        parsed = raw
    else:
        try:
            parsed = json.loads(str(raw).strip())
        except (json.JSONDecodeError, TypeError):
            return 'a', None

    if not isinstance(parsed, dict):
        return 'a', None

    # (b) keys not exactly intent, date, time, and place
    if set(parsed.keys()) != REQUIRED_KEYS:
        return 'b', None

    # (c) intent not one of the eight
    intent = parsed.get("intent")
    if not isinstance(intent, str) or intent not in VALID_INTENTS:
        return 'c', None

    # (d) slot value neither null nor text that appears in command
    text = record.get("text", "")
    text_lower = text.lower()
    for slot in ("date", "time", "place"):
        val = parsed.get(slot)
        if val is None:
            continue
        if not isinstance(val, str):
            return 'd', None
        if val.strip().lower() not in text_lower:
            return 'd', None

    return 'ok', parsed


def main():
    args = parse_args()
    shard_files = sorted(glob.glob(os.path.join(args.input_dir, "shard-*.jsonl")))
    if not shard_files:
        # Fallback to current dir or check datasets/teacher
        shard_files = sorted(glob.glob("datasets/teacher/shard-*.jsonl"))

    if not shard_files:
        print(f"No shard files found in {args.input_dir}", file=sys.stderr)
        sys.exit(1)

    all_records = []
    seen_ids = set()
    for sf in shard_files:
        with open(sf, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    rec_id = rec.get("id")
                    if rec_id in seen_ids:
                        print(f"Warning: duplicate id {rec_id} found in shards", file=sys.stderr)
                    seen_ids.add(rec_id)
                    all_records.append(rec)
                except json.JSONDecodeError:
                    print(f"Error decoding JSON in {sf} line {line_no}", file=sys.stderr)

    total_input = len(all_records)
    print(f"Loaded {total_input} total records from {len(shard_files)} shards.")

    # Sort all records by id first to ensure consistent tie-breaking for duplicates
    all_records.sort(key=lambda r: r.get("id", ""))

    counts = {
        "input": total_input,
        "rejected_a_invalid_json": 0,
        "rejected_b_bad_keys": 0,
        "rejected_c_invalid_intent": 0,
        "rejected_d_slot_not_in_text": 0,
        "rejected_e_duplicate_command": 0,
        "kept": 0,
    }

    seen_commands = {}  # normalized text -> record id kept
    valid_records = []

    for rec in all_records:
        status, parsed = check_record(rec)
        if status == 'a':
            counts["rejected_a_invalid_json"] += 1
        elif status == 'b':
            counts["rejected_b_bad_keys"] += 1
        elif status == 'c':
            counts["rejected_c_invalid_intent"] += 1
        elif status == 'd':
            counts["rejected_d_slot_not_in_text"] += 1
        elif status == 'ok':
            # Check for duplicate command text
            norm_text = " ".join(rec.get("text", "").strip().lower().split())
            if norm_text in seen_commands:
                counts["rejected_e_duplicate_command"] += 1
            else:
                seen_commands[norm_text] = rec.get("id")
                # Keep compact canonical JSON for teacher_raw
                rec["teacher_raw"] = json.dumps(parsed, separators=(',', ':'))
                rec["parsed"] = parsed
                valid_records.append(rec)
                counts["kept"] += 1

    # Ensure records are strictly ordered by id
    valid_records.sort(key=lambda r: r.get("id", ""))

    # Verify partition invariant: input = (a) + (b) + (c) + (d) + duplicates + kept
    partition_sum = (
        counts["rejected_a_invalid_json"]
        + counts["rejected_b_bad_keys"]
        + counts["rejected_c_invalid_intent"]
        + counts["rejected_d_slot_not_in_text"]
        + counts["rejected_e_duplicate_command"]
        + counts["kept"]
    )
    assert partition_sum == counts["input"], f"Partition mismatch: sum={partition_sum} != input={counts['input']}"

    os.makedirs(os.path.dirname(args.output_file) or ".", exist_ok=True)
    with open(args.output_file, "w", encoding="utf-8") as out_f:
        for r in valid_records:
            clean_entry = {
                "id": r["id"],
                "text": r["text"],
                "teacher_raw": r["teacher_raw"]
            }
            out_f.write(json.dumps(clean_entry) + "\n")

    # Compute sha256 checksum of train.jsonl
    sha256 = hashlib.sha256()
    with open(args.output_file, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    digest = sha256.hexdigest()

    os.makedirs(os.path.dirname(args.checksum_file) or ".", exist_ok=True)
    with open(args.checksum_file, "w", encoding="utf-8") as f:
        f.write(f"{digest}  {os.path.basename(args.output_file)}\n")

    os.makedirs(os.path.dirname(args.stats_file) or ".", exist_ok=True)
    with open(args.stats_file, "w", encoding="utf-8") as f:
        json.dump(counts, f, indent=2)

    print(f"Cleaning complete.")
    print(f"Stats: {json.dumps(counts, indent=2)}")
    print(f"Saved {len(valid_records)} records to {args.output_file}")
    print(f"SHA256: {digest} -> {args.checksum_file}")


if __name__ == "__main__":
    main()

