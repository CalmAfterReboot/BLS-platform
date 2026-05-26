# ArgoCD config patches

ArgoCD itself is not currently managed via ArgoCD (chicken-and-egg from the original bootstrap). This directory holds **patches** to the live `argocd-cm` and `argocd-rbac-cm` ConfigMaps, applied manually by the operator until a self-management Application lands.

Each patch is a minimal additive change — they do **not** replace the live ConfigMap, only merge new keys in.

## Files

| File | Patches | Purpose |
|---|---|---|
| `argocd-cm-patch.yaml` | `argocd-cm` | Declares a `viewonly` local account (login + apiKey both enabled). |
| `argocd-rbac-cm-patch.yaml` | `argocd-rbac-cm` | Defines `role:viewonly` (read-only verbs across applications / projects / repositories / clusters) and grants it to the `viewonly` account. |

## Why these exist

ArgoCD is now exposed publicly via Cloudflare Tunnel + Access (ADR-012). The admin account remains intact for operator-local-network use; `viewonly` is the only credential safe to leak if the Cloudflare Access layer is ever bypassed.

The recruiter Access policy in [ADR-012](../../../docs/adr/ADR-012-cloudflare-zero-trust-exposure.md) is scoped to **grafana only** — recruiters never see ArgoCD. The `viewonly` user is defense in depth, not a recruiter path.

## Apply

See [`docs/runbooks/cloudflared-tunnel.md`](../../../docs/runbooks/cloudflared-tunnel.md) §"ArgoCD viewonly account setup" for the exact `kubectl patch` + `argocd account update-password` recipe.

## Future direction

Promote ArgoCD to a self-managed Application (its own `k8s/apps/argocd.yaml`) so these patches become regular chart values, not manual `kubectl patch` steps. Tracked as a follow-up.
