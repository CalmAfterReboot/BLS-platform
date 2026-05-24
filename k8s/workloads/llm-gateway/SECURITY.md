# Security

This document covers the LLM Gateway component only
(`k8s/workloads/llm-gateway/`). Repo-wide security policy lives at the root.

## Secret management

The gateway never stores upstream-provider secrets in version control:

- The OpenAI API key used by the live verification suite lives in
  `k8s/workloads/llm-gateway/.env` (gitignored — see
  [`.env.example`](.env.example) for the template).
- The deployed gateway in `app/` does not read `OPENAI_API_KEY` directly;
  routing to external providers happens inside LiteLLM, configured via
  [`templates/configmap-litellm.yaml`](templates/configmap-litellm.yaml).
  Production secrets are injected via Kubernetes Secrets — see WU-4
  (Sealed Secrets) in the chart [README](README.md).
- The verification key is loaded only at test time by
  [`tests/live/conftest.py`](tests/live/conftest.py), which uses
  `python-dotenv` to read `.env` and then defers to LiteLLM's own env-var
  resolution. The key value is never logged, echoed, or written to disk
  outside `.env` itself.
- No key, header, or auth material ever lands in the verification artefacts
  under [`docs/verification/`](docs/verification/) — those record only the
  sanitised request the test sent and a public response envelope
  (`model_used`, `completion`, `attempts`, `failover_occurred`,
  `latency_ms`, `finish_reason`).

## SealedSecret workflow

The in-cluster `llm-gateway-secrets` Secret is committed as a Bitnami
`SealedSecret` at [`templates/secret.yaml`](templates/secret.yaml).
Three keys are sealed:

| Key | Used by |
|---|---|
| `litellm-master-key` | `deployment-gateway.yaml` env var (forwarded by the FastAPI proxy as `Authorization: Bearer …` when calling the in-cluster LiteLLM service) |
| `bls-api-keys` | `deployment-gateway.yaml` env var, validated by `app/middleware/auth.py` for every inbound non-`/healthz`/`/metrics` request |
| `ollama-endpoint` | `deployment-litellm.yaml` env var, substituted into the LiteLLM configmap via `api_base: os.environ/OLLAMA_ENDPOINT` |

The manifest is sealed with `kubeseal --scope=strict`, which binds it
to **exactly** namespace `llm-gateway` and name `llm-gateway-secrets`.
Applying it in any other namespace or under a different name will
fail to decrypt — by design.

### Re-sealing (rotating keys, changing values, or adding fields)

```bash
# 1. Build a plaintext Secret manifest locally — NEVER commit this.
cat > /tmp/llm-gateway-plaintext.yaml <<'EOF'
apiVersion: v1
kind: Secret
metadata:
  name: llm-gateway-secrets
  namespace: llm-gateway
type: Opaque
stringData:
  litellm-master-key: "<new-value>"
  bls-api-keys: "<new-value>"
  ollama-endpoint: "<new-value>"
EOF

# 2. Fetch the homelab controller's public cert.
kubeseal --controller-namespace=sealed-secrets \
         --controller-name=sealed-secrets --fetch-cert > /tmp/ss-cert.pem

# 3. Seal.
kubeseal --cert=/tmp/ss-cert.pem --format=yaml \
         --scope=strict --namespace=llm-gateway \
         < /tmp/llm-gateway-plaintext.yaml > /tmp/llm-gateway-sealed.yaml

# 4. Replace the encryptedData blocks in templates/secret.yaml with the
#    output. Preserve the Helm template wrapping (the comment header,
#    `{{ .Values.namespace }}` substitutions, and the strict-scope
#    metadata).

# 5. Shred the plaintext.
shred -u /tmp/llm-gateway-plaintext.yaml
```

After commit + merge, ArgoCD reconciles. The sealed-secrets controller
unseals the SealedSecret, the resulting `Secret` change triggers a
rolling restart of both `llm-gateway` and `litellm` deployments via the
`checksum/secret` annotation on each pod template.

### Reading the current decrypted values

The unsealed Secret is a normal Kubernetes Secret — read it with
kubectl in the usual way:

```bash
kubectl get secret llm-gateway-secrets -n llm-gateway \
  -o jsonpath='{.data.bls-api-keys}' | base64 -d
```

Treat the output as sensitive: never paste into a chat, never write to
disk outside `/tmp`, never echo into shell history without `set +o
history` first.

### Multi-cluster note

`SealedSecret` is **cluster-specific**: the encryption is bound to
the public key of the sealed-secrets controller running in that
cluster. The committed `templates/secret.yaml` is sealed against the
homelab (`in-cluster`) controller only. When the `bls-aks-demo`
cluster is re-enabled (currently the `llm-gateway-bls-aks-demo`
Application reports `Unknown` sync), it will need:

- Its own sealed-secrets controller deployed (via the
  `sealed-secrets` Argo Application).
- A separate sealed manifest produced against that controller's
  public cert and applied to the AKS cluster.

The chart structure today does not branch on cluster identity for
the secret. The forward path when AKS comes back is either:

1. Per-cluster overlays via the ApplicationSet's matrix
   parameters, OR
2. An external secret backend (Azure Key Vault + CSI driver) for
   the AKS deployment specifically.

That decision is deferred until the AKS cluster is reachable again.

## Cost cap

The OpenAI key used here is **prepay-only with a $10 hard cap.** Each
verification run costs fractions of a cent:

| Call | Model | Output cap | Approximate cost |
|---|---|---|---|
| Happy path | `openai/gpt-4o-mini` | 8 tokens | < $0.0001 |
| Forced failover — primary | `openai/does-not-exist-…` | n/a (404) | $0 |
| Forced failover — fallback | `openai/gpt-4o-mini` | 8 tokens | < $0.0001 |

Two billable completions per full run, both at `max_tokens=8`. The suite is
not run on CI — there is no automation that drains the cap.

## Pre-commit gates

Hygiene hooks live at the repo root in
[`../../../.pre-commit-config.yaml`](../../../.pre-commit-config.yaml). The
hooks relevant to this gateway:

| Hook | Purpose |
|---|---|
| `detect-secrets` (root `.secrets.baseline`) | Block accidental commits of API keys, tokens, and high-entropy strings. `docs/verification/` is excluded so generated artefacts don't trip the hook on high-entropy completion text. |
| `ruff` / `ruff-format` (scoped to `k8s/workloads/llm-gateway/tests/**.py`) | Lint and format the Python test suite under this chart only — the deployed `app/` is intentionally left alone to avoid surprise reformats. |
| Hygiene (trailing whitespace, EOF, large files, merge-conflict markers) | Standard. |
| `detect-private-key` | Block private-key material. |

First-time setup after cloning:

```bash
cd k8s/workloads/llm-gateway
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# From repo root:
pre-commit install               # wire the hook into .git/hooks
pre-commit run --all-files       # one-off check across the tree
```

## Triaging a `detect-secrets` finding

When pre-commit blocks a commit with a `detect-secrets` failure, the hook
prints the file path and the secret type. The two correct responses:

### False positive

Examples: a high-entropy test fixture string, an example token in
documentation, a Base64-encoded fixture payload.

```bash
# From repo root
detect-secrets audit .secrets.baseline
# Interactive triage — mark the finding as "not a secret".
git add .secrets.baseline
git commit -m "chore: triage detect-secrets baseline"
```

After the audit, the baseline records the finding as known and pre-commit
will allow the original file through.

### True positive

A **real key was about to be committed.** Treat the key as compromised even
if the commit never landed — assume it touched disk and shell history.
Rotate immediately:

1. **Revoke** the key in the provider dashboard. For OpenAI:
   Settings → API Keys → Revoke.
2. **Generate a fresh** project-scoped key with the same `$10` hard cap and
   "Restricted" permission level. Paste it into
   `k8s/workloads/llm-gateway/.env`.
3. **Unstage and scrub** the file:
   ```bash
   git restore --staged <file>
   # then edit <file> to remove the literal secret
   ```
4. If the key had been pushed in earlier history, follow GitHub's guide on
   [removing sensitive data from a repository](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository).
   For a public repo, **assume the key is harvested** even after rewrite —
   rotation is the only defence that matters.

## Live OpenAI verification

The opt-in `tests/live/` suite exercises the real OpenAI endpoint through
the LiteLLM SDK — the same library the deployed `litellm` proxy uses for
its routing. See the committed artefacts under
[`docs/verification/`](docs/verification/). The suite skips cleanly if
`OPENAI_API_KEY` is absent.

```bash
cd k8s/workloads/llm-gateway
source .venv/bin/activate
pytest -m live -v
```

Two scenarios are exercised:

| Scenario | Mechanism | Expected outcome |
|---|---|---|
| Happy path | `litellm.completion(model="openai/gpt-4o-mini", ...)` | Non-empty completion, `failover_occurred=false`. |
| Forced failover | `litellm.Router` with bad primary `openai/does-not-exist-…` and `gpt-4o-mini` as the fallback | Router catches the 404, response served by gpt-4o-mini, `failover_occurred=true`. |

Each run writes a dated JSON artefact:

- `openai-live-happy-path-YYYY-MM-DD.json`
- `openai-live-forced-failover-YYYY-MM-DD.json`

The artefacts contain no API key, no headers, no auth material — only the
test inputs and a sanitised view of the gateway's response envelope.

## SDK / proxy version drift

The deployed LiteLLM proxy container in `templates/deployment-litellm.yaml`
is pinned to `ghcr.io/berriai/litellm:main-latest`, while the live test
suite pins the LiteLLM Python SDK to `>=1.40,<2.0` in
[`requirements-dev.txt`](requirements-dev.txt). These can diverge.

The live suite is a verification that the **library** path works against a
real OpenAI endpoint. It is not a guarantee that the **deployed proxy**
behaves identically to the SDK at every release. Right-size by pinning the
proxy image to a known-good digest before any production use that depends
on specific router semantics.

## Reporting

For security concerns, contact the maintainer via the email on the GitHub
profile of the repository owner.
