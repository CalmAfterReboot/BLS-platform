# Project 4 — BLS LLM Gateway

## What This Project Does

This project builds a private API gateway that lets you send a question to a large language
model (an AI that generates text) and get a response back — using the same format that
OpenAI's ChatGPT API uses. That means any tool that already talks to ChatGPT can be pointed
at this gateway instead, with no changes to the tool itself.

The gateway is self-hosted. The AI models run on hardware you own, not on a cloud provider's
servers. This matters for cost (no per-token billing), privacy (your prompts never leave your
network), and control (you decide which models are available and to whom).

In the BLS portfolio, this is Project 4. The first three projects established the
infrastructure: an Azure landing zone, a Kubernetes cluster running on Proxmox hardware,
and a GitOps pipeline that automatically deploys software when you push changes to GitHub.
Project 4 uses all three of those to ship a real, working application on top of that
infrastructure.

The practical result: a URL inside the homelab network that accepts authenticated API calls,
routes them to locally-running AI models, and returns responses. Any developer who has an
API key can use it without knowing or caring about what runs underneath.

---

## Architecture

The gateway is made of four components. Here is what each one does and why it is here.

### FastAPI

FastAPI is a Python framework for building APIs. It is the front door of this system. Every
request that comes in hits FastAPI first. FastAPI's job in this project is authentication:
it checks that the caller has a valid API key before passing the request on. It does not run
any AI — it just checks credentials and forwards traffic.

FastAPI was chosen because it is fast, it generates interactive documentation automatically
at `/docs`, and it handles concurrent requests well without complex configuration.

### LiteLLM

LiteLLM is a proxy that speaks many AI model dialects. Different AI providers (OpenAI,
Anthropic, Ollama, etc.) all have slightly different API formats. LiteLLM normalises all of
them behind one standard interface — the OpenAI format.

LiteLLM can be used in two ways. **SDK mode** means you import it as a Python library
and call it from inside your own code. **Proxy mode** means you run it as a standalone
HTTP server and point your code at it with a URL. This project uses **proxy mode**.

Proxy mode was chosen because it keeps LiteLLM's concerns completely separate from the
FastAPI gateway's concerns. LiteLLM handles model routing, retries, and response caching.
FastAPI handles authentication. Neither component needs to know about the internals of the
other. If you want to swap out LiteLLM for a different routing layer later, you change one
URL in an environment variable and the FastAPI code is untouched.

### Redis

Redis is an in-memory data store. Here it is configured as a response cache for LiteLLM.
When someone asks "what is the capital of France?", LiteLLM can return the cached answer
from Redis instead of sending the same question to Ollama again.

Redis is included now even though semantic caching (which would actually use it) is not
configured yet. The reason is that wiring it in at the start is a five-minute job. Wiring it
in later, after the rest of the stack is stable, is a potential disruption. The cache TTL is
set to 3600 seconds (one hour). The cost of running a Redis pod with 64Mi of RAM is
negligible.

### Ollama

Ollama is a tool for running open-source AI models locally. It downloads models, manages
their memory, and exposes an HTTP API for sending prompts and getting responses. The models
(llama3.2, mistral, deepseek-r1) are the actual AI — Ollama is the runtime that loads and
serves them.

Ollama runs directly on the Proxmox host machine, not inside the Kubernetes cluster. The
reason is GPU and RAM access. Kubernetes containerises workloads and imposes resource
boundaries. A model like deepseek-r1 needs direct, low-latency access to system RAM (or a
GPU if one is present). Running Ollama inside a container adds overhead and complexity for
no benefit when the Proxmox host is dedicated hardware under your control.

The Proxmox host is reachable from the Kubernetes cluster at `10.212.46.5:11434`. That
address is the Proxmox node's LAN IP. LiteLLM is configured with that endpoint, so when
it needs to run a model it makes an HTTP call across the local network to Ollama.

### Request Flow

```
User request
  → FastAPI on port 8000 (check Bearer token against BLS_API_KEYS)
  → LiteLLM on port 4000 (select model, check Redis cache, route request)
  → Ollama on Proxmox at 10.212.46.5:11434 (run inference)
  → response travels back through LiteLLM → FastAPI → caller
```

A request that fails authentication at the FastAPI layer never reaches LiteLLM. A request
for a cached result never reaches Ollama. A request that times out at the Ollama layer
returns a 504 to the caller with the message "Backend timeout — model may be loading."

---

## Repository Structure

The project lives in two places in the repository. `04-llm-gateway/` is the working
directory where development happens. `k8s/workloads/llm-gateway/` is the GitOps path that
ArgoCD watches. They are kept in sync — any change to `04-llm-gateway/` is mirrored to
`k8s/workloads/llm-gateway/` as part of the same commit.

```
04-llm-gateway/
├── Chart.yaml                          # Helm chart metadata (name, version, description)
├── values.yaml                         # Default configuration values for k3s homelab
├── values-aks.yaml                     # Override values for Azure AKS deployment
├── argocd-app.yaml                     # ArgoCD Application manifest (GitOps registration)
├── app/
│   ├── Dockerfile                      # Build instructions for the FastAPI container image
│   ├── .dockerignore                   # Files excluded from the Docker build context
│   ├── .gitignore                      # Prevents Python bytecode from being committed
│   ├── main.py                         # FastAPI app entrypoint — wires together all middleware and routers
│   ├── middleware/
│   │   ├── auth.py                     # API key authentication middleware
│   │   └── .gitkeep                    # Keeps the directory tracked by git when otherwise empty
│   └── routers/
│       ├── completions.py              # /v1/chat/completions route — proxies requests to LiteLLM
│       └── .gitkeep                    # Keeps the directory tracked by git when otherwise empty
└── templates/
    ├── configmap-litellm.yaml          # LiteLLM configuration file, mounted into the litellm container
    ├── deployment-gateway.yaml         # Kubernetes Deployment for the FastAPI gateway container
    ├── deployment-litellm.yaml         # Kubernetes Deployment for the LiteLLM proxy container
    ├── deployment-redis.yaml           # Kubernetes Deployment for the Redis cache container
    ├── service-gateway.yaml            # Internal DNS name for the FastAPI gateway (ClusterIP)
    ├── service-litellm.yaml            # Internal DNS name for LiteLLM (ClusterIP)
    ├── service-redis.yaml              # Internal DNS name for Redis (ClusterIP)
    ├── ingress.yaml                    # Traefik ingress rule — exposes the gateway at llm-gateway.local
    ├── secret.yaml                     # Bootstrap Secret with placeholder API keys (temporary — see Known Gaps)
    └── .gitkeep                        # Keeps the directory tracked by git when otherwise empty
```

`k8s/workloads/llm-gateway/` has an identical structure minus `argocd-app.yaml` (which is
applied once manually to register the application; it does not need to live in the watched
path).

---

## Infrastructure

### The k3s Cluster

The Kubernetes cluster runs k3s, a lightweight Kubernetes distribution. It is deployed on
five virtual machines hosted on a Proxmox hypervisor:

- Three control plane nodes (the brain of the cluster — they manage state and scheduling)
- Two worker nodes (where application pods actually run)

The cluster has a Virtual IP (VIP) at `192.168.200.5` managed by kube-vip. This means the
cluster is reachable at one stable address even if an individual control plane node goes
down. `kubectl` and external tools connect through this VIP.

### Ollama on Proxmox

Ollama runs directly on the Proxmox host at IP `10.212.46.5`, not inside any virtual
machine or container. It listens on port `11434`. The Proxmox host has direct access to all
physical RAM on the machine, which is what large language models need. Running Ollama inside
a k3s pod would require configuring resource limits, volume mounts for model storage, and
node affinity rules — all to end up with worse performance than running it natively.

The Ollama endpoint `http://10.212.46.5:11434` is stored in `values.yaml` under
`proxmox.ollamaEndpoint` and injected into the LiteLLM ConfigMap at deploy time via Helm
templating.

### GitOps with ArgoCD

ArgoCD is a tool that runs inside Kubernetes and watches a Git repository. When the contents
of a watched path change, ArgoCD automatically applies those changes to the cluster. This
pattern is called GitOps: Git is the single source of truth for what should be running, and
the cluster continuously reconciles itself toward that state.

In practice this means: edit a YAML file, push to GitHub, and within seconds ArgoCD has
applied the change to the cluster. You do not `kubectl apply` anything manually once
ArgoCD is managing a workload.

The ArgoCD Application manifest (`argocd-app.yaml`) is applied once with:

```bash
kubectl apply -f 04-llm-gateway/argocd-app.yaml
```

After that, every push to `k8s/workloads/llm-gateway/` on the `main` branch is
automatically deployed. The `prune: true` flag means resources deleted from Git are also
deleted from the cluster. The `selfHeal: true` flag means if someone manually changes
something in the cluster, ArgoCD reverts it to match Git within minutes.

### Full Automation Chain

Here is what happens from a file change to a running pod:

1. You edit a file under `k8s/workloads/llm-gateway/` and push to `main` on GitHub.
2. If the change is under `k8s/workloads/llm-gateway/app/**`, the GitHub Actions workflow
   in `.github/workflows/build-gateway.yaml` triggers and builds a new container image.
3. The new image is pushed to GHCR (GitHub Container Registry) with two tags: `:latest`
   and `:<git-sha>`.
4. ArgoCD polls the repository every 3 minutes (or is notified via webhook). It detects
   that the Helm chart has changed.
5. ArgoCD runs `helm template` against the updated chart and applies the resulting YAML to
   the cluster.
6. Kubernetes pulls the new container image and performs a rolling update, replacing pods
   one at a time so the service stays available.

---

## Build Process — Step by Step

### Phase 1 — Scaffold

**Commit:** `6356110 feat(p4): scaffold llm-gateway helm chart structure`

The first commit created the directory structure and `Chart.yaml`. A Helm chart is a
packaged Kubernetes application. The chart structure — a `Chart.yaml` metadata file, a
`values.yaml` configuration file, and a `templates/` directory — is Helm's required
layout. Starting with the scaffold before writing any application code ensures the
deployment mechanism is defined from the start, not retrofitted later.

`Chart.yaml` identifies the chart:

```yaml
apiVersion: v2
name: llm-gateway
description: BLS LLM Gateway — FastAPI + LiteLLM + Redis
type: application
version: 0.1.0
appVersion: "0.1.0"
```

`values.yaml` was populated with all four components (gateway, litellm, redis) and their
resource limits upfront, so every subsequent template could reference consistent values
rather than hardcoding numbers in multiple places.

### Phase 2 — LiteLLM ConfigMap

**Commit:** `292063e feat(p4): add litellm configmap and values`

A ConfigMap is a Kubernetes object that stores configuration data as key-value pairs or
files. Pods can mount a ConfigMap as a file on disk. Here, the entire LiteLLM configuration
is stored as a ConfigMap so that changing the model list or routing strategy is a Git
commit — no need to rebuild the container image.

The ConfigMap contains a `config.yaml` file that LiteLLM reads at startup:

```yaml
model_list:
  - model_name: local/llama3.2
    litellm_params:
      model: ollama/llama3.2
      api_base: http://10.212.46.5:11434
  - model_name: local/mistral
    litellm_params:
      model: ollama/mistral
      api_base: http://10.212.46.5:11434
  - model_name: local/deepseek-r1
    litellm_params:
      model: ollama/deepseek-r1:7b
      api_base: http://10.212.46.5:11434

router_settings:
  routing_strategy: least-busy
  num_retries: 2
  timeout: 120
```

Each `model_name` is the name callers use in their API requests. Each `litellm_params`
block tells LiteLLM how to reach the actual model. The `ollama/` prefix tells LiteLLM to
use its Ollama provider driver.

`routing_strategy: least-busy` routes each request to whichever model has the fewest
requests in flight. This is the right choice for a single-host Ollama server because round-
robin would queue requests behind a slow model even if another model is idle. Least-busy
keeps throughput as high as possible given the available hardware.

`num_retries: 2` means LiteLLM will try twice more if the first attempt fails. This handles
transient Ollama hiccups without the caller seeing an error.

`timeout: 120` gives Ollama two minutes to respond. Language model inference on CPU
hardware is slow, and a model that hasn't been used recently takes additional time to load
from disk into RAM. 120 seconds is enough for a cold-start on a small model.

The LiteLLM deployment template includes a checksum annotation:

```yaml
annotations:
  checksum/config: {{ include (print $.Template.BasePath "/configmap-litellm.yaml") . | sha256sum }}
```

This forces a pod restart whenever the ConfigMap changes. Without it, Kubernetes would not
restart the LiteLLM pod when only the ConfigMap changed, and the pod would keep running
with stale config.

### Phase 3 — FastAPI Application

**Commit:** `95f2ab7 feat(p4): add fastapi gateway app and dockerfile`

The application has three Python files.

**`main.py`** is the entrypoint. Line by line:

```python
app = FastAPI(title="BLS LLM Gateway", ...)
```
Creates the application object. The `title` and `description` appear in the auto-generated
docs at `/docs`.

```python
app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)
```
Allows browsers to make API calls from any origin. Without this, a browser-based tool on a
different domain would have its requests blocked by the browser before they reached the
server.

```python
app.add_middleware(APIKeyMiddleware)
```
Registers the authentication middleware. Every request runs through this before it reaches
any route handler.

```python
app.include_router(completions.router, prefix="/v1")
```
Registers the completions router under the `/v1` prefix, so the full path becomes
`/v1/chat/completions` — matching the OpenAI API path that all compatible tools expect.

```python
@app.get("/healthz")
async def health():
    return {"status": "ok", "service": "bls-llm-gateway"}
```
A health check endpoint. Kubernetes probes this every few seconds to decide whether the
pod is alive and ready to receive traffic.

**`middleware/auth.py`** — the authentication middleware:

```python
VALID_KEYS = set(os.getenv("BLS_API_KEYS", "").split(","))
```
Reads the list of valid API keys from an environment variable at startup. The environment
variable is injected from the Kubernetes Secret. Using a `set` means key lookups are O(1)
regardless of how many keys exist.

```python
if request.url.path in ["/healthz", "/docs", "/openapi.json"]:
    return await call_next(request)
```
Three paths bypass authentication entirely. `/healthz` must be open so Kubernetes health
probes work without needing a token. `/docs` and `/openapi.json` expose the interactive
API documentation without requiring credentials.

```python
if not auth.startswith("Bearer "):
    raise HTTPException(status_code=401, detail="Missing Bearer token")
```
A request with no `Authorization` header, or one that uses a scheme other than `Bearer`,
gets a 401 Unauthorized response. The call never reaches the completions router.

```python
token = auth.removeprefix("Bearer ").strip()
if token not in VALID_KEYS:
    raise HTTPException(status_code=403, detail="Invalid API key")
```
A request with a `Bearer` token that is not in the valid key set gets a 403 Forbidden
response. The distinction between 401 (unauthenticated) and 403 (authenticated but not
authorised) is intentional: 401 means "try again with credentials", 403 means "your
credentials don't grant access".

**`routers/completions.py`** — the proxy route:

```python
LITELLM_URL = os.getenv("LITELLM_URL", "http://litellm-service:4000")
```
The LiteLLM address comes from an environment variable, defaulting to the Kubernetes DNS
name `litellm-service` on port 4000. Inside the cluster, Kubernetes automatically creates
DNS entries for every Service, so `litellm-service` resolves to the correct pod IP without
any configuration.

```python
class ChatRequest(BaseModel):
    model: str
    messages: list[dict]
    temperature: float = 0.7
    max_tokens: int = 1024
    stream: bool = False
```
Pydantic validates the request body against this schema before the handler runs. A malformed
request (missing `messages`, wrong types) is rejected with a 422 before any upstream call
is made.

```python
async with httpx.AsyncClient(timeout=130.0) as client:
```
The timeout is 130 seconds — 10 seconds more than LiteLLM's own 120-second model timeout.
This ensures LiteLLM has time to time out and return a clean error before the FastAPI client
gives up, so the caller gets a meaningful error message rather than a connection reset.

```python
headers={"Authorization": f"Bearer {os.getenv('LITELLM_MASTER_KEY', '')}"},
```
FastAPI passes a master key to LiteLLM. This key is read from the Secret and injected as an
environment variable. Note: this key exists for internal service-to-service authentication
only. External callers authenticate with the `BLS_API_KEYS` set in the middleware — they
never see or use the LiteLLM master key.

**`Dockerfile`:**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir \
    fastapi==0.111.0 \
    uvicorn[standard]==0.30.0 \
    httpx==0.27.0 \
    pydantic==2.7.0
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

Versions are pinned to exact numbers to ensure the image built today behaves identically
to the image built in six months. `python:3.11-slim` is used instead of the full Python
image to reduce the image size (and therefore pull time and attack surface).
`--workers 2` means uvicorn spawns two processes, which allows two requests to be handled
concurrently even if one is waiting on a slow LiteLLM response.

### Phase 4 — Kubernetes Templates

**Commit:** `2171460 feat(p4): add kubernetes deployment service and ingress templates`

**What a Deployment is:** A Deployment tells Kubernetes to run a specific container image
and keep a specified number of copies of it running at all times. If a pod crashes,
Kubernetes restarts it. If you update the image, Kubernetes replaces pods one at a time
so the service stays available.

**What a Service is:** A Service gives a Deployment a stable internal network address
(DNS name and IP). Pods have ephemeral IPs that change every restart. A Service IP is
stable. When FastAPI needs to reach LiteLLM, it connects to `litellm-service:4000`, and
Kubernetes routes that to whichever LiteLLM pod is currently running.

**What an Ingress is:** An Ingress is a rule that tells the cluster's ingress controller
(here, Traefik) how to route external HTTP traffic to an internal Service. Without an
Ingress, the FastAPI Service is only reachable from inside the cluster. With the Ingress,
`http://llm-gateway.local` routes to `llm-gateway-service:8000`.

There are three separate Deployments because each component has a different lifecycle.
The gateway image is rebuilt by CI when the FastAPI code changes. The LiteLLM image is
managed by the LiteLLM project upstream and updated by changing the tag in `values.yaml`.
Redis never changes — it is a stable dependency. Separating them means a FastAPI code
change does not restart LiteLLM or Redis, and a LiteLLM upgrade does not restart the
gateway.

**The bootstrap Secret:**

```yaml
# BOOTSTRAP ONLY — replace with Sealed Secrets in Project 5
apiVersion: v1
kind: Secret
metadata:
  name: llm-gateway-secrets
  namespace: llm-gateway
type: Opaque
stringData:
  litellm-master-key: "bls-dev-master-key-change-me"
  bls-api-keys: "bls-local-dev-key-001"
```

This Secret is checked into Git with placeholder values. It is explicitly temporary. The
comment is load-bearing: it documents that this is a known gap, not an oversight. In a
production system, secrets must never be stored in plaintext in Git. Project 5 will
replace this with Sealed Secrets, which encrypts the secret before it is committed so that
only the cluster can decrypt it.

### Phase 5 — GitOps Wire-up

**Commit:** `51b8ad0 feat(p4): add argocd application manifest and copy helm chart to gitops path`

**What ArgoCD is:** ArgoCD is a Kubernetes controller that implements the GitOps pattern. It
runs inside the cluster and periodically compares the desired state (what is in Git) against
the actual state (what is running in the cluster). When they differ, ArgoCD applies the
difference. You configure it once and then interact with the cluster through Git.

**What GitOps means in practice:** Instead of running `kubectl apply -f file.yaml` to deploy
a change, you run `git push`. ArgoCD sees the push and does the apply. This means every
deployment is recorded in Git history, every change is reviewable before it is applied, and
rolling back means reverting a commit.

**The ArgoCD Application manifest:**

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: llm-gateway
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/CalmAfterReboot/BLS-platform
    targetRevision: HEAD
    path: k8s/workloads/llm-gateway
    helm:
      valueFiles:
        - values.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: llm-gateway
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

- `repoURL`: the GitHub repository to watch.
- `targetRevision: HEAD`: always track the latest commit on the default branch.
- `path`: the directory inside the repo that contains the Helm chart.
- `helm.valueFiles`: which values file to use when rendering templates.
- `destination.server: https://kubernetes.default.svc`: deploy to the same cluster where
  ArgoCD is running. This is the in-cluster API server address.
- `destination.namespace: llm-gateway`: deploy resources into this namespace.
- `prune: true`: if a file is deleted from Git, the corresponding resource is deleted from
  the cluster.
- `selfHeal: true`: if someone manually changes a resource in the cluster, ArgoCD reverts
  it back to match Git.
- `CreateNamespace=true`: ArgoCD creates the `llm-gateway` namespace if it does not exist,
  so you do not need a separate `kubectl create namespace` step.

The chart lives at `k8s/workloads/llm-gateway/` rather than `04-llm-gateway/` because the
`k8s/workloads/` path is the conventional location for GitOps-managed workloads in this
repository. The `04-llm-gateway/` directory is the project working directory, which also
contains the application source code (`app/`) and the ArgoCD manifest — none of which
ArgoCD should be rendering as Helm templates.

### Phase 6 — CI Pipeline

**Commit:** `f1e82f1 ci(p4): add github actions build workflow for llm-gateway`

**What GitHub Actions does here:** Every time code in the application directory changes and
is pushed to `main`, GitHub Actions automatically builds a new Docker image and pushes it
to GHCR (GitHub Container Registry). Without this, updating the gateway would require a
developer to run `docker build` and `docker push` locally before pushing to Git.

**The trigger:**

```yaml
on:
  push:
    paths:
      - 'k8s/workloads/llm-gateway/app/**'
    branches: [main]
```

The workflow only fires when files under `app/**` change. A change to `values.yaml` or a
Helm template does not rebuild the image — it just triggers ArgoCD to redeploy with the
updated configuration. This avoids unnecessary image builds and keeps CI fast.

**GHCR and GITHUB_TOKEN:** GHCR (GitHub Container Registry) is GitHub's built-in Docker
registry at `ghcr.io`. Every GitHub Actions workflow run automatically receives a
`GITHUB_TOKEN` secret, which is a short-lived token scoped to the repository. By declaring
`permissions: packages: write` in the workflow, that token is granted permission to push
images to GHCR under the repository owner's namespace. No separate secret or service account
is needed.

---

## Problems Encountered and How They Were Fixed

### 1. Ollama bound to 127.0.0.1

**Symptom:** LiteLLM returned connection errors when trying to reach Ollama at
`10.212.46.5:11434`. The Ollama process was running but unreachable from the network.

**Root cause:** By default, Ollama listens only on `127.0.0.1` (localhost). Connections from
the Kubernetes cluster arrive on the LAN interface, not localhost, and are refused.

**Fix:** Override the `OLLAMA_HOST` environment variable in the Ollama systemd service using
a drop-in override:

```bash
sudo systemctl edit ollama
```

Add the following in the editor:

```ini
[Service]
Environment="OLLAMA_HOST=0.0.0.0"
```

Then reload and restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

**Verification:**

```bash
curl http://10.212.46.5:11434/api/tags
```

A successful response lists the available models as JSON.

---

### 2. `__pycache__` committed to Git

**Symptom:** After running the FastAPI application locally, Python generated `__pycache__/`
directories containing compiled `.pyc` bytecode files. These were accidentally staged and
committed.

**Root cause:** No `.gitignore` existed in the `app/` directory. Git tracked everything.

**Fix:** Add a `.gitignore` in `app/` and use `git rm --cached` to remove the already-
tracked files from Git's index without deleting them from disk:

```bash
echo "__pycache__/
*.pyc
*.pyo
.env" > 04-llm-gateway/app/.gitignore

git rm -r --cached 04-llm-gateway/app/__pycache__/
git rm -r --cached 04-llm-gateway/app/middleware/__pycache__/
git rm -r --cached 04-llm-gateway/app/routers/__pycache__/
```

**Lesson:** `.gitignore` should be one of the first files created in any Python project
directory, before the interpreter is ever run. Bytecode files are machine-specific and
have no place in version control.

---

### 3. llm-gateway `ImagePullBackOff` (403 on GHCR)

**Symptom:** After the first deployment via ArgoCD, the `llm-gateway` pod entered
`ImagePullBackOff` status. `kubectl describe pod` showed a 403 Forbidden error from GHCR
when Kubernetes tried to pull `ghcr.io/calmafterreboot/bls-llm-gateway:latest`.

**Root cause:** The image had never been built or pushed. It did not exist in GHCR yet.

**Why 403 and not 404:** GHCR returns 403 for packages that either do not exist or are
private and the requester is unauthenticated. This is intentional: returning 404 for a
private package would reveal that the package exists but is private. From the cluster's
perspective, 403 and "package doesn't exist yet" look identical.

**Fix:** Build and push the image manually from a machine with Docker and GitHub credentials:

```bash
docker build -t ghcr.io/calmafterreboot/bls-llm-gateway:latest \
  k8s/workloads/llm-gateway/app/

docker push ghcr.io/calmafterreboot/bls-llm-gateway:latest
```

After the image exists in GHCR, ArgoCD triggered a pod restart and it came up successfully.
Subsequent image updates are handled automatically by the GitHub Actions workflow.

---

### 4. litellm `OOMKilled`

**Symptom:** The `litellm` pod kept restarting. `kubectl describe pod litellm-<id>` showed
`Exit Code: 137` in the last state. Exit code 137 means the process was killed by the
kernel's Out-Of-Memory (OOM) killer.

**Root cause:** LiteLLM's memory footprint at startup is higher than expected. The initial
resource limit of 512Mi was not enough for the process to start cleanly.

**Iterations:**

| Commit | Limit | Result |
|--------|-------|--------|
| initial | 512Mi | OOMKilled on startup |
| `a899b7c` | 600Mi | OOMKilled under light load |
| `ec7ef7b` | 1Gi | Stable at startup, OOMKilled under model requests |
| `2387f9b` | 2Gi | Stable |

The request was also raised from 256Mi to 512Mi so Kubernetes schedules the pod on a node
that actually has enough headroom.

**Why 2Gi:** `kubectl top pod -n llm-gateway` showed LiteLLM consuming approximately 1.4Gi
under normal operation with a model request in flight. 2Gi gives sufficient headroom. This
value should be right-sized after profiling under realistic load (see Known Gaps).

---

### 5. litellm readiness probe returning 401

**Symptom:** The `litellm` pod showed `0/1 READY` in `kubectl get pods` even though the
process was running and responding to requests. The pod was never marked ready, so no
traffic was routed to it.

**Root cause:** The original readiness probe called `GET /health` on port 4000. When
LiteLLM has a `master_key` configured (which it did at the time), it requires
authentication on all endpoints including `/health`. The Kubernetes probe makes an
unauthenticated HTTP request, which LiteLLM rejects with 401. Kubernetes interprets a
non-2xx response as a failed probe.

**Fix:** LiteLLM exposes `/health/liveliness` as an explicitly unauthenticated health
endpoint. Switching both probes to that path resolved the issue:

```yaml
livenessProbe:
  httpGet:
    path: /health/liveliness
    port: 4000
readinessProbe:
  httpGet:
    path: /health/liveliness
    port: 4000
```

---

### 6. LiteLLM `No connected db` error

**Symptom:** After fixing the probe path, LiteLLM started successfully but logged
`No connected db` errors and refused to process requests. The error appeared immediately
on startup before any requests were made.

**Root cause:** In LiteLLM v1.x, setting a `master_key` in `general_settings` activates
database mode. LiteLLM expects a `DATABASE_URL` environment variable pointing to a
PostgreSQL instance it can use to store spend logs and budget tracking data. No database
was configured — the stack uses Redis for caching only, not PostgreSQL for spend logging.
LiteLLM would not proceed without the database it expected.

**Fix (two steps):**

First, `disable_spend_logs: true` and `disable_reset_budget: true` were added to
`general_settings` to suppress the features that require a database. This partially
resolved the issue but the database dependency remained because the `master_key` itself
is what triggers database mode.

Second, `master_key` was removed from `general_settings` entirely:

```yaml
general_settings:
  disable_spend_logs: true
  disable_reset_budget: true
```

**Why this is architecturally correct:** LiteLLM's `master_key` is designed for use cases
where LiteLLM is the authentication layer — where clients authenticate directly with
LiteLLM. In this project, authentication is handled entirely by the FastAPI gateway. No
external caller ever reaches LiteLLM directly; it is an internal service only reachable
within the cluster. LiteLLM does not need to authenticate its callers because FastAPI
already did that. Removing `master_key` from LiteLLM is the right call architecturally,
not just a workaround.

---

### 7. GitHub Actions `write_package` permission denied

**Symptom:** The first run of the `build-gateway.yaml` workflow failed with a 403 error
during the `docker push` step. The workflow had `permissions: packages: write` declared,
but the push was still rejected.

**Root cause:** Two separate permission settings must both be configured. Declaring
permissions in the workflow YAML grants the token the capability in principle, but the
repository must also be configured to allow Actions workflows to write packages.

**Fix (two steps in the GitHub UI):**

Step 1 — Repository workflow permissions:
1. Go to the repository on GitHub
2. Settings → Actions → General
3. Under "Workflow permissions", select **Read and write permissions**
4. Save

Step 2 — Package Actions access:
1. Go to your GitHub profile → Packages
2. Find `bls-llm-gateway`
3. Package Settings → Manage Actions access
4. Add the repository and grant it **Write** access

After both changes, re-running the workflow succeeded.

---

## Key Decisions and Why

**Why LiteLLM runs in proxy mode not SDK mode.** SDK mode would have required importing
LiteLLM into the FastAPI codebase and calling it directly from Python. Proxy mode keeps
LiteLLM as a separate, independently scalable process. If LiteLLM needs to be updated, it
is a one-line change in `values.yaml` — no code change, no image rebuild. Proxy mode also
means LiteLLM can be replaced with a different routing layer entirely without touching the
FastAPI codebase.

**Why auth lives in FastAPI not LiteLLM.** LiteLLM's authentication model is designed
around spend tracking and per-key rate limiting backed by a database. That is more than
is needed here, and it comes with a PostgreSQL dependency. FastAPI's auth middleware does
exactly what is required — check the key, allow or reject — with no external dependencies.
Keeping auth in FastAPI also means the security boundary is at the public-facing layer, not
an internal component.

**Why Ollama runs on the Proxmox host not inside k3s.** Language models load several
gigabytes of weights into RAM on startup. A Kubernetes pod has memory limits; exceeding
them triggers an OOMKill. Running Ollama natively on Proxmox gives it access to all
physical RAM on the machine with no artificial ceiling. It also avoids the operational
complexity of persistent volume mounts for model storage in a homelab environment where
storage is not replicated.

**Why `routing_strategy` is `least-busy` not `round-robin`.** Round-robin distributes
requests evenly across backends regardless of how long each request takes. On a single-host
Ollama server serving multiple models, a long-running deepseek-r1 request would block
subsequent round-robin assignments to that model even if llama3.2 is idle. Least-busy
routes to whichever backend has the fewest active requests, which keeps the overall system
more responsive when models have different inference times.

**Why the bootstrap Secret is a known gap.** Storing secrets in Git, even placeholder
values, is a known anti-pattern. The comment in `secret.yaml` documents this explicitly.
It exists because the stack needs _some_ Secret to be present for the pods to start (the
Deployments reference Secret keys as environment variables). Project 5 will introduce
Sealed Secrets, which allows encrypted secret values to be committed safely. The bootstrap
Secret is replaced at that point.

**Why Redis is included now even though semantic caching isn't configured yet.** The
LiteLLM configuration has the `cache:` block pointing to Redis, which means LiteLLM will
use Redis for exact-match response caching automatically even without semantic caching.
Semantic caching (which uses vector embeddings to match similar but not identical prompts)
is a separate feature that requires an embeddings model. Including Redis now, with the
cache block wired in, means the infrastructure is ready when that feature is added. Removing
and re-adding Redis later would cause a brief disruption to the running stack.

---

## Known Gaps (Addressed in Project 5)

- **Bootstrap secret → Sealed Secrets.** The `secret.yaml` file contains plaintext
  placeholder credentials committed to Git. Project 5 replaces this with Sealed Secrets,
  where the secret is encrypted with the cluster's public key before being committed, and
  only the cluster can decrypt it.

- **No TLS on ingress → cert-manager.** The ingress does not terminate HTTPS. All traffic
  to `llm-gateway.local` is plain HTTP. Project 5 adds cert-manager with a self-signed or
  Let's Encrypt certificate so traffic is encrypted in transit.

- **Manual image tag → ArgoCD Image Updater.** The gateway Deployment always pulls
  `:latest`. This works but gives no visibility into which exact version is running.
  Project 5 introduces ArgoCD Image Updater, which automatically opens a PR (or commits
  directly) when a new image tag is pushed to GHCR, pinning the deployment to an immutable
  digest.

- **LiteLLM memory at 2Gi → right-size after profiling with `kubectl top`.** The 2Gi limit
  was set empirically by observing OOMKills under load. It has not been profiled under
  representative sustained traffic. Run `kubectl top pod -n llm-gateway` during a realistic
  workload and set the limit to observed peak plus 20% headroom.

---

## How to Test It

**1. Check all pods are running:**

```bash
kubectl get pods -n llm-gateway
```

Expected output:

```
NAME                           READY   STATUS    RESTARTS   AGE
llm-gateway-<id>               1/1     Running   0          5m
litellm-<id>                   1/1     Running   0          5m
redis-<id>                     1/1     Running   0          5m
```

All three pods must show `1/1 Running` before proceeding. If any show `0/1` or
`CrashLoopBackOff`, run `kubectl describe pod <pod-name> -n llm-gateway` to see the error.

**2. Port-forward the gateway service:**

```bash
kubectl port-forward svc/llm-gateway-service 8080:8000 -n llm-gateway
```

This forwards `localhost:8080` on your machine to the gateway Service inside the cluster.
Leave this terminal open and open a second terminal for the next steps.

**3. Run the smoke test:**

```bash
curl -s -X POST http://localhost:8080/v1/chat/completions \
  -H "Authorization: Bearer bls-local-dev-key-001" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "local/llama3.2",
    "messages": [{"role": "user", "content": "Say hello in one sentence."}],
    "max_tokens": 64
  }' | jq .
```

Expected response shape:

```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "model": "local/llama3.2",
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "Hello! It's great to meet you."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 12,
    "completion_tokens": 14,
    "total_tokens": 26
  }
}
```

A 401 response means the Bearer token is wrong or missing. A 504 means Ollama timed out
(check that Ollama is running on the Proxmox host with `systemctl status ollama`).

**4. Check LiteLLM is routing correctly:**

```bash
kubectl port-forward svc/litellm-service 4001:4000 -n llm-gateway
curl http://localhost:4001/health/liveliness
```

Expected: `{"status": "healthy"}` or similar JSON with a 200 status code.

**5. Check Redis is running:**

```bash
kubectl exec -it -n llm-gateway \
  $(kubectl get pod -n llm-gateway -l app=redis -o jsonpath='{.items[0].metadata.name}') \
  -- redis-cli ping
```

Expected: `PONG`

---

## Git History

```
git log --oneline -- 04-llm-gateway/ k8s/workloads/llm-gateway/
```

```
bffcf15 ci(p4): trigger initial workflow run
ea7046c fix(p4): remove master_key from litellm config to avoid db requirement
5d1695e fix(p4): disable litellm db requirement in general_settings
364b187 fix(p4): use unauthenticated health endpoint for litellm probes
2387f9b fix(p4): bump litellm memory limit to 2Gi
ec7ef7b fix(p4): bump litellm memory limit to 1Gi
a899b7c fix(p4): increase litellm memory limit to 600Mi to prevent OOMKill
51b8ad0 feat(p4): add argocd application manifest and copy helm chart to gitops path
2171460 feat(p4): add kubernetes deployment service and ingress templates
d2f3ffb chore(p4): add .gitignore for python bytecode, remove cached pycache
95f2ab7 feat(p4): add fastapi gateway app and dockerfile
292063e feat(p4): add litellm configmap and values
6356110 feat(p4): scaffold llm-gateway helm chart structure
```

| Commit | What it did |
|--------|-------------|
| `6356110` | Created `Chart.yaml`, `values.yaml`, and directory skeleton — the deployable Helm chart shape |
| `292063e` | Added LiteLLM `ConfigMap` with three model definitions and router/cache settings |
| `95f2ab7` | Added `main.py`, `auth.py`, `completions.py`, and `Dockerfile` — the FastAPI application |
| `d2f3ffb` | Added `.gitignore` and removed committed `__pycache__` bytecode files |
| `2171460` | Added all Kubernetes templates: Deployments, Services, Ingress, and the bootstrap Secret |
| `51b8ad0` | Applied ArgoCD Application manifest and mirrored chart to `k8s/workloads/llm-gateway/` |
| `a899b7c` | Raised litellm memory limit 512Mi → 600Mi after first OOMKill observation |
| `ec7ef7b` | Raised litellm memory limit 600Mi → 1Gi after second OOMKill under load |
| `2387f9b` | Raised litellm memory limit 1Gi → 2Gi (stable); raised request 256Mi → 512Mi |
| `364b187` | Switched litellm probes from `/health` to `/health/liveliness` to fix 401 readiness failures |
| `5d1695e` | Added `disable_spend_logs` and `disable_reset_budget` to suppress database dependency |
| `ea7046c` | Removed `master_key` from litellm config entirely — root fix for the database requirement |
| `bffcf15` | Empty trigger commit to fire the GitHub Actions workflow for the first time |

---

## Tags

`v0.4.0-llm-gateway-live` marks the state of the repository when the full stack was
confirmed running: all three pods in `1/1 Running` state, the smoke test returning a valid
completion response, ArgoCD showing the application as `Synced` and `Healthy`, and the
GitHub Actions CI workflow passing on the `main` branch. The tag represents a stable,
deployable baseline before Project 5 begins addressing the known gaps.
