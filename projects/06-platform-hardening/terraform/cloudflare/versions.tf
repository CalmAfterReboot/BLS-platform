terraform {
  required_version = ">= 1.9.0"

  required_providers {
    cloudflare = {
      source = "cloudflare/cloudflare"
      # Pinned to the latest v4 line. v5 (current major) renamed most
      # resources (cloudflare_record -> cloudflare_dns_record, Zero
      # Trust resources reshaped) and ships a `tf-migrate` tool. The
      # v5 migration is a documented follow-up — this module's
      # resource names + the green plan are on v4. Bumping within v4
      # keeps maintenance fixes without the breaking rewrite.
      version = "~> 4.52"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}
