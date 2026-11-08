# Knowledge Distillation & Cloud Deployment of Lightweight Command-Parsing Language Model

**Course**: CS3081 Cloud Computing Mini Project  
**Author**: Devesh Yadav  
**GitHub Repository**: [https://github.com/Devesh-Yadav22/llm-distillation-k8s-cloud](https://github.com/Devesh-Yadav22/llm-distillation-k8s-cloud)  

---

## 1. Project Overview

This project implements sequence-level knowledge distillation and cloud-native Kubernetes deployment for a voice assistant natural language command parser. A 3.8-billion parameter teacher language model (**Phi-3.5-mini-instruct**) generates structured intent and slot parsing targets across 3,000 commands from the SLURP dataset. These outputs are cleaned, validated against strict four-key JSON schema rules, and used to fine-tune a compact 70-million parameter causal language model (**EleutherAI/pythia-70m**) entirely on CPU hardware.

The trained student model is packaged into a containerized microservice (< 2 GB) with health and readiness probes, deployed to a local Kubernetes (`k3d`) cluster, scaled via Horizontal Pod Autoscaler (HPA), and exposed through a Traefik Ingress controller.

---

## 2. Directory Structure

```text
cloud_assignment/
├── cluster/
│   └── k3d.yaml                  # k3d cluster config with port 8080:80 mapping
├── data/
│   ├── commands_pool.jsonl       # 3,000 raw SLURP voice assistant commands
│   ├── validation.jsonl          # 100 gold-labelled validation commands
│   ├── schema.json               # 4-key JSON schema and slot extraction rules
│   └── rate_card.json            # Resource billing rates for cost analysis
├── datasets/
│   ├── teacher/                  # Sharded raw outputs from teacher model
│   │   ├── shard-0.jsonl
│   │   └── shard-1.jsonl
│   └── v1/
│       ├── train.jsonl           # 2,854 cleaned training records
│       └── train.sha256          # SHA-256 integrity checksum
├── k8s/
│   ├── seaweedfs.yaml            # SeaweedFS S3-compatible object storage
│   ├── secrets.yaml              # Kubernetes S3 access credentials
│   ├── pipeline.yaml             # Parallel shard worker batch jobs
│   ├── deployment.yaml           # Command parser rolling-update deployment
│   ├── service.yaml              # ClusterIP service on port 8000
│   ├── ingress.yaml              # Traefik Ingress routing /parse
│   └── hpa.yaml                  # Horizontal Pod Autoscaler (1-2 replicas, 70% CPU)
├── models/
│   ├── v1/                       # Distilled student model (v1) & checksums
│   └── v2/                       # Distilled student model (v2) for rolling updates
├── network/
│   ├── nacl.json                 # Stateless Network Access Control List rules
│   ├── packets_sample.jsonl      # Test packet suite for NACL simulation
│   └── subnets.md                # Subnetting derivations, tables, and reasoning
├── prompts/
│   └── teacher_prompt.txt        # System prompt for teacher model (Phi-3.5)
├── report/
│   └── report.pdf                # 8-page comprehensive technical report
├── results/
│   ├── cleaning_stats.json       # Record breakdown from worker/clean.py
│   ├── teacher_validation.json   # Teacher model accuracy metrics on validation set
│   ├── untrained_validation.json # Baseline untrained Pythia-70M validation report
│   ├── student_validation.json   # Distilled student validation report (Quality Gate)
│   ├── loadtest_stats.csv        # Locust 2-minute load test summary statistics
│   ├── loadtest_headers.json     # Request distribution across replicas & versions
│   ├── cold_start_logs.txt       # Cold-start timeline across 3 runs
│   ├── hpa_scaling.txt           # Autoscaler event logs under load
│   ├── rolling_update_recovery.txt# Zero-downtime rolling update & pod recovery logs
│   └── peak_memory_test.txt      # 50-request memory profile under 1 CPU / 1 GiB limit
├── service/
│   ├── app.py                    # FastAPI inference service (/parse, /healthz, /readyz)
│   ├── validator.py              # Zero-dependency schema & fault-injection validator
│   ├── Dockerfile                # Docker container with CPU-only PyTorch (< 2 GB)
│   └── requirements.txt          # Pinned Python package dependencies
├── tests/
│   ├── test_clean_rules.py       # Unit tests for cleaning filters (a)-(e)
│   ├── test_service_validation.py# Unit tests for FastAPI validator & fault injection
│   └── test_nacl_stateless.py    # Unit tests for NACL simulation rules
├── tools/
│   ├── locustfile.py             # Locust load test harness tracking response headers
│   ├── nacl_sim.py               # Stateless NACL evaluator
│   └── score.py                  # Evaluation scoring tool with --min-validity gate
├── training/
│   ├── config.yaml               # Pinned hyperparameters & library versions
│   ├── train.py                  # PyTorch student distillation training script
│   ├── evaluate.py               # Validation scoring automation script
│   └── loss.csv                  # Per-epoch training loss records
├── .github/
│   └── workflows/ci.yml          # CI/CD pipeline: Gitleaks, Lint, Test, Eval & Gate
├── Makefile                      # Automated make up, down, train, test targets
├── AI_USE.md                     # Disclosure of AI tools, verification, and human audit
└── README.md                     # Project documentation and reproduction guide
```

---

## 3. Quick Start Commands

The entire environment can be built, trained, tested, deployed, and destroyed using `make`:

```bash
# 1. Run unit tests across all components
make test

# 2. Clean dataset shards and compute train.sha256
make clean-data

# 3. Train Pythia-70M student model on CPU (SUBSET=50 for quick sanity check)
make train SUBSET=50

# 4. Spin up k3d cluster and deploy all Kubernetes workloads
make up

# 5. Tear down the cluster and clean up resources
make down
```

---

## 4. Step-by-Step Task Reproduction

### Task 1: Object Storage and Parallel Teacher Labelling
1. Launch local Kubernetes cluster:
   ```bash
   k3d cluster create --config cluster/k3d.yaml
   ```
2. Deploy SeaweedFS S3-compatible storage in namespace `data`:
   ```bash
   kubectl apply -f k8s/seaweedfs.yaml
   ```
3. Run parallel shard workers in namespace `pipeline`:
   ```bash
   kubectl apply -f k8s/pipeline.yaml
   ```
4. Run dataset cleaning script:
   ```bash
   python worker/clean.py --input-dir datasets/teacher --output-file datasets/v1/train.jsonl
   ```
   **Result**: 3,000 raw inputs $\rightarrow$ 2,854 kept clean records, satisfying $3000 = 25 (a) + 20 (b) + 20 (c) + 31 (d) + 50 (duplicates) + 2854 (kept)$.

---

### Task 2: Student Model Distillation (Pythia-70M)
1. Verify hyperparameters in `training/config.yaml`:
   - `model_name`: `EleutherAI/pythia-70m`
   - `learning_rate`: `0.0005`, `batch_size`: `16`, `epochs`: `3`, `seed`: `42`
2. Train model:
   ```bash
   python training/train.py --config training/config.yaml
   ```
3. Verify evaluation results against `data/validation.jsonl`:
   ```bash
   python tools/score.py results/student_raw.jsonl data/validation.jsonl --min-validity 95
   ```
   **Student Results**: JSON validity: **99.0%**, Full-frame accuracy: **78.0%**.

---

### Task 3: Containerized Inference Service
1. Build the lightweight Docker image:
   ```bash
   docker build -t localhost:5001/command-parser:v1 -f service/Dockerfile .
   ```
2. Verify image size is under 2 GB:
   ```bash
   docker images localhost:5001/command-parser:v1
   # Observed size: ~980 MB
   ```
3. Test Fault Injection:
   ```bash
   docker run -d -p 8000:8000 -e FAULT_INJECT=1 localhost:5001/command-parser:v1
   curl -i -X POST http://localhost:8000/parse -H "Content-Type: application/json" -d '{"text": "set alarm"}'
   # Returns: HTTP 500 {"error": "invalid_model_output"}
   ```

---

### Task 4: Kubernetes Deployment, Autoscaling & Resilience
1. Apply app manifests:
   ```bash
   kubectl apply -f k8s/secrets.yaml -f k8s/deployment.yaml -f k8s/service.yaml -f k8s/ingress.yaml -f k8s/hpa.yaml
   ```
2. Run Locust load test:
   ```bash
   locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 --run-time 2m --host http://localhost:8080 --csv results/loadtest
   ```
3. Test Zero-Downtime Rolling Update to v2:
   ```bash
   kubectl set env deployment/command-parser MODEL_VERSION=v2 MODEL_URI=s3://models/v2 -n app
   kubectl rollout status deployment/command-parser -n app
   kubectl rollout undo deployment/command-parser -n app
   ```

---

### Task 5: Subnetting and Stateless NACL
1. Review subnetting derivations in `network/subnets.md`.
2. Validate stateless NACL rules against packet samples:
   ```bash
   python tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check
   # Correct: 6 / 6 = 100.0%
   ```

---

### Task 6: Testing & CI/CD
1. Run local test suite:
   ```bash
   python -m unittest discover tests
   ```
2. Review `.github/workflows/ci.yml` for linting, testing, model release evaluation, quality gate, and Gitleaks scanning.

---

### Task 7: Performance & Cost Analysis
- **Throughput**: $8.53\text{ req/s}$ ($30,708\text{ requests/hour}$)
- **Latency**: Median (p50) = $320\text{ ms}$, 95th Percentile (p95) = $590\text{ ms}$
- **Error Rate**: $0.29\%$ (3 failures out of 1,024 requests, well below the 1.0% limit)
- **Cost**: ₹0.26 per 1,000 requests using `data/rate_card.json`.
- **SLO**: 99.0% success target over a 2-minute window (Error budget = 10.2 requests; 3 consumed = 29.4% budget used).
