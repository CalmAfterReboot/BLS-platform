# ADR-003: Ansible over Cloud-Init for Node Configuration

**Status:** Accepted  
**Date:** 2026-05-01  
**Author:** BLS DevOps

---

## Context

The BLS homelab requires a repeatable, auditable method of applying a security baseline to Ubuntu 24.04 nodes. Two primary options were evaluated:

1. **Cloud-Init** — a YAML-driven, first-boot configuration system baked into Ubuntu cloud images.
2. **Ansible** — an agentless, idempotent configuration management tool driven by SSH or local connection.

Cloud-Init runs once at first boot and is well-suited for bootstrapping immutable infrastructure. Ansible runs on-demand and is designed for iterative, day-2 operations on long-lived nodes.

The target environment is a homelab node (`192.168.200.50`) that will be re-hardened over time as security requirements evolve, rather than torn down and reprovisioned on every change.

---

## Decision

**Use Ansible** for node hardening via an `ansible_connection: local` playbook executed on the node itself.

---

## Rationale

| Criterion | Cloud-Init | Ansible |
|---|---|---|
| Re-runnable after first boot | No (one-shot) | Yes (idempotent) |
| Drift correction | None | `--check --diff` detects and fixes drift |
| Change auditing | systemd journal only | `--diff` output, git history of role |
| Incremental hardening | Full reprovision required | Add tasks, re-run |
| Dry-run support | None | `--check` mode |
| Community hardening content | Limited | Extensive (Galaxy roles, posix/general) |
| Local execution (no SSH key needed) | Native | `ansible_connection: local` |
| Integration with CI/CD | Complex | Native via `ansible-playbook` in pipeline |

The decisive factors are **re-runnability** and **drift correction**. Cloud-Init cannot safely re-apply configuration after the first boot without custom scripting that recreates what Ansible already provides. The `--check` and `--diff` flags give operators a safe preview of any change before it is applied, which is critical for a production-adjacent homelab.

---

## Consequences

### Positive
- Security baseline changes are applied by re-running the playbook — no node reprovisioning.
- `ansible-playbook ansible/site.yml --check --diff` acts as a continuous compliance checker.
- Tags (`-t ssh`, `-t ufw`, etc.) allow surgical re-application of individual controls.
- The role can be extended to additional nodes by adding entries to `inventory/hosts.yml`.
- `bls-run.sh` provides a consistent, documented interface for day-2 operations.

### Negative / Trade-offs
- Ansible must be installed on the control node (or the target node itself for local runs).
- First-boot bootstrapping still requires either Cloud-Init or a manual `apt install ansible` step before the playbook can run.
- Secrets (SSH keys, vault passwords) must be managed separately — not addressed by this role.

---

## Alternatives Considered

### Cloud-Init only
Rejected. One-shot execution model does not support iterative hardening. Any change to the baseline requires full node reprovisioning, which conflicts with a homelab where the node accumulates state (monitoring, logs, local services).

### Chef / Puppet
Rejected. Require a persistent agent and a central server (Chef Server, Puppet Master). Complexity and resource overhead are disproportionate for a single-node homelab.

### Shell scripts
Rejected. Not idempotent by default. Significant engineering effort to achieve the same safety guarantees Ansible provides out of the box.

---

## References

- [ADR-002: Homelab over Cloud-Only Development](ADR-002-homelab-over-cloud-only.md)
- [Ansible posix collection](https://github.com/ansible-collections/ansible.posix)
- [CIS Ubuntu 24.04 Benchmark](https://www.cisecurity.org/benchmark/ubuntu_linux)
- [NCSC UK — Device Security Guidance](https://www.ncsc.gov.uk/collection/device-security-guidance)
