# The Cloudflare provider authenticates via the CLOUDFLARE_API_TOKEN
# environment variable. Export it before `terraform plan` / `apply`:
#   export CF_API_TOKEN="<token>"
#   export CLOUDFLARE_API_TOKEN="$CF_API_TOKEN"
# The token must carry these scopes (per Cloudflare dashboard
# → My Profile → API Tokens → Create Token):
#   - Zone:DNS:Edit (on the bluelayersystems.com zone)
#   - Account:Cloudflare Tunnel:Edit
#   - Account:Access:Apps and Policies:Edit
provider "cloudflare" {}

provider "random" {}
