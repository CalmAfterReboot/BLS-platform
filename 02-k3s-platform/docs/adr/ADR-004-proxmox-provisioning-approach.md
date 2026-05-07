# ADR-004 — Terraform + Ansible for Proxmox VM Provisioning

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-05-07 |
| **Project** | BLS Project 2 — k3s HA Platform on Proxmox |
| **Deciders** | BLS DevOps |

---

## Context

Five VMs (three k3s control plane, two worker) needed to be provisioned on a single Proxmox VE host to form a k3s HA cluster. The provisioning approach had to satisfy the following requirements:

- Reproducible: the entire cluster must be destroyable and rebuildable from code
- Auditable: changes to VM specifications must be reviewable as diffs
- Separated: infrastructure state (what exists) must be distinct from configuration state (how it's configured)
- Portfolio-aligned: must mirror patterns used in production cloud environments

Three approaches were evaluated.

---

## Options Considered

### Option A — Manual VM Creation via Proxmox UI

Provision each VM interactively through the Proxmox web interface, configuring CPU, memory, disk, and network by hand.

**Rejected.** Not reproducible — there is no artefact representing the desired state that can be version-controlled, diffed in code review, or used to recreate the cluster after a wipe. Each rebuild requires manual steps with no guarantee of consistency.

### Option B — Proxmox Built-in Cloud-Init Without Terraform

Use `qm clone` and `qm set` shell commands to clone VMs from the template and configure them via cloud-init, driven by an ad-hoc shell script.

**Rejected.** Provides reproducibility in the sense that a script can be re-run, but there is no state management — the script has no knowledge of what already exists, cannot plan changes, and cannot safely reconcile drift. Adding or removing nodes requires careful manual script editing with no plan/apply safety gate.

### Option C — Terraform (`bpg/proxmox`) + Ansible *(selected)*

Use Terraform with the `bpg/proxmox` provider for VM lifecycle management, backed by Azure Storage remote state. Use Ansible for post-provisioning configuration management. Generate the Ansible inventory automatically from Terraform outputs.

---

## Decision

**Use Terraform (`bpg/proxmox` 0.66.3) for VM lifecycle with Azure Storage remote state, and Ansible for post-provisioning node configuration. Inventory is generated automatically from Terraform outputs via `scripts/generate-inventory.sh`.**

The two tools own distinct, non-overlapping concerns:

| Layer | Tool | Owns |
|---|---|---|
| Infrastructure | Terraform | VM creation, destruction, resizing, network config, cloud-init bootstrap |
| Configuration | Ansible | Package state, SSH hardening, UFW rules, sysctl, auditd, NTP, fail2ban |
| Bootstrap only | cloud-init | First user (`ansible`), SSH public key, static IP — nothing else |

---

## Rationale

**Reproducible end-to-end rebuild.** `terraform apply` provisions all five VMs in under 60 seconds from a clean state. `ansible-playbook harden.yml` configures all five nodes idempotently. The entire cluster can be destroyed and rebuilt without manual steps.

**Separation of concerns.** Terraform owns infrastructure state; Ansible owns configuration state. Neither tool crosses into the other's domain. This boundary prevents the common failure mode where infrastructure and configuration tooling fight over the same resources.

**Portfolio alignment.** The Terraform + Ansible pattern mirrors what is used in production cloud environments (Azure, AWS, GCP). Using it here demonstrates the same skill set in a homelab context.

**Inventory generation removes manual handoff.** `scripts/generate-inventory.sh` reads `terraform output -json` and writes `ansible/inventory/hosts.yml` directly. There is no manual step between `terraform apply` and `ansible-playbook` — the inventory is always consistent with the actual deployed state.

**Provider version pinned at 0.66.3.** The `bpg/proxmox` provider has introduced breaking changes in minor releases. The version is explicitly pinned in `versions.tf` to prevent `terraform init -upgrade` from silently breaking the configuration. Any upgrade must be tested explicitly.

---

## Consequences

### Positive

- Full cluster rebuild is automated end-to-end. Any operator with the credentials and the repository can recreate the cluster from scratch.
- Terraform state is stored in Azure Storage — it survives local machine loss and supports multi-operator access with state locking.
- VM topology changes (adding a node, resizing memory) are a single edit to `locals.tf`, reviewable as a diff before `terraform apply` executes the change.
- The `plan` → `apply` gate means changes are always reviewed before they are made.

### Negative

- The `bpg/proxmox` provider requires a Proxmox API token with broad VM and datastore permissions. The token is sensitive and must be kept out of version control (`terraform.tfvars` is gitignored).
- Provider version must be managed carefully — `bpg/proxmox` is still maturing and breaking changes have appeared in minor versions. Do not run `terraform init -upgrade` without first reviewing the provider changelog.
- The cloud-init template (VM ID 9000) must be created manually as a one-time prerequisite. This step is not yet automated and is documented in [README.md — Phase 1](../../README.md#phase-1--cloud-init-template-proxmox-host). Automating template creation is a candidate for a future improvement.

---

## Alternatives Rejected

| Alternative | Reason rejected |
|---|---|
| Manual UI provisioning | Not reproducible; no version-controlled artefact; not portfolio-worthy |
| `qm clone` shell scripts | No state management; no plan/apply gate; unsafe to rerun against existing VMs |
| Ansible-only (`community.general.proxmox` module) | Weaker state management than Terraform; does not produce a lockable remote state; less alignment with target infrastructure role requirements |
