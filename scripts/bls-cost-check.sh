#!/usr/bin/env bash
# BLS Azure cost summary — requires Azure CLI (az) logged in
set -euo pipefail

SUBSCRIPTION="${AZURE_SUBSCRIPTION_ID:-}"
TIMEFRAME="${1:-MonthToDate}"
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-}"

usage() {
  cat <<EOF
Usage: $(basename "$0") [timeframe] [--rg RESOURCE_GROUP]

Timeframes: MonthToDate (default) | LastMonth | WeekToDate | TheLastMonth
  --rg  Filter by resource group name

Requires:
  - Azure CLI installed (az)
  - Active login (az login) or service principal env vars:
      AZURE_SUBSCRIPTION_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID

Examples:
  $(basename "$0")
  $(basename "$0") LastMonth
  $(basename "$0") MonthToDate --rg bls-landing-zone-rg
EOF
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --rg) RESOURCE_GROUP="$2"; shift 2 ;;
    -h|--help) usage ;;
    MonthToDate|LastMonth|WeekToDate|TheLastMonth) TIMEFRAME="$1"; shift ;;
    *) echo "Unknown argument: $1" >&2; usage ;;
  esac
done

if ! command -v az &>/dev/null; then
  echo "[bls-cost] ERROR: Azure CLI not found. Install from https://docs.microsoft.com/en-us/cli/azure/install-azure-cli" >&2
  exit 1
fi

if [[ -z "$SUBSCRIPTION" ]]; then
  SUBSCRIPTION=$(az account show --query id -o tsv 2>/dev/null || true)
fi

if [[ -z "$SUBSCRIPTION" ]]; then
  echo "[bls-cost] ERROR: No active Azure subscription. Run 'az login' first." >&2
  exit 1
fi

echo "[bls-cost] Subscription : $SUBSCRIPTION"
echo "[bls-cost] Timeframe     : $TIMEFRAME"
echo "[bls-cost] Resource Group: ${RESOURCE_GROUP:-<all>}"
echo ""

FILTER_ARG=""
if [[ -n "$RESOURCE_GROUP" ]]; then
  FILTER_ARG="--filter \"ResourceGroupName eq '$RESOURCE_GROUP'\""
fi

echo "=== Cost Summary ==="
# shellcheck disable=SC2086
az consumption usage list \
  --subscription "$SUBSCRIPTION" \
  --billing-period-name "$TIMEFRAME" \
  --query "[].{Service:instanceName, Cost:pretaxCost, Currency:currency}" \
  -o table ${FILTER_ARG:-} 2>/dev/null || \
az costmanagement query \
  --type "ActualCost" \
  --timeframe "$TIMEFRAME" \
  --dataset-aggregation '{"totalCost":{"name":"Cost","function":"Sum"}}' \
  --dataset-grouping '[{"type":"Dimension","name":"ServiceName"}]' \
  --scope "subscriptions/$SUBSCRIPTION" \
  --query "properties.rows" \
  -o table

echo ""
echo "[bls-cost] Done."
