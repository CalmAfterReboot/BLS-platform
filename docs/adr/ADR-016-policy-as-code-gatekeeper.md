# ADR-016 — Policy-as-Code via OPA/Gatekeeper: Five Fitness Functions

| Field | Value |
|---|---|
| **Status** | Accepted (dryrun phase) |
| **Date** | 2026-05-28 |
| **Project** | BLS Project 6 — Platform Engineering (Stream C) |
| **Deciders** | BLS DevOps |

---

## Context

The platform has accumulated implicit conventions over P1–P5 that nothing enforces:

- All first-party images should be **digest-pinned** ([ADR-015](ADR-015-image-digest-pinning.md)) — but a future PR could re-introduce `:latest` and the cluster would happily reconcile it.
- All workload containers should declare **liveness + readiness probes** — but the matrix ApplicationSet doesn't lint manifests; a Deployment with no probes is invisibly broken (rolling updates believe pods are ready before they actually are).
- All resources should carry **owner / cost-center / environment labels** for downstream cost attribution and incident-response routing — but nothing checks at apply time.
- **NodePort Services** are inappropriate for this platform — the public surface is Cloudflare Tunnel ([ADR-012](ADR-012-cloudflare-zero-trust-exposure.md)), and NodePort exposes the homelab's worker IPs to LAN-direct routing. But a developer could ship one accidentally.
- **Containers running as root** are an unnecessary blast-radius increase. Pod Security Standards' `restricted` profile already disallows it, but the cluster runs the default `privileged` PSA — by design, because some early bootstrap workloads (Longhorn) need root. Per-resource policy is needed.

These are *fitness functions* in the sense Neal Ford uses the term in **Building Evolutionary Architectures** — automated checks that verify the system continues to meet the architectural characteristics it was designed for, run on every change. We've had the architectural intent. We haven't had the enforcement.

This ADR records the decision to adopt **OPA/Gatekeeper** as the policy engine and ships five initial ConstraintTemplates as the first generation of fitness functions.

---

## Options Considered

### Option A — Kyverno

Kubernetes-native policy engine. Policies are YAML (no Rego), with built-in support for mutation, image verification, and generation alongside validation.

**Considered, rejected for this round.** Kyverno's YAML-first language is operationally simpler than Rego for the basic cases here — but the trade-off is power: Rego is a full logic language, and once policies grow past simple field checks (e.g., the `K8sRequiredLabels` constraint's set difference operation, or future cross-resource policies looking at Service ↔ Endpoint consistency), Rego does what YAML can't. Gatekeeper's [community library](https://github.com/open-policy-agent/gatekeeper-library) has 100+ battle-tested templates we can adopt verbatim. The choice is *operational complexity now* vs *policy ceiling later* — and the policy ceiling will matter more as the platform grows.

### Option B — Gatekeeper + 5 initial fitness functions *(selected)*

Adopt OPA/Gatekeeper. Ship five ConstraintTemplates + matching Constraints, deployed as a Helm-managed Application alongside the gateway / monitoring / observability stacks. Constraints initially run in `enforcementAction: dryrun` (audit-only); flip to `deny` after 24 h of baseline observation confirms zero in-tree violations.

### Option C — Pod Security Admission (PSA)

Built-in Kubernetes admission for the three Pod Security Standards (`privileged`, `baseline`, `restricted`). No external dependency.

**Rejected as insufficient.** PSA only covers the security axis (and only the PSS profile axes — runAsNonRoot, allowedCapabilities, hostNetwork, etc.). Three of the five fitness functions here (`K8sRequiredLabels`, `K8sRequiredProbes`, `K8sImageDigestPinned`) are operational, not security-axis. PSA would handle `K8sPSPNoRoot` and `K8sBlockNodePort` only; we'd need a second policy engine for the rest. Two engines, two mental models, two audit trails.

### Option D — Validation in CI only (kube-conform, kubeconform, conftest)

Run the same Rego policies (or Kyverno YAML, or kube-conform CRD checks) as a pre-merge GitHub Action. Never blocks at admission; only catches PRs.

**Rejected as the primary layer, accepted as a complementary one (future).** Pre-merge validation is fast feedback, but anyone with `kubectl apply` access to the cluster bypasses it. The point of policy-as-code is to be a deterministic floor, not a courtesy. A future enhancement is to run the same Rego in CI via `conftest` against the rendered manifests — but it's an *addition* to Gatekeeper, not a substitute.

---

## Decision

**Deploy OPA/Gatekeeper via the upstream `open-policy-agent/gatekeeper` Helm chart. Ship five initial ConstraintTemplates + matching Constraints under an umbrella chart at `k8s/workloads/gatekeeper-constraints/`. Start at `enforcementAction: dryrun`; flip to `deny` after 24 h baseline observation.**

| ConstraintTemplate | Constraint name | Scope | Rejects |
|---|---|---|---|
| `K8sPSPNoRoot` | `psp-no-root` | All Pods (and Pod templates) | Containers without `securityContext.runAsNonRoot: true` |
| `K8sRequiredLabels` | `required-labels` | All namespaced workload kinds | Resources missing `owner`, `cost-center`, `environment` labels |
| `K8sRequiredProbes` | `required-probes` | Deployments + StatefulSets + DaemonSets | Containers without both `livenessProbe` and `readinessProbe` |
| `K8sBlockNodePort` | `block-nodeport` | All Services | `spec.type: NodePort` |
| `K8sImageDigestPinned` | `image-digest-pinned` | All Pod-spec-carrying kinds | Container `image` strings without `@sha256:` |

Each Constraint excludes `gatekeeper-system` from its `match.namespaceSelector` (the policy engine cannot policy itself into uninstallability) and the K8s system namespaces (`kube-system`, `kube-public`, `kube-node-lease`) from `K8sRequiredLabels` and `K8sRequiredProbes` (kube-system DaemonSets we don't own would otherwise be flagged forever).

---

## Rationale

### Why these five, in this order

The five chosen are the constraints that *match concrete, observed risk in this platform* — not a generic best-practice checklist. Each closes a specific failure mode the audit named:

- **No-root** closes the "compromised container = root on the worker node" blast-radius increase. Even with `runAsNonRoot` defaulting in the cluster's PSA, declarative enforcement at admission makes this auditable.
- **Required-labels** is the prerequisite for cost attribution. Without owner/cost-center/environment labels on every Pod, kube-prometheus-stack's cost-related queries (and future Azure Cost Management integration in Sequence 5) can't pivot by team or environment.
- **Required-probes** closes the silent-broken-rollout failure mode. A Deployment without probes is `Ready` at the instant the pod's process starts, regardless of whether it can serve traffic. Rolling updates that look healthy in `kubectl rollout status` but actually broke happen *because* of this.
- **Block-NodePort** closes the inadvertent-LAN-exposure failure mode in tandem with [ADR-012](ADR-012-cloudflare-zero-trust-exposure.md). The public path is Cloudflare Tunnel; NodePort would create a parallel public path that bypasses CF Access.
- **Image-digest-pinned** is the enforcement half of [ADR-015](ADR-015-image-digest-pinning.md). The ADR makes the rule; the Constraint catches anything that breaks it at apply time.

### Why dryrun before deny

Existing workloads predate the constraints. Flipping straight to `deny` would have one of two outcomes:

1. ArgoCD sync starts failing on any chart that doesn't comply yet — including third-party charts (kube-prometheus-stack, sealed-secrets) that we don't control. The cluster degrades because policy is stricter than reality.
2. Even after we've fixed our own charts, an upstream chart update could ship a new manifest that violates — and the cluster again refuses to reconcile until we fix it.

`dryrun` reports violations as Constraint status (`kubectl get constraints -A -o jsonpath='{.items[*].status.violations}'`) without rejecting the apply. The 24 h dryrun window gives the operator a measured view of the violation baseline. The follow-up PR that flips `dryrun` → `deny` is small, surgical, and the act of merging it represents a deliberate "we know the baseline is clean, now enforce." Without the staging, the rollout is a coin-flip.

### Why fitness functions (the framing)

Neal Ford and Patrick Kua's **Building Evolutionary Architectures** introduces fitness functions as the unit of architecture verification — a fitness function asserts a *characteristic* of the system that should remain true as the system evolves, and runs automatically. The mental shift Gatekeeper enables: every ConstraintTemplate is a fitness function. We declare what we believe about the platform (every workload has probes; every image is digest-pinned; every Service is ClusterIP) and Gatekeeper proves it on every reconcile.

The framing matters because it changes the question from "how do we lock the cluster down?" (a one-time security exercise) to "what architectural characteristics do we want to remain true?" (an ongoing engineering practice).

### Why an umbrella chart for constraints

A single Helm chart at `k8s/workloads/gatekeeper-constraints/` produces all five ConstraintTemplates + Constraints from one Application. Two practical wins:

- **One toggle per constraint.** `values.yaml` has booleans like `constraints.imageDigestPinned.enabled: true` so an operator can stage rollouts (turn one on, watch the report, turn the next on).
- **One enforcement-mode flip.** When the time comes to flip dryrun → deny, it's `enforcementAction: deny` in five places, one PR. Not a per-constraint dance.

---

## Consequences

- **Gatekeeper admission webhook is now in the apply path.** Every `kubectl apply` (including ArgoCD reconciles) blocks until the Gatekeeper webhook validates. The chart pins resource requests + readiness probes appropriately so the webhook itself stays available; if it fails, the cluster degrades to whatever its `failurePolicy` says (default: `Ignore`, so reconciles succeed even if policy is down — operational choice we accept).
- **Adding the sixth constraint costs ~20 lines.** Pattern is established: ConstraintTemplate (Rego) + Constraint (match criteria + parameters). Future additions (image-source allow-list, NetworkPolicy required-on-every-namespace, etc.) follow.
- **The `K8sRequiredLabels` constraint has a backfill cost.** Every existing in-tree resource needs the three labels added. That's a follow-up PR that goes alongside this one's flip-to-deny — done together so the deny isn't a surprise.
- **CI gains a `conftest` pre-merge check eventually** (deferred). Same Rego runs against the rendered manifests as a PR check; failures block before they hit the cluster. Today Gatekeeper at admission time is the only enforcement; that's acceptable for a single-operator platform.
- **`docs/runbooks/gatekeeper-violations-baseline.md`** is the operator-curated record of the dryrun-phase violations. Populated post-merge after 24 h. Used as evidence to justify the flip-to-deny PR.

---

## Review trigger

Revisit if any of the following becomes true:

1. **A multi-tenant requirement emerges.** Per-tenant Constraints (different rules for different namespaces) push Gatekeeper into more complex territory; Kyverno's policy hierarchy is friendlier there. Re-evaluate the Kyverno trade-off.
2. **Gatekeeper's admission latency starts hurting reconciles.** The webhook is in the critical path; if 99th-percentile admission latency climbs past 100 ms, look at constraint-evaluation profiling and consider per-Constraint disabling.
3. **A constraint becomes a frequent friction point** — operators routinely disabling it for a class of resources. That's evidence either the constraint is over-broad or the constraint's intent isn't real architecture; refine or remove.
4. **Image signing / cosign verification lands** ([ADR-015](ADR-015-image-digest-pinning.md) Option D). At that point, Gatekeeper grows a new family of ConstraintTemplates for signature verification, and image-pinning becomes one of several supply-chain fitness functions.
