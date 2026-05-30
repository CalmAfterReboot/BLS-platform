variable "account_id" {
  description = "Cloudflare account ID that owns the zone, the tunnel, and the Access apps. Find it in the Cloudflare dashboard right-hand sidebar (URL: dash.cloudflare.com/<account_id>)."
  type        = string
}

variable "zone_name" {
  description = "Apex DNS name of the Cloudflare zone (e.g. bluelayersystems.com). The zone_id is resolved at plan time via a data source — no need to paste a hex ID."
  type        = string
  default     = "bluelayersystems.com"
}

variable "tunnel_name" {
  description = "Human-readable name for the cloudflare_zero_trust_tunnel_cloudflared resource."
  type        = string
  default     = "bls-platform"
}

variable "operator_emails" {
  description = "Email addresses allowed on all three apps via the Operator policy (one-time-PIN, 24h session). Any of these emails may authenticate."
  type        = list(string)
}

variable "hostnames" {
  description = "Map of subdomain -> upstream service URL. Each subdomain becomes a CNAME + Access app. The upstream is what cloudflared forwards to in-cluster."
  type        = map(string)
  default = {
    "grafana" = "http://kube-prometheus-stack-grafana.monitoring.svc.cluster.local:80"
    # argocd-server redirects HTTP->HTTPS (307); forwarding plain HTTP
    # behind the TLS-terminating tunnel causes a redirect loop. Send it
    # over HTTPS instead — no_tls_verify is set for https upstreams in
    # the tunnel config (main.tf) since argocd-server uses a self-signed cert.
    "argocd" = "https://argocd-server.argocd.svc.cluster.local:443"
    # Verified against the live cluster: the gateway Service is
    # `llm-gateway-service` on :8000 (not `gateway:80`).
    "gateway" = "http://llm-gateway-service.llm-gateway.svc.cluster.local:8000"
  }
}

variable "recruiter_session_minutes" {
  description = "Length of the recruiter one-time-PIN session in minutes. Default 60 per ADR-012 trade-off."
  type        = number
  default     = 60
}

variable "operator_session_hours" {
  description = "Length of the operator MFA session in hours. Default 24 — long enough for a working day without needing to re-auth."
  type        = number
  default     = 24
}
