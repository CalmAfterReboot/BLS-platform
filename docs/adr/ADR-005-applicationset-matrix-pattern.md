# ADR-005 — Matrix ApplicationSet for Multi-Cluster Workload Delivery

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-05-07 |
| **Project** | BLS Project 3 — Multi-Cluster GitOps |
| **Deciders** | BLS DevOps |

---

## Context

After provisioning both a k3s homelab cluster (Project 2) and an AKS cluster (Project 3), ArgoCD needed to manage workload deployments to both environments simultaneously. The platform must support:

- Single Git repository containing all workload definitions
- Deploy the same workload to multiple clusters with no code duplication
- Easy scaling: adding a new cluster should automatically deploy existing workloads
- Easy scaling: adding a new workload should automatically deploy to all clusters

Three approaches were evaluated.

---

## Options Considered

### Option A — Individual Application Manifests per Cluster

Create one Application per workload per cluster. For `N` workloads and `M` clusters, maintain `N × M` Application manifests.

**Example:** 5 workloads × 2 clusters = 10 Application manifests (each manually kept in sync).

**Rejected.** Does not scale and violates DRY principle:
- Adding a 3rd cluster requires 5 new Application manifests
- Adding a new workload requires 2 new Application manifests
- Cluster-specific differences (labels, projects, namespaces) become difficult to track
- No single policy point — sync policy, project, or pruning rules must be updated in multiple places

---

### Option B — One ApplicationSet per Workload

Create one ApplicationSet per workload, using a `clusters` generator to target all registered clusters.

**Example:**
- `ApplicationSet: podinfo` → generates Applications for `podinfo-in-cluster`, `podinfo-bls-aks-demo`
- `ApplicationSet: llm-gateway` → generates Applications for `llm-gateway-in-cluster`, `llm-gateway-bls-aks-demo`

**Rejected.** Still requires manifest multiplication:
- Adding a new workload requires a new ApplicationSet manifest
- Synchronization policy is duplicated across ApplicationSet manifests
- No single source of truth for "which workloads deploy where"

---

### Option C — Matrix ApplicationSet *(selected)*

Create a single ApplicationSet using a `matrix` generator combining:

1. **Git directory generator** — discovers workload folders from the Git repository
2. **Clusters generator** — discovers all clusters registered with ArgoCD

Result: one Application per `(workload folder, cluster)` combination. New workloads and new clusters are discovered automatically.

---

## Decision

**Use a matrix ApplicationSet combining `git` directory generator and `clusters` generator to automatically generate Applications for all (workload, cluster) combinations.**

The ApplicationSet is deployed once and remains static. Scaling is achieved by:
1. Adding workload folders to `k8s/workloads/` → automatically deploys to all clusters
2. Registering new clusters with ArgoCD → automatically deploys all workloads to the new cluster

---

## Rationale

**Automatic discovery of workloads.** The `git` directory generator scans `k8s/workloads/*/` and treats each folder as a deployable workload. Adding a new folder automatically triggers discovery and deployment to all clusters — no ApplicationSet changes required.

**Automatic discovery of clusters.** The `clusters` generator lists all clusters registered with ArgoCD. Registering a new cluster in ArgoCD immediately makes it available as a target — no ApplicationSet changes required.

**Single policy point.** All workload deployments on all clusters share the same sync policy, project, pruning rules, and health assessment. Policy changes are made once and propagate uniformly.

**Scales to N×M combinations.** A 3×3 matrix (3 workloads, 3 clusters) generates 9 Applications — all from a single ApplicationSet. A 10×5 matrix (10 workloads, 5 clusters) generates 50 Applications seamlessly.

**Naming convention enforces clarity.** Generated Application names follow `{workload}-{cluster-name}`, making ownership and targeting obvious in the ArgoCD UI and kubectl.

---

## Consequences

### Positive

- **Platform scales automatically without manifest changes.** Registering a second cluster immediately results in Application objects for all workloads on that cluster.
- **Single source of truth for delivery policy.** Sync policy, health assessment, pruning, and project assignment are defined once in the matrix ApplicationSet.
- **Git-driven discovery.** Adding a workload is as simple as creating `k8s/workloads/new-workload/` with a kustomization or Helm chart — ArgoCD auto-discovers it.
- **Supports GitOps-first workflows.** New infrastructure (workloads, clusters) is integrated purely through Git commits — no kubectl imperative commands required.

### Negative

- **All workloads deploy to all clusters by default.** If cluster-specific filtering is needed (e.g., "machine learning workloads only on GPU nodes"), requires additional label selectors or `clusterSelector` logic in the ApplicationSet template. Fine-grained routing adds complexity.
- **ApplicationSet must be recreated after new cluster registration.** ArgoCD v3.4.1 caches the cluster list when the matrix generator first evaluates. Registering a new cluster does not trigger matrix re-evaluation in the existing ApplicationSet. Workaround: `kubectl delete applicationset` and reapply.
  - **Note:** Newer ArgoCD versions (3.5+) may address this with hot-reloading of cluster lists.
- **Single policy point is also a single failure point.** If the matrix ApplicationSet spec is incorrect, all generated Applications inherit the error. Requires careful testing of ApplicationSet changes before applying to production.

---

## Alternatives Rejected

| Alternative | Reason |
|---|---|
| Individual Application per cluster | O(N×M) manifests; does not scale; violates DRY |
| One ApplicationSet per workload | Still requires new manifests for each workload; no benefit over Option A beyond syntax |
| Helm umbrella chart with subchart inclusions | Requires templating language; less GitOps-pure than Application-based discovery; harder to debug in ArgoCD UI |
| Manual GitHub Actions workflow | Not GitOps; moves source of truth away from Git; requires custom CI/CD logic per cluster |

---

## Implementation

### ApplicationSet Template

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: bls-workloads
  namespace: argocd
spec:
  template:
    metadata:
      name: "{{ workload }}-{{ cluster.name }}"
      namespace: argocd
      labels:
        app: "{{ workload }}"
        cluster: "{{ cluster.name }}"
    spec:
      project: default
      source:
        repoURL: https://github.com/CalmAfterReboot/BLS-DevOps.git
        path: "k8s/workloads/{{ workload }}"
        targetRevision: HEAD
      destination:
        server: "{{ cluster.server }}"
        namespace: default
      syncPolicy:
        syncOptions:
        - CreateNamespace=true
        automated:
          prune: true
          selfHeal: true
  generators:
  - matrix:
      generators:
      - git:
          repoURL: https://github.com/CalmAfterReboot/BLS-DevOps.git
          revision: HEAD
          directories:
          - path: "k8s/workloads/*"
      - clusters:
          selector:
            matchLabels: {}  # Matches all registered clusters
```

### Deployment

```bash
kubectl apply -f k8s/apps/app-of-apps.yaml
kubectl get applications -n argocd

# Monitor Application generation
kubectl logs -n argocd -l app.kubernetes.io/name=applicationset-controller -f
```

### Future Enhancements

1. **Cluster filtering:** Add label selectors to limit workloads to specific cluster types (e.g., only deploy monitoring stack to production clusters)
2. **Per-workload sync policies:** Use ApplicationSet templates to define different sync intervals or pruning rules per workload
3. **Cross-cluster dependencies:** Extend the pattern to express workload ordering across clusters (e.g., database cluster before application cluster)
