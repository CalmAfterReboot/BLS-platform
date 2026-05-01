#!/usr/bin/env bash
# BLS Ansible wrapper — run from the repo root or ansible/ directory
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANSIBLE_DIR="${SCRIPT_DIR}/../ansible"
PLAYBOOK="${ANSIBLE_DIR}/site.yml"

usage() {
  cat <<EOF
Usage: $(basename "$0") <command> [options]

Commands:
  run       Run the full playbook
  check     Dry-run (--check mode)
  syntax    Syntax check only
  ping      Ping all inventory hosts
  tags      List available tags

Options:
  -t TAGS   Comma-separated tags to run (e.g. -t ssh,ufw)
  -l LIMIT  Limit to specific hosts or groups
  -v        Verbose output (-vvv for debug)
  -h        Show this help

Examples:
  $(basename "$0") run
  $(basename "$0") run -t ssh,ufw
  $(basename "$0") check -t sysctl
  $(basename "$0") syntax
  $(basename "$0") ping
EOF
  exit 0
}

TAGS=""
LIMIT=""
VERBOSE=""

while getopts ":t:l:vh" opt; do
  case $opt in
    t) TAGS="$OPTARG" ;;
    l) LIMIT="$OPTARG" ;;
    v) VERBOSE="-vvv" ;;
    h) usage ;;
    *) echo "Unknown option: -$OPTARG" >&2; usage ;;
  esac
done

shift $((OPTIND - 1))
COMMAND="${1:-help}"

build_args() {
  local args=("$PLAYBOOK")
  [[ -n "$TAGS" ]]    && args+=("--tags" "$TAGS")
  [[ -n "$LIMIT" ]]   && args+=("--limit" "$LIMIT")
  [[ -n "$VERBOSE" ]] && args+=("$VERBOSE")
  echo "${args[@]}"
}

cd "$ANSIBLE_DIR"

case "$COMMAND" in
  run)
    echo "[bls-run] Running playbook..."
    # shellcheck disable=SC2046
    ansible-playbook $(build_args)
    ;;
  check)
    echo "[bls-run] Dry-run (check mode)..."
    # shellcheck disable=SC2046
    ansible-playbook --check --diff $(build_args)
    ;;
  syntax)
    echo "[bls-run] Syntax check..."
    ansible-playbook --syntax-check "$PLAYBOOK"
    ;;
  ping)
    echo "[bls-run] Pinging all hosts..."
    ansible all -m ping ${VERBOSE:-}
    ;;
  tags)
    echo "[bls-run] Available tags:"
    ansible-playbook --list-tags "$PLAYBOOK"
    ;;
  help|*)
    usage
    ;;
esac
