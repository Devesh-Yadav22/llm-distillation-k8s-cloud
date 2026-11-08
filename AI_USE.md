# AI Usage and Attribution Statement (`AI_USE.md`)

In accordance with the project guidelines ("You'll be using AI and no one can stop you. But do use it with your eyes wide open"), this document describes the artificial intelligence tools utilized during the design, development, and debugging of this project, the exact tasks they assisted with, and the verification methods used to audit and validate their outputs.

---

## 1. AI Tools Used

1. **Google DeepMind / Antigravity Agent (Gemini 3.8 Flash High)**
   - **Role**: Architectural assistant, code scaffolding, automated testing, and report structuring.
2. **Phi-3.5-mini-instruct (Teacher LLM, 3.8B parameters)**
   - **Role**: Knowledge distillation teacher model served via Ollama (`temperature=0.0`, `seed=42`) generating sequence-level training targets for the SLURP command dataset.

---

## 2. Tasks Assisted by AI and Verification Methods

| AI Tool | Task / Purpose | What the AI Generated | How It Was Checked & Verified |
| :--- | :--- | :--- | :--- |
| **Phi-3.5-mini-instruct** | Task 1: Teacher Labelling | Natural language command annotations into JSON (`intent`, `date`, `time`, `place`). | Verified programmatically through `worker/clean.py` enforcing strict JSON syntax, 8 canonical intents, verbatim slot matching against command substrings, and checksumming. Evaluated with `tools/score.py`. |
| **Antigravity AI Agent** | Task 5: Subnetting & NACL | IPv4 prefix math, CIDR block boundaries, and NACL JSON rules. | Formally verified by manual binary math ($2^{32-p}-2$) and tested against `network/packets_sample.jsonl` using `tools/nacl_sim.py --check` achieving 100.0% accuracy on all inbound and outbound rules. |
| **Antigravity AI Agent** | Task 3 & 4: Kubernetes Manifests & Dockerfile | Multi-stage Dockerfile with CPU-only wheels, Traefik Ingress routing, HPA configuration. | Tested locally with Docker build, inspected image layers with `docker image inspect` ensuring size $< 2$ GB, and verified probe endpoints (`/healthz`, `/readyz`). |
| **Antigravity AI Agent** | Task 6: Unit Testing Suite & CI/CD | `unittest` test cases in `tests/` covering schema validation, fault injection, and cleaning rules. | Executed all unit tests using `python -m unittest discover tests`, confirming 11/11 passing tests with zero dependencies. |
| **Antigravity AI Agent** | Report Generation & Cost Modeling | LaTeX / Markdown report synthesis, mathematical derivations for cost and error budgets. | Manually re-computed hourly rate formulas against `data/rate_card.json`, cross-checked latency percentiles, and verified that measured numbers matched Locust outputs. |

---

## 3. Human Critical Evaluation & Discoveries

1. **Hallucination Detection in Slot Extraction**: 
   When prompting the teacher model, generative LLMs occasionally canonicalize time expressions (e.g. converting *"seven in the evening"* to *"19:00"* or *"7:00 pm"*). Rule 1 of Section 4 explicitly forbids this. Our automated verification script (`worker/clean.py` Rule `d`) intercepted and filtered out records where extracted slot strings were not verbatim substrings of the original command text.

2. **Stateless NACL Bidirectional Traffic**:
   AI code generators often omit reply rules for ephemeral ports (`1024-65535`). By running `tools/nacl_sim.py`, we identified missing reverse return paths and added explicit rules for client responses and pod responses, ensuring complete bidirectional connectivity.

3. **PyTorch Docker Image Bloat**:
   Default `pip install torch` downloads GPU/CUDA libraries exceeding 3 GB. Applying human domain knowledge, we specified `--extra-index-url https://download.pytorch.org/whl/cpu` to ensure the final container remained under 1 GB, well within the 2 GB assignment limit.

