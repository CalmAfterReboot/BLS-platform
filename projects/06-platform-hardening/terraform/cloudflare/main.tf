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

# One-time-PIN identity provider for the recruiter policy.
resource "cloudflare_zero_trust_access_identity_provider" "otp" {
  account_id = var.account_id
  name       = "one-time-pin"
  type       = "onetimepin"
}

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
  allowed_idps              = each.key == "grafana" ? [cloudflare_zero_trust_access_identity_provider.otp.id] : []

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

  include {
    email = [var.operator_email]
  }

  require {
    auth_method = "mfa"
  }
}

# Recruiter policy — ONLY on grafana, one-time PIN to any email, 1h.
resource "cloudflare_zero_trust_access_policy" "recruiters" {
  account_id     = var.account_id
  application_id = cloudflare_zero_trust_access_application.app["grafana"].id
  name           = "Recruiters"
  precedence     = 2
  decision       = "allow"

  include {
    everyone = true
  }

  require {
    login_method = [cloudflare_zero_trust_access_identity_provider.otp.id]
  }
}
