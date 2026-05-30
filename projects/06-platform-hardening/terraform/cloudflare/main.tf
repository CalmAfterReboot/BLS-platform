# Cloudflare Zero Trust public-exposure module for the BLS platform.
# See docs/adr/ADR-012-cloudflare-zero-trust-exposure.md for the
# decision record and threat model.

# Zone lookup by name avoids hardcoding the hex zone_id. If the zone
# is not in the authenticated account the plan fails with a clear error.
data "cloudflare_zone" "this" {
  name = var.zone_name
}

# Tunnel secret is generated locally and base64-encoded for the
# Cloudflare API. The same secret is embedded in the credentials.json
# the operator seals into the cluster post-merge (see runbook).
resource "random_id" "tunnel_secret" {
  byte_length = 32
}

resource "cloudflare_zero_trust_tunnel_cloudflared" "this" {
  account_id = var.account_id
  name       = var.tunnel_name
  secret     = random_id.tunnel_secret.b64_std
  config_src = "cloudflare"
}

# Ingress rules for the tunnel — published to Cloudflare's edge.
# Each hostname routes to the corresponding in-cluster service. The
# 404 catch-all at the end is required by cloudflared.
resource "cloudflare_zero_trust_tunnel_cloudflared_config" "this" {
  account_id = var.account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.this.id

  config {
    dynamic "ingress_rule" {
      for_each = var.hostnames
      content {
        hostname = "${ingress_rule.key}.${var.zone_name}"
        service  = ingress_rule.value
        # HTTPS upstreams (e.g. argocd-server with its self-signed cert)
        # get no_tls_verify so cloudflared doesn't reject the cert.
        dynamic "origin_request" {
          for_each = startswith(ingress_rule.value, "https://") ? [1] : []
          content {
            no_tls_verify = true
          }
        }
      }
    }

    ingress_rule {
      service = "http_status:404"
    }
  }
}

# CNAME per hostname → <tunnel-id>.cfargotunnel.com. Proxied through
# Cloudflare (orange-cloud) so traffic terminates at the edge.
resource "cloudflare_record" "tunnel" {
  for_each = var.hostnames

  zone_id = data.cloudflare_zone.this.id
  name    = each.key
  type    = "CNAME"
  value   = "${cloudflare_zero_trust_tunnel_cloudflared.this.id}.cfargotunnel.com"
  proxied = true
  ttl     = 1 # 1 = "automatic" when proxied
  comment = "Managed by terraform — ${var.tunnel_name} tunnel"
}

# NOTE: we deliberately do NOT manage a one-time-PIN identity provider
# resource. Cloudflare Zero Trust ships a built-in One-Time-PIN login
# method enabled by default on every account, so the email-PIN flow is
# available without an IdP resource — and creating one via the API needs
# the "Access: Organizations, Identity Providers, and Groups" token scope
# that this token does not carry. Relying on the built-in method keeps
# go-live unblocked with the existing token scopes.

# One Access application per hostname.
resource "cloudflare_zero_trust_access_application" "app" {
  for_each = var.hostnames

  account_id                = var.account_id
  name                      = "${each.key}.${var.zone_name}"
  domain                    = "${each.key}.${var.zone_name}"
  type                      = "self_hosted"
  session_duration          = each.key == "grafana" ? "${var.recruiter_session_minutes}m" : "${var.operator_session_hours}h"
  auto_redirect_to_identity = false
  app_launcher_visible      = false
  # Empty = all enabled account login methods are offered. With only the
  # built-in One-Time-PIN enabled, every app presents the email-PIN flow.
  allowed_idps = []

  depends_on = [cloudflare_record.tunnel]
}

# Operator policy on every app — email + MFA, 24h session.
resource "cloudflare_zero_trust_access_policy" "operator" {
  for_each = var.hostnames

  account_id     = var.account_id
  application_id = cloudflare_zero_trust_access_application.app[each.key].id
  name           = "Operator"
  precedence     = 1
  decision       = "allow"

  # The gate is the email include above: only the operator's email is
  # allowed, authenticated via the account's built-in One-Time-PIN.
  # No `require` block — the original auth_method=mfa was dropped (no
  # MFA IdP configured; it would lock the operator out of argocd/gateway
  # which have no fallback policy), and we don't pin a specific
  # login_method so no IdP resource is needed. To restore true MFA later,
  # add a Google/GitHub OAuth IdP + `require { auth_method = "mfa" }`.
  include {
    email = var.operator_emails
  }
}

# Recruiter policy — ONLY on grafana, one-time PIN to any email, 1h.
resource "cloudflare_zero_trust_access_policy" "recruiters" {
  account_id     = var.account_id
  application_id = cloudflare_zero_trust_access_application.app["grafana"].id
  name           = "Recruiters"
  precedence     = 2
  decision       = "allow"

  # Everyone may request access; the built-in One-Time-PIN means each
  # visitor must prove control of an email before the policy passes.
  # 1-hour session is set on the grafana application (session_duration).
  include {
    everyone = true
  }
}
