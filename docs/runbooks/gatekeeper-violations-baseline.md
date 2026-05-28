# Runbook — Gatekeeper Constraint Violations Baseline

| Field | Value |
|---|---|
| **Owner** | BLS DevOps |
| **Backed by** | [ADR-016](../adr/ADR-016-policy-as-code-gatekeeper.md) |
| **Scope** | The five initial Constraints shipped by `k8s/workloads/gatekeeper-constraints/`, currently in `enforcementAction: dryrun` |

This runbook is the operator-curated record of the **dryrun-phase violations** for each Constraint. The pre-merge state is a placeholder; the operator populates each section after 24 h of dryrun observation post-merge. Once all five violation counts are at zero (or the remaining violations are documented exceptions), a follow-up PR flips `enforcementAction: dryrun` → `enforcementAction: deny` per the staged rollout in [ADR-016 §"Why dryrun before deny"](../adr/ADR-016-policy-as-code-gatekeeper.md).

---

## How to collect

```bash
# Overview — one line per constraint, current violation count
kubectl get constraints -A -o wide

# Per-constraint detail — names every offending resource
for c in psp-no-root required-labels required-probes block-nodeport image-digest-pinned; do
  echo "=== $c ==="
  kubectl get $(kubectl get crds -o name | grep gatekeeper | xargs -I{} kubectl get {} -o name 2>/dev/null) \
    --all-namespaces \
    -o jsonpath='{range .items[?(@.metadata.name=="'$c'")]}{.status.violations[*].name}{"\n"}{end}'
done

# Single Constraint deep dive
kubectl get k8simagedigestpinned image-digest-pinned -o yaml \
  | yq '.status.violations'
```

## Baseline observation

Captured: `<DATE — operator fills in 24h after merge>`

| Constraint | Violations | Expected? | Action |
|---|---|---|---|
| `psp-no-root` | TBD | | |
| `required-labels` | TBD | | |
| `required-probes` | TBD | | |
| `block-nodeport` | TBD | | |
| `image-digest-pinned` | TBD | | |

### Notes per constraint

#### `psp-no-root`
TBD. Expected offenders: any third-party chart that hardcodes `runAsUser: 0`. Mitigation: chart-level values override, or per-namespace exception via `match.namespaceSelector` if a chart cannot be made compliant.

#### `required-labels`
TBD. Likely needs backfill of `owner=bls-devops`, `cost-center=portfolio`, `environment=homelab` on every in-tree Deployment/Service/ConfigMap. Treat as a follow-up PR that lands alongside the flip-to-deny PR — the labels must be added before deny goes live.

#### `required-probes`
TBD. Expected clean for first-party workloads (gateway, LiteLLM, Redis, cloudflared, otel-collector — all have probes). Third-party chart components may lack probes; document on a per-component basis.

#### `block-nodeport`
TBD. Expected clean — public exposure goes through Cloudflare Tunnel (ADR-012), no in-tree Service uses NodePort.

#### `image-digest-pinned`
TBD. Expected offenders post-merge: any pod created from a Helm chart whose values still reference a tag (the matrix won't flip those during this PR; Renovate's first run + ADR-015 application sweeps them over time). Exceptions documented in `values.yaml` (`stefanprodan/podinfo`).

---

## Flip-to-deny PR (follow-up)

Once the table above is filled in and all five rows show 0 violations (or the non-zero rows have a documented `match.namespaceSelector` or values-level exception):

1. Open a new branch from `main` named `p6/3-flip-to-deny`.
2. Edit `k8s/workloads/gatekeeper-constraints/values.yaml`:
   ```diff
   - enforcementAction: dryrun
   + enforcementAction: deny
   ```
3. Update this runbook with the final baseline table (replace TBDs with measured counts).
4. Open a small PR titled `chore(p6.3): flip Gatekeeper constraints to enforcementAction=deny`.
5. After merge + sync, run the verification step from [ADR-016 §Verification (deliberately non-compliant test)] to confirm the webhook rejects a known-bad manifest.

---

## Verification — deliberately non-compliant manifest

After the flip-to-deny PR merges, confirm enforcement is live by attempting to apply a deliberately bad manifest:

```bash
cat <<'EOF' | kubectl apply -f - --dry-run=server
apiVersion: v1
kind: Pod
metadata:
  name: gatekeeper-canary-non-compliant
  namespace: default
spec:
  containers:
    - name: canary
      image: nginx:latest   # violates image-digest-pinned
      # no probes -> violates required-probes (Pod kind directly)
      # no securityContext.runAsNonRoot -> violates psp-no-root
EOF
# Expected: kubectl returns admission webhook rejection with 3 violations.
```

If the apply succeeds, Gatekeeper is not enforcing — investigate `kubectl logs -n gatekeeper-system -l control-plane=controller-manager`.
