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
