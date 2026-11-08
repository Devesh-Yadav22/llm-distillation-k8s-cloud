.PHONY: all help up down train test clean clean-data build-images

# Default target
help:
	@echo "Available commands:"
	@echo "  make up               - Create k3d cluster and deploy all Kubernetes resources"
	@echo "  make down             - Tear down and delete local k3d cluster"
	@echo "  make train            - Train Pythia-70M student model (use SUBSET=50 for quick test)"
	@echo "  make test             - Run comprehensive test suite"
	@echo "  make clean-data       - Clean teacher shards and generate train.jsonl"
	@echo "  make build-images     - Build container images for worker and service"

# Task 6: make up builds and deploys whole system in at most three commands
up:
	k3d cluster create --config cluster/k3d.yaml
	kubectl apply -f k8s/seaweedfs.yaml -f k8s/secrets.yaml -f k8s/deployment.yaml -f k8s/service.yaml -f k8s/ingress.yaml -f k8s/hpa.yaml
	kubectl rollout status deployment/command-parser -n app --timeout=120s

# Task 6: make down deletes the cluster
down:
	k3d cluster delete cloud-cluster

# Task 2: reproducible training command reading training/config.yaml
train:
	python training/train.py --config training/config.yaml $(if $(SUBSET),--subset $(SUBSET),)

# Clean dataset from teacher shards
clean-data:
	python worker/clean.py --input-dir datasets/teacher --output-file datasets/v1/train.jsonl --checksum-file datasets/v1/train.sha256

# Build Docker images
build-images:
	docker build -t localhost:5001/pipeline-worker:latest -f worker/Dockerfile .
	docker build -t localhost:5001/command-parser:v1 -f service/Dockerfile .

# Run test suite
test:
	python -m unittest discover tests

