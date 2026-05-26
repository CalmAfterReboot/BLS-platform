# Runbook — Cloudflared Tunnel

| Field | Value |
|---|---|
| **Owner** | BLS DevOps |
| **Backed by** | [ADR-012](../adr/ADR-012-cloudflare-zero-trust-exposure.md) |
| **Scope** | `cloudflared` Deployment in the `cloudflared` namespace + Cloudflare-side tunnel/DNS/Access state managed by `projects/06-platform-hardening/terraform/cloudflare/` |

This runbook covers initial setup post-PR-merge, routine operations (rotation, scale), and incident response (tunnel down, credential compromise, recruiter PIN abuse).

---

## Initial setup (one-time, post-PR-merge)

Order matters: Terraform creates the tunnel + DNS + Access policies, then the operator seals the tunnel credentials, then ArgoCD picks up the chart.

### 1. Apply the Cloudflare Terraform

```bash
cd projects/06-platform-hardening/terraform/cloudflare
cp backend.tfbackend.example backend.tfbackend
cp terraform.tfvars.example terraform.tfvars
# Edit both files — fill in the storage account name and your CF account_id + operator_email.
terraform init -backend-config=backend.tfbackend
export CLOUDFLARE_API_TOKEN="$CF_API_TOKEN"   # the provider reads CLOUDFLARE_API_TOKEN
terraform plan -out tfplan
# Review carefully — this provisions DNS records on bluelayersystems.com.
terraform apply tfplan
```

Capture the outputs:

```bash
TUNNEL_ID=$(terraform output -raw tunnel_id)
echo "$TUNNEL_ID"   # paste into k8s/workloads/cloudflared/values.yaml `tunnel.id`
```

### 2. Seal the tunnel credentials and commit the SealedSecret

The Terraform output `tunnel_credentials_json` carries the `credentials.json` payload that `cloudflared` needs to authenticate to its tunnel. Pipe it directly through `kubeseal` — **do not echo it to a shell, do not write it to a temporary file the shell can recover**.

```bash
terraform output -raw tunnel_credentials_json \
  | kubectl create secret generic cloudflared-credentials \
      --namespace cloudflared \
      --dry-run=client \
      --from-file=credentials.json=/dev/stdin \
      -o yaml \
  | kubeseal \
      --controller-namespace sealed-secrets \
      --controller-name sealed-secrets \
      --format yaml \
  > /tmp/cloudflared-credentials-sealed.yaml
```

Replace the placeholder in [`k8s/workloads/cloudflared/templates/secret-sealed.yaml`](../../k8s/workloads/cloudflared/templates/secret-sealed.yaml) with the `encryptedData.credentials.json` field from the generated YAML, commit, push.

Update the `tunnel.id` value in [`k8s/workloads/cloudflared/values.yaml`](../../k8s/workloads/cloudflared/values.yaml) in the same commit. ArgoCD picks up both changes on the next sync.

### 3. ArgoCD `viewonly` account setup

```bash
kubectl -n argocd patch configmap argocd-cm \
  --patch-file k8s/workloads/argocd-config/argocd-cm-patch.yaml

# RBAC patch — be careful if the live argocd-rbac-cm already has a
# custom policy.csv. Diff first:
kubectl -n argocd get cm argocd-rbac-cm -o yaml > /tmp/argocd-rbac-cm-before.yaml
kubectl -n argocd patch configmap argocd-rbac-cm \
  --patch-file k8s/workloads/argocd-config/argocd-rbac-cm-patch.yaml

# Set the viewonly password. Choose a strong random; store in
# OPERATOR-PRIVATE.md or a 1Password vault.
argocd login argocd.bluelayersystems.com --grpc-web   # via CF Access (operator MFA)
argocd account update-password \
  --account viewonly \
  --current-password <admin-password> \
  --new-password <strong-random-password>
```

### 4. Verify

```bash
# Check the tunnel is registered with Cloudflare
cloudflared tunnel list --origincert <your-cert>

# Check the cloudflared pods are Running
kubectl -n cloudflared get pods

# Hit each public hostname from outside the homelab — expect the
# Cloudflare Access challenge page.
curl -I https://grafana.bluelayersystems.com   # operator path = MFA challenge
curl -I https://argocd.bluelayersystems.com    # operator path = MFA challenge
curl -I https://gateway.bluelayersystems.com   # operator path = MFA challenge

# Hit grafana from an incognito browser without auth — expect the
# PIN-request screen. Submit an email; the PIN arrives in seconds.
```

---

## Incident — tunnel down (no replicas Ready)

**Symptom:** `kubectl -n cloudflared get pods` shows 0/2 Ready, or external `curl https://grafana.bluelayersystems.com` returns Cloudflare 530.

**Triage:**

```bash
kubectl -n cloudflared logs -l app.kubernetes.io/name=cloudflared --tail=200
```

Common patterns:
- `error="failed to read credentials file"` → the SealedSecret hasn't been filled in or sealed-secrets controller hasn't decrypted yet. Check `kubectl -n cloudflared get secrets`.
- `error="origin certificate has expired"` → tunnel credentials rotation overdue. Re-run "Initial setup" step 2 to issue fresh credentials.
- `error="ingress rule X does not match any hostname"` → ConfigMap drift from the Terraform-side tunnel config. Re-apply Terraform OR update `values.yaml ingress` to match.

**Recover:**

```bash
# Force a redeploy (picks up sealed-secret rotation, config changes)
kubectl -n cloudflared rollout restart deployment/cloudflared
kubectl -n cloudflared rollout status deployment/cloudflared --timeout=2m
```

If the tunnel itself has been deleted Cloudflare-side, re-run `terraform apply` (it will recreate the resource and emit a new tunnel ID — back to "Initial setup" step 2 with the new ID).

---

## Incident — credentials suspected compromised

**Symptom:** Cloudflare Audit log shows access-app changes you did not make, or `terraform plan` shows drift against resources you did not modify, or the operator notices an unfamiliar tunnel in `cloudflared tunnel list`.

**Rotate:**

```bash
cd projects/06-platform-hardening/terraform/cloudflare
# Force the tunnel_secret to regenerate:
terraform taint random_id.tunnel_secret
terraform apply -out tfplan-rotate
```

The tunnel ID stays the same; the credentials change. Re-run "Initial setup" step 2 to re-seal and commit.

Rotate the Cloudflare API token at the same time (dashboard → My Profile → API Tokens → Roll). Export the new value into `$CF_API_TOKEN` before the next Terraform run.

---

## Incident — recruiter PIN abuse

**Symptom:** Cloudflare Access audit log shows unusually high OTP request volume against `grafana.bluelayersystems.com`, or repeated PIN entries from a single source IP that look bot-driven.

**Immediate:**

1. Tighten the recruiter policy via Terraform — replace `include { everyone = true }` with an explicit allow-list:

   ```hcl
   resource "cloudflare_zero_trust_access_policy" "recruiters" {
     # ...
     include {
       email = [
         "verified.recruiter1@example.com",
         "verified.recruiter2@example.com",
       ]
     }
   }
   ```

   `terraform apply` — recruiters who were not on the allow-list are immediately blocked.

2. Pull the Cloudflare Access audit log for the offending window:

   ```bash
   # Cloudflare API call (token needs Account:Access:Apps Read)
   curl -H "Authorization: Bearer $CF_API_TOKEN" \
     "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/access/logs/access_requests?since=2026-05-24T00:00:00Z" \
     | jq '.result[] | select(.app_domain == "grafana.bluelayersystems.com")'
   ```

**Follow-up:**

- Re-evaluate the PIN trade-off in ADR-012 under the "Review trigger" §2.
- If the abuse continues despite the allow-list, escalate to Cloudflare support and consider Bot Fight Mode on the zone.

---

## Routine — Cloudflare API token rotation

Every 90 days, or whenever the token is suspected stale:

1. Dashboard → My Profile → API Tokens → Roll on the BLS-platform token.
2. Export new value into `$CF_API_TOKEN`. Also update any CI secret if the token is used there (currently it is not — manual `terraform apply` only).
3. `terraform plan` — should be no drift; the token is auth, not state.

---

## Routine — cloudflared image bump

1. Check the [Cloudflare releases page](https://github.com/cloudflare/cloudflared/releases) for the latest stable version.
2. Update `image.tag` in [`k8s/workloads/cloudflared/values.yaml`](../../k8s/workloads/cloudflared/values.yaml) AND the workstation `cloudflared --version` should match (operator-local `cloudflared tunnel` commands must speak the same tunnel-credentials format as the in-cluster daemon).
3. Commit, push, ArgoCD syncs.
4. Watch `kubectl -n cloudflared rollout status` — confirm both replicas Ready before walking away.
