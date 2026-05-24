# Operator Handbook (template)

> Template for the **operator-private** handbook every operator of this
> platform should maintain locally. The filled-in version lives at the
> repo root as `OPERATOR-PRIVATE.md` and is **gitignored** — see the
> rule in [`.gitignore`](../../.gitignore).
>
> This template is intentionally generic. Copy it to
> `OPERATOR-PRIVATE.md` at the repo root and fill in your environment's
> values. Do **not** commit the filled-in version.

## Why this file exists

A platform of this complexity has dozens of credentials, URLs, and
rotation procedures spread across cloud subscriptions, cluster
secrets, local `.env` files, and the operator's password manager.
The operator handbook is the **single index** that answers, for any
given credential or URL:

- **What it is.**
- **Where the live value lives** (not the value itself — a *pointer*
  to where it can be read).
- **How to rotate it** (the exact command or procedure).
- **When it expires** (calendar cadence, if applicable).

The file is reference-only. **No literal passwords, tokens, or
private keys belong in this file**, even though it is gitignored.
The pattern is: "look up the live value via this `kubectl` command",
"see entry `X` in your password manager", "read from `~/.env`". If
the file leaks (lost laptop, disk forensics, accidental upload),
no credential is directly compromised.

## Required sections

Every operator's filled-in handbook should carry at least these
sections:

### 1. Quickstart — getting from zero to a working operator session

A short numbered list, ten lines or fewer. The output of running
the list is a shell that can `kubectl get pods -A`, has `kubeseal`
on PATH, and has the right Azure subscription selected. No
secrets in this section — credentials come from steps in the
sections below.

### 2. Live URLs and access paths

A table of every operationally-relevant URL. Includes:

- **ArgoCD UI** — port-forward command and resulting `localhost`
  URL. ArgoCD is not exposed publicly on the homelab.
- **Grafana UI** — port-forward command and resulting URL.
- **Prometheus UI** — same.
- **LLM gateway** — both the Ingress (`<chart-ingress-host>`)
  and a port-forward fallback.
- **LiteLLM proxy** — port-forward to the in-cluster service for
  direct routing inspection.
- **Kubernetes API** — `kubectl cluster-info` output for the active
  context. Note which contexts are reachable (e.g. `default` for
  the homelab, `bls-aks-demo` for AKS when re-enabled).
- **Proxmox UI** — homelab hypervisor URL.
- **Azure Portal** — `portal.azure.com` + the subscription's
  tenant-scoped login URL.
- **GitHub repository** —
  `https://github.com/CalmAfterReboot/BLS-platform`.
- **GHCR registry** — `ghcr.io/calmafterreboot/<image>`.

Each row carries the *command to reach the URL* (port-forward, az
login etc.), not the resulting URL alone — so re-creating a stale
port-forward is one-line.

### 3. Credential index

A table or section per credential, ordered by blast radius. For
each credential, four facts:

| Field | Example |
|---|---|
| **What** | "ArgoCD `admin` UI password" |
| **Where the live value lives** | `kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' \| base64 -d` |
| **Rotation procedure** | "Delete the secret; ArgoCD regenerates on next sync. Then re-record this row." |
| **Expiry / cadence** | "No automatic expiry. Rotate quarterly or on operator handoff." |

Minimum credentials to cover (this list scales with the platform):

- ArgoCD admin UI password
- Sealed-secrets controller's active and rotated-out private keys
  (and the off-workstation backup location)
- `llm-gateway-secrets` payload — the three sealed keys and how to
  read each one
- OpenAI prepay API key — file path (`.env`) and cost cap
- LiteLLM master key — sealed in `llm-gateway-secrets`, decrypts
  with the gateway pod's secretKeyRef mount
- Grafana admin password
- Azure subscription / tenant identifiers (kept here, redacted in
  public docs)
- Azure service-principal credentials used by Terraform CI
  (`ARM_CLIENT_ID`, `ARM_CLIENT_SECRET`, `ARM_TENANT_ID`,
  `ARM_SUBSCRIPTION_ID`) — names of GitHub Actions secrets, plus a
  password-manager pointer for the underlying SP secret
- Proxmox API token and SSH credentials used by Terraform
- GitHub Personal Access Token (PAT) used by GHCR push
- SSH key used by Ansible to reach k3s nodes
- The kubeseal master cert (public — fetched from the cluster;
  pin it locally for offline re-sealing)

### 4. Renewal calendar

A simple bulleted list of credentials with explicit calendar
cadence. Examples:

- **OpenAI prepay**: balance check monthly; top up before <£2;
  $10 hard cap configured at the OpenAI dashboard.
- **GitHub PAT**: 90-day expiry; renew the week before.
- **Azure service principal secret**: 12-month expiry; renew the
  month before with `az ad sp credential reset`.
- **Sealed-secrets controller key**: no automatic expiry; verified
  backups quarterly.

### 5. Operational toolkit

Commands that get used often enough that retyping them is friction:

- `kubeseal --controller-namespace=sealed-secrets
  --controller-name=sealed-secrets --fetch-cert` — re-fetch the
  current sealing cert.
- The full sealing-cmd for `llm-gateway-secrets` re-seals (see
  `k8s/workloads/llm-gateway/SECURITY.md`).
- `kubectl rollout restart deployment/<X> -n <ns>` to pick up new
  Secrets without a configmap diff.
- `terraform init -backend-config=backend.tfbackend -reconfigure`
  per project root.

## Editing rules

The file is reference-only. Treat it like documentation, not like
a vault. **Do not paste live secret values into this file** — even
though it is gitignored, plaintext on disk is its own blast
radius. If a section is tempted to include the value rather than
a pointer to it, that section is in the wrong file.

Update this file when:

- A credential is rotated (rotation procedure or password-manager
  entry name may change).
- A new credential is introduced.
- A port-forward target moves (e.g. Grafana behind Ingress in the
  future).
- A cluster context is added or removed.
- The Azure subscription or tenant changes.

## On rotation

When a credential is rotated, treat the value as compromised
between the old issuance time and the rotation timestamp, no
matter how unlikely a leak. Walk through what the credential
could have reached during that window and revoke any derived
artefacts (signed tokens, cached sessions) the leak could have
produced. Then update this handbook to reflect the new rotation
date.

## Backup of the operator-private handbook

The filled-in handbook is gitignored, so it lives in plaintext
on the operator's workstation only. Disk loss (lost laptop,
failed drive, reformat, malware ransom) destroys the index.

The standard backup pattern is a GPG-symmetric-encrypted copy of
the handbook, stored anywhere the operator wants — USB key,
cloud backup, private Gist. The encrypted blob is opaque without
the passphrase, so cloud-sync services do not see the contents.
`*.gpg` is in the repo-root `.gitignore` as a safety net.

### Create the backup

Run from the repo root. GPG will prompt for a passphrase twice.
Use a strong passphrase and **store it in your password manager**
under the same vault entry that references this handbook.

```bash
gpg -c --output OPERATOR-PRIVATE.md.gpg OPERATOR-PRIVATE.md
```

The output is encrypted with AES-256 (GPG 2.x default symmetric
cipher).

### Decrypt to recover

```bash
gpg --output OPERATOR-PRIVATE.md --decrypt OPERATOR-PRIVATE.md.gpg
```

### Re-encrypt after an edit

```bash
# --yes overwrites the existing .gpg without prompting
gpg -c --yes --output OPERATOR-PRIVATE.md.gpg OPERATOR-PRIVATE.md
```

### Round-trip test (verify the backup is good)

```bash
# Print only the first 20 lines to stdout — leaves no plaintext on disk
gpg --decrypt OPERATOR-PRIVATE.md.gpg | head -20
```

A clean round-trip output is the only confirmation that:

- The `.gpg` file is not corrupt.
- Your password-manager entry holds the correct passphrase.

### Backup cadence

Re-encrypt after every meaningful edit to the handbook. A stale
backup is worse than no backup — it gives false reassurance.

---

*This is the template. The filled-in version lives in
`OPERATOR-PRIVATE.md` at the repo root, gitignored. The encrypted
backup is `OPERATOR-PRIVATE.md.gpg`, also gitignored.*
