# BLS Project 3 — Multi-Cluster GitOps: AKS + k3s via ArgoCD

**Blue Layer Systems DevOps Portfolio · Project 3 of N**

Demonstrates production-grade GitOps patterns at scale. A single ApplicationSet deployed to both a Proxmox-hosted k3s cluster (Project 2) and an Azure AKS cluster simultaneously — one Git repository, one deployment strategy, two target environments.

---

## Table of Contents

1. [Overview](#overview)
2. [Infrastructure](#infrastructure)
3. [Cost Management](#cost-management)
4. [Phase 1 — AKS Provisioning](#phase-1--aks-provisioning)
5. [Phase 2 — Cluster Registration](#phase-2--cluster-registration)
6. [Phase 3 — Multi-Cluster ApplicationSet](#phase-3--multi-cluster-applicationset)
7. [Results](#results)
8. [Teardown](#teardown)
9. [Troubleshooting Log](#troubleshooting-log)
10. [ADR-005](#adr-005)

---

## Overview

| Item | Detail |
|---|---|
| **What it builds** | AKS cluster provisioned alongside k3s (from Project 2), registered as second target in ArgoCD, same ApplicationSet deploying workload to both environments |
| **Demo workload** | `podinfo` — small Go HTTP server for testing deployments |
| **Stack** | Terraform (`azurerm` ~3.110), Azure AKS, ArgoCD v3.4.1, ApplicationSet matrix generator |
| **Demonstrates** | Multi-cluster GitOps — single `git push` deploys to k3s + AKS simultaneously |
| **Duration** | Ephemeral demo — spin up, capture screenshots, destroy (30 minutes) |

---

## Infrastructure

### Azure Resources

**AKS Cluster:**
- Name: `bls-aks-demo`
- Region: `uksouth`
- Resource group: `rg-bls-aks-demo`
- Node pool: single node, `Standard_D2pls_v6` (ARM-based, 2 vCPU, 8 GB RAM)
- Kubernetes version: latest stable
- Network plugin: Azure CNI
- Load balancer: Standard

**Terraform State Backend:**
- Account: `<AZURE_STORAGE_ACCOUNT>`
- Container: `tfstate`
- Key: `03-aks-multicluster.tfstate`
- Remote state in Azure Storage prevents local loss and enables multi-operator access

**Why Single Node?**

This is a demo cluster — not production. A single node cluster is sufficient to demonstrate GitOps deployment patterns:
- Reduces cost (no compute charges for control plane, minimal agent cost)
- Deploys in under 3 minutes
- Clusters are entirely disposable — destroy immediately after screenshots

### Registered Clusters in ArgoCD

| Cluster | Location | Registered as |
|---|---|---|
| `in-cluster` | Proxmox homelab (k3s) | Local ArgoCD instance |
| `bls-aks-demo` | Azure UK South (AKS) | External cluster, API credentials stored in `argocd-cluster-secret` |

---

## Cost Management

### Per-Session Cost

**Single 30-minute session:**

- AKS control plane: **FREE** (no charge for managed control plane with AKS Free tier)
- Standard_D2pls_v6 compute: ~£0.0968/hour = **~£0.05 for 30 minutes**
- Managed identity: **FREE**
- VNet, NSG, NIC: **FREE** (no separate charges)

**Total per session: < £0.10**

### Cost Discipline

**Always run `terraform destroy` immediately after capturing screenshots.** The AKS resource does not have automatic shutdown — it will incur costs if left running.

```bash
# After demo is complete
terraform destroy -auto-approve

# Cost: £0 until the next provisioning
```

---

## Phase 1 — AKS Provisioning

All infrastructure is defined in `terraform/`. The Terraform configuration dynamically calculates the AKS API server's DNS name and outputs kubeconfig credentials.

### Prerequisites

```bash
# Azure CLI authenticated to the correct subscription
az account show
az account set --subscription "<SUBSCRIPTION_ID>"  # if needed

# Terraform installed
terraform --version

# kubectl installed (for later cluster access)
kubectl version --client
```

### Check VM Quota

New Azure subscriptions have restricted VM family quotas per region. Always verify availability before provisioning.

```bash
# Check available vCPU quota in the target region
az vm list-usage --location uksouth --query "[?name.value=='standardDPSv6Family'].{Name:name.localizedValue, Limit:limit, CurrentValue:currentValue}"

# Expected output: sufficient quota for 2 vCPU (e.g., Limit: 100, CurrentValue: 0)
```

If quota is exhausted:
- Switch region (e.g., `eastus`, `westus2`)
- Switch VM family (e.g., `Standard_D2s_v5` if `v6` unavailable)
- Do **not** request quota increases for ephemeral clusters

### Initialize and Apply

```bash
cd terraform/

# Fetch the azurerm provider and modules
terraform init

# Plan the deployment
terraform plan

# Apply — fully automated (AKS takes ~2–3 minutes to deploy)
terraform apply -auto-approve
```

### Expected Output

```
Outputs:

cluster_name = "bls-aks-demo"
kubeconfig_path = "<temp file path>"
resource_group_name = "rg-bls-aks-demo"
```

The `kubeconfig_path` output points to a temporary kubeconfig file. Terraform configures kubectl context `bls-aks-demo` automatically.

### Verify Cluster Access

```bash
# List available contexts
kubectl config get-contexts

# Set the context to the new AKS cluster
kubectl config use-context bls-aks-demo

# Confirm connectivity
kubectl get nodes

# Expected: 1 node in Ready state
```

---

## Phase 2 — Cluster Registration

ArgoCD needs credentials to the AKS cluster. The registration process creates a ServiceAccount on AKS and stores its credentials in the ArgoCD control plane (running on k3s).

### Prerequisites

- ArgoCD is running on the k3s cluster (Project 2)
- You have both `kubeconfig` contexts configured:
  - `in-cluster` — k3s with local ArgoCD
  - `bls-aks-demo` — AKS cluster

### Register the Cluster

```bash
# Ensure you're connected to the AKS cluster
kubectl config use-context bls-aks-demo
kubectl get nodes

# Return to the k3s/ArgoCD context for registration
kubectl config use-context in-cluster

# Register the cluster with ArgoCD
argocd cluster add bls-aks-demo --name bls-aks-demo

# Output: created a ClusterRole, ClusterRoleBinding, and ServiceAccount on AKS
# The token is stored in a Secret on k3s: argocd-cluster-secret
```

### Verify Registration

```bash
# List all clusters registered with ArgoCD
argocd cluster list

# Expected output:
# NAME                      VERSION  STATUS   MESSAGE
# https://kubernetes.default  <v1.x>   Healthy  Cluster information ...
# https://bls-aks-demo-<hash>.hcp.uksouth.azmk8s.io:443  <v1.x>  Healthy  Cluster information ...
```

Both clusters should show `Healthy` status. If `Unhealthy`, verify network connectivity between k3s and AKS and check the secret in `argocd-cluster-secret`.

---

## Phase 3 — Multi-Cluster ApplicationSet

### Overview

A single ApplicationSet uses a **matrix generator** to combine two sources:

1. **Git directory generator** — discovers workload folders in the Git repository
2. **Clusters generator** — discovers all clusters registered with ArgoCD

Result: one Application per `(workload folder, cluster)` combination.

**Example:**
- Workloads: `podinfo`
- Clusters: `in-cluster`, `bls-aks-demo`
- Generated Applications: `podinfo-in-cluster`, `podinfo-bls-aks-demo`

### ApplicationSet YAML

The ApplicationSet is stored in the Git repository at `k8s/apps/app-of-apps.yaml`:

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

### Deploying the ApplicationSet

```bash
# From the k3s context (where ArgoCD is running)
kubectl config use-context in-cluster

# Apply the ApplicationSet
kubectl apply -f k8s/apps/app-of-apps.yaml

# Verify creation
kubectl get applicationset -n argocd

# Watch the matrix generator evaluate and create Applications
kubectl get applications -n argocd -w

# Expected output (after ~10 seconds):
# podinfo-bls-aks-demo    Synced   Healthy
# podinfo-in-cluster      Synced   Healthy
```

### Key Design Pattern

| Component | Responsibility |
|---|---|
| Matrix generator | Combines workload paths × clusters to generate Application manifests |
| Git directory generator | Discovers workload paths (`k8s/workloads/*/`) in the Git repo |
| Clusters generator | Discovers registered cluster APIs from ArgoCD |
| Naming convention | `{workload}-{cluster-name}` for each generated Application |

### Important: Regenerating After Cluster Registration

ArgoCD ApplicationSet controllers cache the cluster list when they first evaluate the matrix. **If you register a new cluster after the ApplicationSet is created, the new cluster will not appear in the matrix until the ApplicationSet is recreated.**

To add the newly registered cluster to existing workloads:

```bash
# Delete the ApplicationSet
kubectl delete applicationset bls-workloads -n argocd

# Recreate it (forces fresh matrix evaluation with new cluster list)
kubectl apply -f k8s/apps/app-of-apps.yaml

# Verify the new Applications are created
kubectl get applications -n argocd
```

---

## Results

### Multi-Cluster Deployment

After the ApplicationSet is deployed, both clusters are running the same workload from the same Git revision:

| Application | Target Cluster | Namespace | Status | Sync Status |
|---|---|---|---|---|
| `podinfo-bls-aks-demo` | AKS (uksouth) | `default` | Healthy | Synced |
| `podinfo-in-cluster` | k3s homelab | `default` | Healthy | Synced |

### Verifying Deployment

**On AKS:**

```bash
kubectl config use-context bls-aks-demo
kubectl get pods -n default
# NAME                       READY   STATUS    RESTARTS
# podinfo-<hash>             1/1     Running   0
```

**On k3s:**

```bash
kubectl config use-context in-cluster
kubectl get pods -n default
# NAME                       READY   STATUS    RESTARTS
# podinfo-<hash>             1/1     Running   0
```

**Via ArgoCD UI:**

Both Applications show:
- **Status:** `Healthy` (pods are Running)
- **Sync Status:** `Synced` (cluster state matches Git)
- **Last Sync:** timestamp
- **Repo:** same branch, same revision

### Screenshots

![ArgoCD Multi-Cluster — AKS](../../docs/screenshots/argocd-multicluster-aks.png)
*podinfo-bls-aks-demo in ArgoCD — deployed to AKS*

![ArgoCD Multi-Cluster — k3s](../../docs/screenshots/argocd-multicluster-k3s.png)
*podinfo-in-cluster in ArgoCD — deployed to k3s homelab*

---

## Teardown

### Immediate Destroy (Most Important)

AKS does not auto-shutdown. Leaving the cluster running will incur ongoing costs. **Always destroy immediately after the demo.**

```bash
cd 03-aks-multicluster/terraform/

# Destroy all AKS resources
terraform destroy -auto-approve

# Output: destroyed 1 resource (the AKS cluster + associated managed resources)
```

### Remove Cluster from ArgoCD

Once the AKS cluster is destroyed, remove it from ArgoCD to clean up stored credentials and avoid failed health checks:

```bash
# Get the server URL of the destroyed cluster (from kubeconfig history or terraform state)
# Typically: https://bls-aks-demo-<hash>.hcp.uksouth.azmk8s.io:443

argocd cluster rm https://bls-aks-demo-<hash>.hcp.uksouth.azmk8s.io:443

# Verify removal
argocd cluster list

# Expected: only `https://kubernetes.default` remains
```

### Optional: Delete Applications

If you want to clean up the generated Applications (optional — they'll be removed when the clusters are destroyed anyway):

```bash
kubectl delete applicationset bls-workloads -n argocd
```

---

## Troubleshooting Log

### Issue 1 — VM Size Not Available in Subscription

**Symptom:** `terraform apply` fails with:

```
Error: Code="BadRequest" Message="The VM size Standard_D2pls_v6 is not allowed in your subscription in this region."
```

**Cause:** New Azure subscriptions have restricted VM families by default. The specific SKU is not available in the selected region.

**Fix:** Check available sizes and switch to an available SKU:

```bash
# List available vCPU quotas in uksouth
az vm list-usage --location uksouth --query "[?contains(name.value, 'Family')].{Name:name.localizedValue, Limit:limit, Current:currentValue}"

# If standardDPSv6Family is exhausted, try:
# - Standard_D2s_v5 (previous generation, usually available)
# - Different region (e.g., westus2, eastus)
```

Update `terraform/main.tf` with the available SKU:

```hcl
vm_size = "Standard_D2s_v5"
```

Then `terraform apply` again.

**Lesson:** New subscriptions have restricted VM family quotas per region. Always check quota before writing Terraform. Do not request quota increases for ephemeral demo clusters — switching regions is faster.

---

### Issue 2 — Zero vCPU Quota for VM Family

**Symptom:** `terraform apply` fails with:

```
Error: Code="ErrCode_InsufficientVCPUQuota" Message="Insufficient quota remaining for quota type 'standardDPSv6Family' when adding 2 vCPU for VM size 'Standard_D2pls_v6'"
```

**Cause:** The entire quota for the VM family is exhausted (e.g., total quota 20 vCPU, already 20 allocated).

**Fix:** Switch region or VM family. Do not request quota increases.

```bash
# Option 1: Switch region in terraform.tfvars
location = "westus2"  # instead of uksouth

# Option 2: Switch VM family in terraform/main.tf
vm_size = "Standard_B2s"  # smaller, different family
```

Then `terraform destroy` the failed deployment (if partially created) and `terraform apply` again.

**Lesson:** Quota constraints are common on new subscriptions. Switching regions is faster than requesting quota increases. Document which region/family has available capacity for future sessions.

---

### Issue 3 — ApplicationSet Generating 1 Application Instead of 2 After Cluster Registration

**Symptom:** After registering the AKS cluster, the ApplicationSet shows only 1 generated Application (`podinfo-in-cluster`) instead of 2. Logs show:

```
generated 1 applications from matrix generator
```

**Cause:** ArgoCD ApplicationSet controllers cache the cluster list from the `clusters` generator when they first evaluate the matrix. Registering a new cluster does not trigger a matrix re-evaluation in the existing ApplicationSet. The controller only sees the cluster that existed at first evaluation.

**Fix:** Delete and recreate the ApplicationSet to force a fresh matrix evaluation:

```bash
# Delete the ApplicationSet (this does NOT delete the generated Applications)
kubectl delete applicationset bls-workloads -n argocd

# Wait a moment for the ApplicationSet to be removed
sleep 2

# Recreate it — now the matrix generator sees both clusters
kubectl apply -f k8s/apps/app-of-apps.yaml

# Verify two Applications are now generated
kubectl get applications -n argocd
# podinfo-bls-aks-demo
# podinfo-in-cluster
```

**Lesson:** ArgoCD ApplicationSet v3.4.1 caches generator results. New cluster registration does not automatically propagate into existing matrix generators — recreation is required. This is a known limitation being addressed in newer ArgoCD versions. Plan cluster registration **before** deploying the ApplicationSet if possible.

---

## ADR-005

**Status:** Pending — see [docs/adr/ADR-005-applicationset-matrix-pattern.md](../../docs/adr/ADR-005-applicationset-matrix-pattern.md)

**Topic:** Matrix ApplicationSet pattern for multi-cluster workload delivery.

**Decision:** Use a matrix ApplicationSet combining `git` directory generator and `clusters` generator to automatically create Applications for every (workload, cluster) combination.

**Key benefits:**
- Adding a new cluster automatically deploys all existing workloads to it — zero manifest updates required
- Adding a new workload directory automatically deploys to all clusters — zero manifest updates required
- Single policy point: all workloads, all clusters, synchronized from the single ApplicationSet definition

**Consequence:** ApplicationSet must be recreated after new cluster registration to update the cached cluster list (ArgoCD v3.4.1 behaviour).
