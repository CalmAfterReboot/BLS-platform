# ADR-012 — Cloudflare Zero Trust Exposure: Tunnel + Access for the Public Routes

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-05-25 |
| **Project** | BLS Project 6 — Platform Engineering (Stream A) |
| **Deciders** | BLS DevOps |

---

## Context

P5 closed with three useful surfaces — Grafana (kube-prometheus-stack), ArgoCD, and the LLM gateway — each reachable only via `kubectl port-forward`. Every demo, every shared screenshot, every recruiter walkthrough requires either a recorded session or the operator at the keyboard. The platform has nothing to show that a third party can click through.

The constraints on opening this up:

- **No static operator IP.** Home connection is dynamic; rotating an IP allow-list weekly is not a sustainable hardening posture.
- **No VPN client install for recruiters.** A portfolio-quality demo cannot start with "install WireGuard." Anyone landing from a LinkedIn link should be one email away from a working Grafana view.
- **No public inbound port on the homelab firewall.** Opening `:443` on the operator's residential connection makes the homelab a discoverable target on Shodan within a day.
- **Free-tier-only cost discipline.** P3's AKS teardown (ADR-002 cap of £60) sets the precedent: Cloudflare's free Zero Trust tier (50 users) is the budget.
- **Defense in depth, not perimeter-only.** Whatever fronts the cluster must be one of several authentication layers, not the only one.

The question this ADR settles: how do Grafana, ArgoCD, and the gateway become publicly reachable without violating any of the above?

---

## Options Considered

### Option A — Public LoadBalancer Service + Cloudflare proxy + IP allow-list

Expose each app via a LoadBalancer / NodePort, point Cloudflare at it as a proxied DNS record, restrict via Cloudflare WAF rules to the operator's current IP.

**Rejected.** Two failures:

1. **IP churn.** Residential dynamic IP means the allow-list rotates weekly. The operator either ends up locked out, or the allow-list grows into a stale wildcard.
2. **Recruiter access is blocked.** The whole point is third-party demos; an IP allow-list defeats it.

### Option B — Self-hosted VPN (WireGuard / Tailscale free tier)

Stand up WireGuard or use Tailscale's free tier. Operator + recruiters install a client. Cluster is reachable over the mesh; nothing is publicly exposed.

**Rejected.** Recruiter UX is the blocker: "install Tailscale, set up an account, accept an invite, run it, then come back and click this link" loses 90% of the audience before the first paint of Grafana. Self-hosted WireGuard adds an additional service to keep alive at a tier the operator does not have a paging rotation for.

### Option C — Cloudflare Tunnel + Cloudflare Access *(selected)*

A `cloudflared` Deployment in the cluster initiates an outbound mTLS tunnel to Cloudflare's edge — no inbound port on the homelab firewall. Cloudflare Access enforces authentication at the edge before any request touches the cluster: operator email + MFA (24h session) for all three apps; one-time-PIN to any email (1h session) for Grafana only, on the recruiter path.

The defense-in-depth chain becomes four layers:

1. **Cloudflare Access** (edge) — PIN or MFA, before any byte reaches the cluster.
2. **Backend auth** (in-cluster) — Grafana login form still on, ArgoCD admin still on, gateway Bearer-token middleware still on. If Cloudflare Access is bypassed (account compromise, edge bug, tunnel impersonation), the backend still refuses anonymous traffic.
3. **NetworkPolicy** (namespace) — cloudflared's egress is scoped to public HTTPS + the three target namespaces only. A compromised cloudflared pod cannot reach `monitoring-controller`, `argocd-application-controller`, the etcd plane, or anything cross-namespace not on the explicit list. ADR-009 covers the llm-gateway side of this.
4. **ArgoCD RBAC** (account) — the `viewonly` local account, behind both CF Access and backend login, can read state but cannot `apps:sync`, cannot `applicationsets:*`, cannot exec. The admin account remains reachable only via local `kubectl port-forward`, not via the public hostname.

### Option D — Public Ingress with backend-only auth

Open Traefik/nginx Ingress directly, rely entirely on each backend's own auth.

**Rejected.** No rate limiting, no MFA enforcement, exposes the infrastructure (server version, TLS fingerprint, IP) to passive crawlers, and the cluster's NetworkPolicy stops at the ingress namespace so any compromise spreads laterally. Single-layer auth fails the "defense in depth, not perimeter-only" constraint.

---

## Decision

**Adopt Cloudflare Tunnel + Access (Option C). Manage tunnel + DNS + Access policies via Terraform under `projects/06-platform-hardening/terraform/cloudflare/`. Run `cloudflared` as a 2-replica in-cluster Deployment under `k8s/workloads/cloudflared/`, gated by ArgoCD with `automated: prune=false, selfHeal=false`.**

Recruiter access: one-time-PIN to any email, **scoped to `grafana.bluelayersystems.com` only**. 1-hour session. ArgoCD and the gateway are *operator-only* (MFA), 24-hour session. The recruiter path never reaches a control-plane surface.

---

## Rationale

- **Outbound-only tunnel.** No new public port on the homelab firewall; `cloudflared` initiates the connection. The operator's home IP stays unadvertised; the cluster is not on any public CIDR scan list.
- **Edge auth before backend auth.** A request that never reaches the cluster cannot exhaust kube-apiserver, cannot probe backend auth weaknesses, cannot saturate ingress controllers.
- **Recruiter PIN is the right trade-off for this audience.** Portfolio reviewers won't tolerate an account-creation flow; PIN-to-any-email is the lowest-friction primitive Cloudflare offers that still produces an audit trail of which email accessed which app and when.
- **1-hour recruiter session caps abuse.** A leaked PIN code is valid for one hour after issuance, not forever. A leaked session token expires by the time it is sold on. (Operator MFA at 24h trades convenience against the same risk — operator account compromise is a higher-tier event with its own response, not a session-length problem.)
- **PIN abuse mitigations.** Cloudflare's Access rate-limits OTP issuance per source IP and per destination email. A bot rotating millions of throwaway emails to brute-force the PIN space is bounded by CF's edge rate limit before it touches the cluster. The recruiter-only scope means PIN-issued sessions cannot reach the gateway, cannot reach ArgoCD, cannot reach anything that costs money or controls state.
- **Manual sync gate.** ArgoCD `prune: false, selfHeal: false` on the cloudflared Application means tunnel state mutations are operator-initiated commits, not autonomous reconciliation loops. A regression in this chart will not delete the live tunnel.

---

## Consequences

- **Dependency on Cloudflare.** If Cloudflare's free Zero Trust tier is discontinued or terms change to disallow this use case, the public routes go dark until a replacement (Tailscale Funnel, self-hosted reverse proxy + WireGuard for operator + email-link auth for recruiters) is in place. The review trigger below names this explicitly.
- **`cloudflared` adds an in-cluster pod fleet.** 2 replicas (~100 m CPU / 128 MiB each), HA against single-worker loss. Negligible at this scale.
- **Tunnel credentials are operationally sensitive.** Stored as a `SealedSecret` in the `cloudflared` namespace; rotation is a runbook step, not an emergency hotpath. See [`docs/runbooks/cloudflared-tunnel.md`](../runbooks/cloudflared-tunnel.md).
- **Grafana / ArgoCD / gateway gain a second authentication boundary.** Existing backend auth is *not* disabled — defense in depth requires both. The recruiter PIN is one factor at the edge; whatever the backend asks for (Grafana login form, ArgoCD `viewonly` password, gateway Bearer token) is the second factor.
- **DNS becomes Cloudflare-managed for three subdomains.** `grafana.bluelayersystems.com`, `argocd.bluelayersystems.com`, `gateway.bluelayersystems.com` resolve to `<tunnel-id>.cfargotunnel.com`. If the zone moves off Cloudflare, the records move too.
- **Terraform state for Cloudflare resources** lives in the existing Azure Storage backend under key `projects/06-platform-hardening/cloudflare/dev.tfstate` — same blob, different key, no new credential surface.

---

## Review trigger

Revisit this decision if any of the following becomes true:

1. **Cloudflare changes Zero Trust free tier terms** to disallow this use case (size limits, paywall on OTP, geographic restrictions). Replacement candidates: Tailscale Funnel (free tier limited to one operator), Pomerium self-hosted, Authentik self-hosted in front of a public Ingress.
2. **Recruiter PIN abuse becomes material** — meaning either Cloudflare flags repeated OTP rate-limit breaches against this account, or audit logs show high-volume access from bot-style email patterns. Tighter scope (explicit allow-list of recruiter emails) is a 30-minute Terraform change away.
3. **A second portfolio property** (the BLS website's own dashboard, a Cloudflare-Worker-based widget) requires the same exposure pattern — generalise into a reusable Terraform module under `modules/cloudflare/` rather than continuing to expand `projects/06-platform-hardening/terraform/cloudflare/main.tf`.
4. **The homelab gains a static IP or migrates to a colo with a static IP** — Option A becomes viable for operator paths; PIN flow can stay for recruiters or be retired in favour of a public docs site.
