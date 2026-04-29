# ADR-002: Proxmox Homelab over Cloud-Only Development

## Status
Accepted

## Date
2026-04-29

## Context
The BLS portfolio requires a development environment for building and testing
containerised workloads before deploying to Azure. The options were:
- Cloud-only: Azure VMs for all development work
- Hybrid: Proxmox homelab for local development, Azure for production demos

## Decision
Use Proxmox homelab (128GB RAM, 6-core Xeon) as the primary development
environment, with Azure used only for production-grade portfolio deployments.

## Rationale
- Cost: Azure dev VMs running 8+ hours/day would breach the £60 total budget
  within weeks. Homelab has zero marginal cost per hour.
- Latency: Local iteration cycles are faster — no upload/download overhead
  for container images during development
- Realism: Running pfSense, VLANs, and managed switching locally mirrors
  enterprise network architecture more accurately than cloud-only
- Skill signal: Demonstrating hybrid infrastructure competency (on-prem + cloud)
  is a stronger portfolio signal than cloud-only for DevOps roles

## Consequences
- Azure spend is preserved for portfolio deployments that need to be
  publicly demonstrable (AKS, Landing Zone, etc.)
- Local environment requires maintenance (Proxmox, pfSense, VLAN config)
- Development workflow: build/test locally on k3s, promote to AKS for
  portfolio-grade deployment
- Single point of failure on homelab hardware — acceptable for dev,
  not for production

## Alternatives Considered
- Azure Dev VMs: Rejected on cost grounds
- GitHub Codespaces: Rejected — no network namespace or systemd access,
  cannot simulate infrastructure behaviour accurately
