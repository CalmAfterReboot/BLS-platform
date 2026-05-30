# ADR-015 — Container Image Digest Pinning + Renovate Workflow

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-05-28 |
| **Project** | BLS Project 6 — Platform Engineering (Stream C) |
| **Deciders** | BLS DevOps |

---

## Context

The audit at the start of P6 flagged image-pinning as a known gap (audit §3, §10 #6): every first-party image referenced a floating tag — `:latest` for the gateway, `:main-latest` for LiteLLM, `:7-alpine` for Redis. Only `stefanprodan/podinfo:6.7.0` was version-pinned, and even that wasn't digest-pinned.

Three concrete failure modes follow from floating tags in a GitOps platform with `selfHeal: true`:

1. **Silent upstream rolls forward.** `build-gateway.yaml` overwrites `:latest` on every merge to `main`. The next ArgoCD reconcile pulls whatever happened to be at `:latest` at that moment — not the image that was reviewed in the merge commit. Any review of "what's running in the cluster" is approximate.
2. **No rollback target.** If a regression ships, "roll back to the previous version" is undefined — `:latest` is whatever the registry says now. There is no immutable handle on the previous image. Recovery becomes "find the old commit, look at the build artefacts, hope GHCR's retention kept that layer."
3. **Supply chain assumption.** Floating tags allow the registry to substitute different content for the same tag string. A compromised GHCR account, a typo'd tag overwrite, a rebuilt-for-arm64 single-arch substitution — all of these change what the cluster pulls without changing what the repo declares.

This ADR records the decision to fix all three by pinning every first-party and critical-path image to its immutable SHA-256 digest, and to manage the bump cadence via Renovate.

---

## Options Considered

### Option A — Status quo: floating tags + manual bumps when something breaks

Keep `:latest`, `:main-latest`, `:7-alpine`. Operator pulls and inspects images out-of-band; no digest references in the repo.

**Rejected.** This is what the audit flagged. Documented failure modes above.

### Option B — Tag-pin to specific versions (e.g., `:v0.4.0`, `:7.4.0-alpine`)

Replace floating tags with explicit version tags, but stop short of digest. `:v0.4.0` is documented to mean "the v0.4.0 release of the gateway."

**Rejected as insufficient.** A version tag can still be re-pushed; OCI registries treat tags as mutable pointers. Tag pinning is a *convention*, not a *cryptographic constraint*. An attacker (or a careless operator) who can push to the registry can repoint `:v0.4.0` at a different image; the cluster pulls the new one on the next reconcile. The whole point of digest pinning is that the cluster's pull request includes the content hash, and the registry returns 404 if the hash doesn't match.

### Option C — Digest-pin every image + Renovate-managed bumps *(selected)*

Replace every `image: <repo>:<tag>` with `image: <repo>@sha256:<digest>`. The tag stays as a YAML comment for human readability + a `last-known-good` provenance note. Renovate runs weekly, opens grouped PRs proposing digest bumps; PRs are reviewed and merged manually.

### Option D — Sigstore / cosign verification at admission time

Beyond digest pinning: require every image to carry a cosign signature, verified at the cluster's admission webhook (via `policy-controller` or Gatekeeper with a sigstore-aware ConstraintTemplate).

**Deferred, not rejected.** This is the right end-state but adds a signing pipeline, a key-management surface, and an admission dependency that the platform doesn't have today. Worth a follow-up ADR once the platform has at least one image being built by the operator's own infrastructure that needs trust beyond "we control the GHCR repository." For now, digest pinning + Renovate is the 80% solution.

---

## Decision

**Pin every first-party and critical-path container image to its SHA-256 digest. Keep the originating tag as a comment for human readability. Manage bump cadence via Renovate.**

| Image | Old reference | New reference (digest) |
|---|---|---|
| `ghcr.io/calmafterreboot/bls-llm-gateway` | `:latest` | `@sha256:c67e10e8…` (single-arch manifest) |
| `ghcr.io/berriai/litellm` | `:main-latest` | `@sha256:7c311546…` (multi-arch index) |
| `redis` (Docker Hub) | `:7-alpine` | `@sha256:6ab0b6e7…` (multi-arch index) |
| `stefanprodan/podinfo` | `:6.7.0` | **left as `:6.7.0`** — see exception below |

For multi-arch images, the index digest is pinned (not the per-platform manifest). Kubernetes pulls the right architecture from the index automatically; pinning the index keeps content addressability without locking to a single platform.

### Exception list

- **`stefanprodan/podinfo`** stays at `:6.7.0`. Rationale: it's a portfolio demo workload, not a critical-path service. Its purpose is to be the "hello world" thing that lights up the matrix ApplicationSet — losing the demo because podinfo's tag floated is a low-cost failure mode. Documenting the exception here avoids the audit ever flagging it as drift from this ADR.

### Renovate config

`.github/renovate.json` is the live source of truth. Highlights:

- **`pinDigests: true`** for every Kubernetes manager (`kubernetes`, `helm-values`, `argocd`) on Docker datasources. Renovate appends `# renovate: image=<tag>` comments automatically so the human-readable tag survives every bump.
- **Weekly schedule** (`before 6am on Monday, Europe/London`) for container-image digest sweeps. Grouped into one PR per week so review effort stays bounded.
- **Monthly schedule** (first day of month) for Helm-chart version bumps. Separate group so chart upgrades aren't mixed with image bumps.
- **Vulnerability alerts override the schedule** — Renovate's `vulnerabilityAlerts.enabled: true` opens out-of-band PRs labelled `security` when GHSA flags a known CVE in a pinned image.
- **`automerge: false`** globally — every digest bump is a manual review. The point of pinning is to make the bump deliberate; auto-merge would defeat it.
- **`stefanprodan/podinfo` is `pinDigests: false`** — codifies the exception.

---

## Rationale

- **Cryptographic vs lexical identity.** A digest is the content; a tag is a pointer to content. The cluster's pull contract should reference the content, not the pointer. This is the same logic that argued against trusting upstream `:latest` for ten years — we're just finally applying it to ourselves.
- **Renovate is the cadence belt.** Without an automated bump pipeline, digest pinning becomes either (a) frozen-in-amber (the cluster runs old images forever, missing security fixes) or (b) a chore the operator never has time for. Renovate's weekly grouped PR puts the bump on a schedule the operator can actually keep.
- **Comments preserve the human story.** A reviewer looking at `image: ghcr.io/foo@sha256:c67e10e8…` learns nothing; with the tag comment, the line reads as "this is `:latest` as of 2026-05-28, pinned for safety." Cognitive cost of digest pinning drops sharply.
- **The Renovate PR is itself the audit trail.** When a digest bump merges, the PR body contains the old → new diff, the source-of-truth tag, and the rationale (Renovate's "what changed" comment). Better than a periodic out-of-band review of running images.

---

## Consequences

- **ArgoCD `selfHeal: true` becomes safer.** Without digest pinning, selfHeal could pull a different image on every reconcile if the registry changed. With pinning, selfHeal pulls exactly what's in `main`, every time.
- **Image bumps cluster on Mondays.** Renovate's weekly schedule produces one grouped PR per week (Monday morning). Operator reviews + merges; that's the "bumping process." Fits a sprint-style workflow.
- **CI cost grows minimally.** Renovate runs as a GitHub-hosted bot; no compute on the cluster. The only repo-side cost is the CI pipeline that runs on the bump PRs (the same pipeline that runs on any PR — `terraform-ci.yml`, pre-commit, helm template).
- **Gatekeeper enforces this at admission time** ([ADR-016](ADR-016-policy-as-code-gatekeeper.md)). The `K8sImageDigestPinned` ConstraintTemplate rejects any Pod whose container image string lacks `@sha256:`. After dryrun + violation review, this flips to `deny` — meaning a regression that drops digest pinning is blocked at apply time, not caught months later in an audit.
- **Two-stage rollout protects against breaking the cluster on day one.** Constraints land at `enforcementAction: dryrun` so existing violations are reported, not blocked. The operator audits the dryrun report (kept at `docs/runbooks/gatekeeper-violations-baseline.md`); only when violations are zero does a follow-up PR flip enforcement to `deny`.

---

## Review trigger

Revisit if any of the following becomes true:

1. **A signed-image / cosign verification flow is funded.** Then Option D becomes reachable, and digest pinning becomes the *fallback* layer rather than the primary trust boundary. Update this ADR + add a new "supply-chain verification" ADR alongside.
2. **Renovate is rate-limited or paywalled.** Substitutes: `dependabot` (less Helm/k8s coverage; would lose the digest-pinning manager), self-hosted Renovate on the homelab, or a hand-rolled `gh workflow` that periodically inspects manifests + opens PRs.
3. **A first-party image moves to a registry that doesn't support OCI digests.** Unlikely — GHCR, Docker Hub, ECR, GAR, ACR all do. Mentioned for completeness.
4. **Tag pinning is mandated by an external policy** (regulator, parent org, third-party security audit). Digest pinning is strictly stronger than tag pinning; combining both is fine but redundant.
