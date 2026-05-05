#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="$SCRIPT_DIR/../terraform"
INVENTORY_FILE="$SCRIPT_DIR/../ansible/inventory/hosts.yml"

cd "$TERRAFORM_DIR"

echo "Fetching Terraform outputs..."
TF_OUTPUT=$(terraform output -json)

{
  echo "---"
  echo "all:"
  echo "  children:"
  echo "    k3s_cluster:"
  echo "      children:"
  echo "        k3s_control:"
  echo "          hosts:"
  echo "$TF_OUTPUT" | jq -r '
    .control_plane_ips.value
    | to_entries
    | sort_by(.key)[]
    | "            \(.key):\n              ansible_host: \(.value)"
  '
  echo "        k3s_worker:"
  echo "          hosts:"
  echo "$TF_OUTPUT" | jq -r '
    .worker_ips.value
    | to_entries
    | sort_by(.key)[]
    | "            \(.key):\n              ansible_host: \(.value)"
  '
  echo "  vars:"
  echo "    ansible_user: ansible"
  echo "    ansible_ssh_private_key_file: ~/.ssh/bls_ansible_ed25519"
} > "$INVENTORY_FILE"

echo "Inventory written to $INVENTORY_FILE"
