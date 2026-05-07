# Blue Layer Systems — DevOps Platform Portfolio

**A cloud platform engineered from first principles, demonstrating production-grade infrastructure practices.**

---

## What This Portfolio Is

Blue Layer Systems is a public, verifiable engineering identity built by a Cloud and DevOps engineer. Rather than completing online tutorials or guided labs, this portfolio demonstrates real, working infrastructure that solves actual architectural challenges.

Every project in this portfolio runs live in production-like environments. The code is version-controlled, the deployment processes are automated, and the decisions are documented. This isn't a showcase of theoretical knowledge — it's evidence of engineering capability.

The portfolio brand is consistent, the architecture evolves methodically, and each new project builds on the foundations laid by the previous one. By the end, you'll see how a complete, multi-environment platform comes together.

---

## What Has Been Built

### Project 1: Cloud Foundation (Azure Landing Zone)

Think of this as building a house before you move in — establishing a secure, compliant foundation that all future projects will run on top of.

A complete Azure cloud environment was built using infrastructure-as-code, following enterprise-grade governance patterns. The foundation includes isolated networks (one for shared infrastructure, another for workloads), security boundaries that deny all traffic by default, automatic logging and monitoring, and policy enforcement to keep cloud resources compliant.

Every decision was intentional. Network segments are separated so that if one environment is compromised, the others remain isolated. Security rules default to "block everything" and require explicit approval for each allowed connection. Compliance policies are in place to enforce tagging standards and geographic restrictions. All infrastructure is defined in Terraform, which means every change is reviewed before it's deployed and can be audited weeks later.

Why this matters: This is how enterprise cloud environments are actually built and governed. Most companies have either built this poorly or not at all. This project proves the ability to architect and implement a cloud foundation to production standards.

---

### Project 2: Private Cloud Platform (Kubernetes on Proxmox)

Having built the cloud foundation in Azure, the next step was to build a compute platform that can actually run applications — a Kubernetes cluster.

Rather than rely entirely on the cloud, this project builds a private cluster in a homelab environment using five Linux servers (three management servers that coordinate, two worker servers that run applications). The cluster is highly available — if any single management server fails, the other two take over automatically with no downtime.

What makes this challenging is the automation. All five servers were provisioned at the same time, not built manually. They were all hardened automatically using industry-standard security practices: disabling remote access for privileged users, enforcing strong encryption algorithms, monitoring access attempts, and tracking changes. It all happened in an automated workflow — push a button, five hardened servers appear ready to run applications.

The cluster handles real-world infrastructure problems. When DNS failed due to a misconfigured firewall rule on the network appliance, the problem was diagnosed and resolved. When an etcd (the cluster's memory) became corrupted after a mistyped command, the cluster was recovered. These aren't hypothetical problems — they happened and were solved.

Why this matters: Most engineers have only worked with managed Kubernetes services (like Azure's). Building and operating Kubernetes from bare metal demonstrates significantly deeper infrastructure capability. This includes diagnosing cluster failures, understanding distributed systems failure modes, and knowing how to recover from partial data corruption.

---

### Project 3: Multi-Cloud Delivery (GitOps with ArgoCD)

With both a cloud foundation and a compute platform built, the final piece is the delivery mechanism — how applications actually get deployed to production.

This project demonstrates GitOps, a deployment pattern where pushing code to GitHub automatically updates applications across multiple environments. A single application was deployed to both the private homelab cluster and to a public Azure Kubernetes Service cluster at the same time, from the same GitHub repository, with no manual intervention.

The power of this pattern is subtle but profound. Developers commit code to GitHub. Minutes later, the application is running on multiple clusters simultaneously. If something goes wrong, the fix is a git revert. The entire history of every deployment is in Git, not in some deployment tool. Infrastructure changes and application changes stay in sync because they're both in the same repository. Rollback is as simple as reverting a commit.

Why this matters: This is how modern platform teams deliver software reliability at scale. Every major technology company (Spotify, Netflix, Google) uses patterns like this. Demonstrating proficiency here signals knowledge of how modern infrastructure actually works in practice.

---

## How It All Connects

These three projects aren't isolated demonstrations. They're deliberately layered, each building on the previous one.

**Project 1 established the cloud foundation** — a secure, well-governed place to run infrastructure. It's the base layer.

**Project 2 built the compute platform** that will run applications. Whether that's the private homelab cluster or Azure's managed service, applications need somewhere to run.

**Project 3 wired them together** — a single mechanism that can deploy applications to any of these clusters. Push code, applications deploy everywhere.

The next project (Project 4, currently planned) will be the first production workload running on top of this platform — an AI gateway that routes requests to large language models. By that point, the entire stack will be in place: secure cloud foundation, highly available compute layer, and automated deployment mechanism.

This is how platform engineering works in reality. You build the layers in order, test each one thoroughly, document the decisions, and then when everything is in place, you can move at extraordinary speed because all the infrastructure is there to support it.

---

## Technical Depth Indicators

For technical reviewers who need to assess depth, here's what's under the hood:

| Category | Scope |
|---|---|
| **Cloud platforms** | Microsoft Azure (primary), AWS patterns studied |
| **Infrastructure-as-Code** | Terraform (Azure, Proxmox), modules for networking and security |
| **Kubernetes** | k3s (production-grade, lightweight), Azure AKS, Helm, Kustomize |
| **Deployment automation** | ArgoCD with multi-cluster patterns, matrix ApplicationSets, git-driven deployments |
| **Configuration management** | Ansible with reusable roles, idempotent playbooks, security hardening |
| **Network architecture** | Hub-spoke VNets, VLANs, NSG policies, network segmentation, firewall rules |
| **Security practices** | SSH key-based auth, DH moduli validation, auditd rules, PAM limits, fail2ban, UFW policies |
| **Observability** | Azure Log Analytics, NSG diagnostics, error tracking and incident documentation |
| **Incident response** | DNS resolution troubleshooting, etcd recovery, ArgoCD controller cache issues, VM quota management |

**Real incidents encountered and documented:**

- **DNS resolution failure:** Traced to a misconfigured NAT rule on a pfSense firewall redirecting DNS queries meant for a local resolver. Diagnosed with tcpdump and fixed by rule removal.
- **etcd corruption:** A mistyped join command on a Kubernetes node partially corrupted the cluster's distributed database. Resolved with full node reinstall and recreated kube-vip manifest.
- **ArgoCD ApplicationSet caching:** After registering a new cluster, the deployment system didn't immediately pick up the new cluster because internal caches weren't invalidated. Resolved by recreating the ApplicationSet manifest.
- **Azure VM quota exhaustion:** Attempted to provision a VM size not available in the target region. Diagnosed with `az vm list-usage` and resolved by switching regions.

**Architectural decisions documented:**

Five Architecture Decision Records (ADRs) document the reasoning behind key choices:
- ADR-002: Why hybrid homelab + cloud infrastructure instead of pure cloud
- ADR-003: Why Ansible instead of cloud-init for node configuration
- ADR-004: Why Terraform + Ansible instead of manual provisioning for VM management
- ADR-005: Why matrix ApplicationSets instead of individual Application manifests for multi-cluster delivery

---

## Portfolio Structure

The repository is organized for clarity:

```
BLS-DevOps/
├── projects/
│   └── 01-landing-zone/          Azure cloud foundation project
│
├── 02-k3s-platform/               Kubernetes cluster on homelab
│   ├── terraform/                 VM provisioning code
│   ├── ansible/                   Security hardening automation
│   └── scripts/                   Inventory generation
│
├── 03-aks-multicluster/           Multi-cloud deployment demonstration
│   ├── terraform/                 AKS provisioning code
│   └── k8s/                        Application manifests
│
├── docs/
│   ├── adr/                       Architecture decision records
│   └── screenshots/               Live deployment evidence
│
└── README.md                      This file

```

Each project has its own complete README with technical depth, design decisions, setup instructions, and troubleshooting guides. The docs/ folder contains architecture decision records explaining the reasoning behind each major choice.

---

## Current Status

**3 of 6 projects complete and running.** The portfolio is ahead of schedule for the planned timeline.

**Next phase:** Project 4 — an AI Gateway that routes requests to large language models, running on top of the completed platform infrastructure. This will be the first "real" application workload demonstrating the entire platform in production use.

**Timeline:** Project development is progressing methodically with full documentation at each stage. Each new project adds capability without disrupting previous work.

---

## Explore the Portfolio

Each project has complete technical documentation:

- **[Project 1 README](projects/01-landing-zone/README.md)** — Cloud foundation architecture, design decisions, security baseline
- **[Project 2 README](02-k3s-platform/README.md)** — Kubernetes cluster setup, node hardening, multi-phase provisioning
- **[Project 3 README](03-aks-multicluster/README.md)** — Multi-cluster GitOps, ApplicationSet patterns, deployment verification

**Architecture decision records** for deeper context on why things were built this way:

- [All ADRs](docs/adr/) — Complete decision history and rationale

**Live code:**

- [GitHub Repository](https://github.com/CalmAfterReboot/BLS-DevOps) — Complete source code, infrastructure definitions, deployment automation

---

## What This Demonstrates

**For hiring managers and recruiters:**

This portfolio shows the ability to:

- Design and build production-grade infrastructure from first principles
- Implement enterprise security and governance patterns
- Operate and troubleshoot distributed systems in production
- Automate complex deployment workflows
- Document architectural decisions and incident responses
- Work across multiple platforms (Azure cloud, homelab infrastructure, Kubernetes)
- Ship multiple complete projects to working, documented standards

This isn't a hiring signal based on certifications or online course completion. It's evidence of real engineering capability demonstrated through working infrastructure.

**For technical reviewers:**

The codebase demonstrates proficiency in infrastructure-as-code, Kubernetes operations, security hardening, multi-environment deployment patterns, and incident recovery. Real incidents were encountered and solved. Architectural decisions were made deliberately and documented. The code is clean, the automation is reliable, and the systems work.

---

## Questions?

Explore the projects directly on [GitHub](https://github.com/CalmAfterReboot/BLS-DevOps). Each project README has complete technical documentation, setup instructions, and troubleshooting guides.

For inquiries about platform engineering, DevOps practices, or infrastructure-as-code: reach out through your normal recruitment channels.

Blue Layer Systems — Production-grade infrastructure, built to last.
