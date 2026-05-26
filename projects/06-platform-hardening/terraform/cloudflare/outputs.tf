output "tunnel_id" {
  description = "Cloudflare tunnel UUID. Required by the cloudflared Deployment's credentials.json (which the operator generates and seals post-merge — see docs/runbooks/cloudflared-tunnel.md)."
  value       = cloudflare_zero_trust_tunnel_cloudflared.this.id
}

output "tunnel_cname_target" {
  description = "FQDN that every public hostname CNAMEs to. Useful for verification (`dig CNAME grafana.bluelayersystems.com` should resolve to this)."
  value       = "${cloudflare_zero_trust_tunnel_cloudflared.this.id}.cfargotunnel.com"
}

output "tunnel_credentials_json" {
  description = "credentials.json content for the cloudflared Deployment. Sensitive — pipe directly to kubeseal, do not echo to a shell or commit to git. See docs/runbooks/cloudflared-tunnel.md step 2."
  value = jsonencode({
    AccountTag   = var.account_id
    TunnelID     = cloudflare_zero_trust_tunnel_cloudflared.this.id
    TunnelName   = cloudflare_zero_trust_tunnel_cloudflared.this.name
    TunnelSecret = random_id.tunnel_secret.b64_std
  })
  sensitive = true
}

output "hostnames" {
  description = "Resolved FQDNs the tunnel publishes."
  value       = { for k, _ in var.hostnames : k => "${k}.${var.zone_name}" }
}

output "access_application_ids" {
  description = "Cloudflare Access application IDs, keyed by short hostname. Useful when wiring Audit or downstream tooling against the Access API."
  value       = { for k, v in cloudflare_zero_trust_access_application.app : k => v.id }
}
