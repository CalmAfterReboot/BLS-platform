#!/usr/bin/env bash
# WU-2 pre-flight — read-only verification of cluster state and hypothesis.
# Safe to run repeatedly. Produces artefacts under scripts/wu-2/artefacts/preflight/
# Exit codes: 0 = green, ready to execute. Non-zero = stop, investigate.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTEFACT_DIR="${SCRIPT_DIR}/artefacts/preflight/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "${ARTEFACT_DIR}"

# Latest symlink for convenience
ln -sfn "${ARTEFACT_DIR}" "${SCRIPT_DIR}/artefacts/preflight/latest"

NS_ARGOCD="argocd"
NS_WORKLOAD="llm-gateway"
APP_STANDALONE="llm-gateway"
APP_MATRIX="llm-gateway-in-cluster"

red()    { printf '\033[31m%s\033[0m\n' "$*"; }
green()  { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
blue()   { printf '\033[34m%s\033[0m\n' "$*"; }

FAILED=0
fail() { red "  ✗ $*"; FAILED=1; }
pass() { green "  ✓ $*"; }
warn() { yellow "  ! $*"; }

blue "═══════════════════════════════════════════════════════════"
blue "WU-2 pre-flight — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
blue "Artefacts: ${ARTEFACT_DIR}"
blue "═══════════════════════════════════════════════════════════"

# ─── 1. Git hygiene ────────────────────────────────────────────
blue "[1/7] Git state"
if [[ -n "$(git status --porcelain)" ]]; then
  fail "Working tree dirty"
  git status --short | tee "${ARTEFACT_DIR}/git-status.txt"
else
  pass "Working tree clean"
fi

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "${CURRENT_BRANCH}" != "main" ]]; then
  warn "On branch '${CURRENT_BRANCH}' (not main) — confirm this is intentional"
else
  pass "On main"
fi

git rev-parse HEAD > "${ARTEFACT_DIR}/git-head.txt"

# ─── 2. kubectl context ────────────────────────────────────────
blue "[2/7] kubectl context"
CTX="$(kubectl config current-context)"
echo "${CTX}" > "${ARTEFACT_DIR}/kubectl-context.txt"
pass "Context: ${CTX}"

if ! kubectl get ns "${NS_ARGOCD}" >/dev/null 2>&1; then
  fail "Namespace ${NS_ARGOCD} not reachable — wrong context?"
  exit 1
fi

# ─── 3. Both Applications exist ────────────────────────────────
blue "[3/7] ArgoCD Applications"
for app in "${APP_STANDALONE}" "${APP_MATRIX}"; do
  if kubectl get application -n "${NS_ARGOCD}" "${app}" >/dev/null 2>&1; then
    pass "${app} present"
    kubectl get application -n "${NS_ARGOCD}" "${app}" -o yaml \
      > "${ARTEFACT_DIR}/app-${app}.yaml"
  else
    fail "${app} missing — hypothesis invalid"
  fi
done

# ─── 4. Sync state — confirm the problem still exists ──────────
blue "[4/7] Sync state (the problem WU-2 fixes)"
if kubectl get application -n "${NS_ARGOCD}" "${APP_STANDALONE}" >/dev/null 2>&1; then
  SYNC_STATUS="$(kubectl get application -n "${NS_ARGOCD}" "${APP_STANDALONE}" \
    -o jsonpath='{.status.sync.status}')"
  HEALTH_STATUS="$(kubectl get application -n "${NS_ARGOCD}" "${APP_STANDALONE}" \
    -o jsonpath='{.status.health.status}')"
  echo "${APP_STANDALONE}: sync=${SYNC_STATUS} health=${HEALTH_STATUS}" \
    | tee "${ARTEFACT_DIR}/sync-state.txt"

  if [[ "${SYNC_STATUS}" == "Synced" && "${HEALTH_STATUS}" == "Healthy" ]]; then
    warn "${APP_STANDALONE} reports Synced/Healthy — problem may have self-resolved"
    warn "Investigate before proceeding; WU-2 may be a no-op"
  else
    pass "${APP_STANDALONE} is ${SYNC_STATUS}/${HEALTH_STATUS} — problem confirmed"
  fi
fi

# ─── 5. ApplicationSet generating the matrix app ───────────────
blue "[5/7] ApplicationSet topology"
kubectl get applicationset -A -o wide | tee "${ARTEFACT_DIR}/applicationsets.txt"

MATRIX_OWNER="$(kubectl get application -n "${NS_ARGOCD}" "${APP_MATRIX}" \
  -o jsonpath='{.metadata.ownerReferences[?(@.kind=="ApplicationSet")].name}' 2>/dev/null || true)"
if [[ -n "${MATRIX_OWNER}" ]]; then
  pass "${APP_MATRIX} owned by ApplicationSet: ${MATRIX_OWNER}"
  echo "${MATRIX_OWNER}" > "${ARTEFACT_DIR}/applicationset-owner.txt"
else
  fail "${APP_MATRIX} has no ApplicationSet owner — hypothesis revision needed"
fi

# ─── 6. Finalizer presence on the doomed Application ───────────
blue "[6/7] Finalizers on ${APP_STANDALONE}"
FINALIZERS="$(kubectl get application -n "${NS_ARGOCD}" "${APP_STANDALONE}" \
  -o jsonpath='{.metadata.finalizers}' 2>/dev/null || echo '[]')"
echo "${FINALIZERS}" > "${ARTEFACT_DIR}/finalizers.txt"
if [[ "${FINALIZERS}" == *"resources-finalizer.argocd.argoproj.io"* ]]; then
  warn "ArgoCD resources-finalizer PRESENT — execution must strip it before delete"
else
  pass "No ArgoCD resources-finalizer — delete will not cascade-prune workload"
fi

# ─── 7. Resource ownership audit ───────────────────────────────
blue "[7/7] Tracking-id annotations in ${NS_WORKLOAD}"
if kubectl get ns "${NS_WORKLOAD}" >/dev/null 2>&1; then
  {
    echo "# kind/name → tracking-id"
    for kind in deployment service configmap secret ingress replicaset; do
      while IFS= read -r name; do
        [[ -z "${name}" ]] && continue
        tid="$(kubectl get "${kind}" -n "${NS_WORKLOAD}" "${name}" \
          -o jsonpath='{.metadata.annotations.argocd\.argoproj\.io/tracking-id}' 2>/dev/null || true)"
        echo "${kind}/${name} → ${tid:-<none>}"
      done < <(kubectl get "${kind}" -n "${NS_WORKLOAD}" -o name 2>/dev/null | sed 's|.*/||')
    done
  } | tee "${ARTEFACT_DIR}/tracking-ids-before.txt"

  STANDALONE_OWNED=$(grep -c "→ ${APP_STANDALONE}:" "${ARTEFACT_DIR}/tracking-ids-before.txt" || true)
  MATRIX_OWNED=$(grep -c "→ ${APP_MATRIX}:" "${ARTEFACT_DIR}/tracking-ids-before.txt" || true)
  echo ""
  echo "Resources tracked by ${APP_STANDALONE}: ${STANDALONE_OWNED}"
  echo "Resources tracked by ${APP_MATRIX}:     ${MATRIX_OWNED}"

  if [[ "${STANDALONE_OWNED}" -eq 0 ]]; then
    warn "${APP_STANDALONE} owns zero resources — already lost the ownership race?"
  fi
else
  fail "Namespace ${NS_WORKLOAD} missing"
fi

# ─── Manifest in git ───────────────────────────────────────────
blue "[bonus] Repo state"
REPO_ROOT="$(git rev-parse --show-toplevel)"
MANIFEST="${REPO_ROOT}/04-llm-gateway/argocd-app.yaml"
if [[ -f "${MANIFEST}" ]]; then
  pass "Manifest present at ${MANIFEST} (will be removed in WU-2)"
  cp "${MANIFEST}" "${ARTEFACT_DIR}/argocd-app.yaml.snapshot"
else
  warn "Manifest already absent from git — partial state, investigate"
fi

# ─── Summary ───────────────────────────────────────────────────
echo ""
blue "═══════════════════════════════════════════════════════════"
if [[ "${FAILED}" -eq 0 ]]; then
  green "PRE-FLIGHT GREEN — ready for execution"
  blue "Artefacts: ${ARTEFACT_DIR}"
  blue "Next: review tracking-ids-before.txt, then run execute.sh"
  exit 0
else
  red "PRE-FLIGHT FAILED — do not proceed"
  exit 1
fi
