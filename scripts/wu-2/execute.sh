#!/usr/bin/env bash
# WU-2 execution — cluster-mutating. Two-phase confirmation gates.
# Idempotent where possible; safe to re-run after partial failure.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
ARTEFACT_DIR="${SCRIPT_DIR}/artefacts/execute/${TS}"
mkdir -p "${ARTEFACT_DIR}"
ln -sfn "${ARTEFACT_DIR}" "${SCRIPT_DIR}/artefacts/execute/latest"

NS_ARGOCD="argocd"
NS_WORKLOAD="llm-gateway"
APP_STANDALONE="llm-gateway"
APP_MATRIX="llm-gateway-in-cluster"
REPO_ROOT="$(git rev-parse --show-toplevel)"
MANIFEST="${REPO_ROOT}/04-llm-gateway/argocd-app.yaml"

red()    { printf '\033[31m%s\033[0m\n' "$*"; }
green()  { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
blue()   { printf '\033[34m%s\033[0m\n' "$*"; }

confirm() {
  local prompt="$1"
  echo ""
  yellow "${prompt}"
  read -r -p "Type 'yes' to proceed: " ans
  if [[ "${ans}" != "yes" ]]; then
    red "Aborted by operator"
    exit 1
  fi
}

wait_for() {
  # wait_for <description> <timeout-sec> <command...>
  local desc="$1"; shift
  local timeout="$1"; shift
  local elapsed=0
  while (( elapsed < timeout )); do
    if "$@" >/dev/null 2>&1; then
      green "  ✓ ${desc}"
      return 0
    fi
    sleep 5
    elapsed=$((elapsed + 5))
    printf '  . waiting (%ds/%ds)\r' "${elapsed}" "${timeout}"
  done
  red "  ✗ ${desc} — timeout after ${timeout}s"
  return 1
}

blue "═══════════════════════════════════════════════════════════"
blue "WU-2 execution — ${TS}"
blue "═══════════════════════════════════════════════════════════"

# ─── Gate 0: insist on green pre-flight ────────────────────────
PREFLIGHT_LATEST="${SCRIPT_DIR}/artefacts/preflight/latest"
if [[ ! -d "${PREFLIGHT_LATEST}" ]]; then
  red "No pre-flight artefacts found. Run preflight.sh first."
  exit 1
fi
PREFLIGHT_AGE=$(( $(date +%s) - $(stat -c %Y "${PREFLIGHT_LATEST}") ))
if (( PREFLIGHT_AGE > 1800 )); then
  yellow "Pre-flight artefacts are $(( PREFLIGHT_AGE / 60 ))m old."
  confirm "Re-running pre-flight is recommended. Continue with stale data?"
fi

# ─── Phase 1: snapshot ─────────────────────────────────────────
blue "[1/6] Snapshot before any mutation"
kubectl get application -n "${NS_ARGOCD}" "${APP_STANDALONE}" -o yaml \
  > "${ARTEFACT_DIR}/app-standalone-before.yaml"
kubectl get application -n "${NS_ARGOCD}" "${APP_MATRIX}" -o yaml \
  > "${ARTEFACT_DIR}/app-matrix-before.yaml"
kubectl get all,cm,secret,ingress -n "${NS_WORKLOAD}" -o yaml \
  > "${ARTEFACT_DIR}/workload-before.yaml"
green "  ✓ Snapshots written to ${ARTEFACT_DIR}"

# ─── Phase 2: strip finalizer (non-destructive, no race) ───────
# Reversible, triggers no reconcile, closes the cascade-prune risk
# before the survivor is suspended. No confirm gate.
blue "[2/6] Strip resources-finalizer on ${APP_STANDALONE}"
FINALIZERS="$(kubectl get application -n "${NS_ARGOCD}" "${APP_STANDALONE}" \
  -o jsonpath='{.metadata.finalizers}' 2>/dev/null || echo '[]')"
echo "${FINALIZERS}" > "${ARTEFACT_DIR}/standalone-finalizers-original.json"

if [[ "${FINALIZERS}" == *"resources-finalizer.argocd.argoproj.io"* ]]; then
  kubectl patch application -n "${NS_ARGOCD}" "${APP_STANDALONE}" \
    --type=merge -p '{"metadata":{"finalizers":null}}'
  green "  ✓ Finalizer stripped (cascade-prune risk closed)"
else
  yellow "  ! No finalizer present — skipping"
fi

# ─── Phase 3-4: atomic suspend+delete block ────────────────────
# Suspending the survivor opens a window where the doomed standalone can
# reconcile freely with selfHeal=true. The delete must follow within seconds.
# Single confirm gate up front — once past, the two operations run back-to-back.
blue "[3/6] Atomic block: suspend survivor, delete standalone"

# Capture survivor's original sync policy BEFORE the confirm — non-destructive
# read; needed by Phase 5 restore even if the operator aborts here.
ORIG_AUTOMATED="$(kubectl get application -n "${NS_ARGOCD}" "${APP_MATRIX}" \
  -o jsonpath='{.spec.syncPolicy.automated}' || true)"
echo "${ORIG_AUTOMATED}" > "${ARTEFACT_DIR}/matrix-automated-original.json"

yellow "The next two operations must run back-to-back to avoid a reconcile race."
yellow "  a) Suspend ${APP_MATRIX} automated sync (closes survivor's selfHeal window)"
yellow "  b) Delete ${APP_STANDALONE} Application CR (--cascade=orphan)"
confirm "Confirm you are at the keyboard and ready to proceed without interruption."

# (a) suspend survivor
if [[ -n "${ORIG_AUTOMATED}" && "${ORIG_AUTOMATED}" != "null" ]]; then
  kubectl patch application -n "${NS_ARGOCD}" "${APP_MATRIX}" \
    --type=merge -p '{"spec":{"syncPolicy":{"automated":null}}}'
  green "  ✓ Survivor automated sync suspended"
else
  yellow "  ! Survivor already had automated=null — proceeding to delete"
fi

# (b) delete standalone — no second gate
kubectl delete application -n "${NS_ARGOCD}" "${APP_STANDALONE}" --cascade=orphan

wait_for "Application ${APP_STANDALONE} fully removed" 60 \
  bash -c "! kubectl get application -n ${NS_ARGOCD} ${APP_STANDALONE} 2>/dev/null"

# Verify workload survived
blue "  → Verifying workload pods still running"
kubectl get pods -n "${NS_WORKLOAD}" -o wide | tee "${ARTEFACT_DIR}/pods-after-delete.txt"
NOT_RUNNING=$(kubectl get pods -n "${NS_WORKLOAD}" \
  --field-selector=status.phase!=Running -o name 2>/dev/null | wc -l)
if (( NOT_RUNNING > 0 )); then
  red "  ✗ ${NOT_RUNNING} pod(s) not Running — investigate before proceeding"
  exit 1
fi
green "  ✓ All workload pods still Running"

# ─── Phase 5: restore automated sync on the survivor ───────────
blue "[5/6] Restore automated sync on ${APP_MATRIX} and force reconcile"
if [[ -n "${ORIG_AUTOMATED}" && "${ORIG_AUTOMATED}" != "null" ]]; then
  # ORIG_AUTOMATED is JSON like {"prune":true,"selfHeal":true}
  PATCH=$(jq -nc --argjson auto "${ORIG_AUTOMATED}" '{spec:{syncPolicy:{automated:$auto}}}')
  echo "${PATCH}" > "${ARTEFACT_DIR}/matrix-restore-patch.json"
  kubectl patch application -n "${NS_ARGOCD}" "${APP_MATRIX}" --type=merge -p "${PATCH}"
  green "  ✓ Automated sync restored"
fi

# Trigger a sync by annotating refresh
kubectl annotate application -n "${NS_ARGOCD}" "${APP_MATRIX}" \
  argocd.argoproj.io/refresh=hard --overwrite

wait_for "${APP_MATRIX} reaches Synced/Healthy" 180 \
  bash -c "[[ \$(kubectl get application -n ${NS_ARGOCD} ${APP_MATRIX} -o jsonpath='{.status.sync.status}') == 'Synced' && \$(kubectl get application -n ${NS_ARGOCD} ${APP_MATRIX} -o jsonpath='{.status.health.status}') == 'Healthy' ]]"

# Verify re-adoption: a sample Deployment should now report matrix tracking-id
SAMPLE_DEPLOY=$(kubectl get deployment -n "${NS_WORKLOAD}" -o name | head -n1 | sed 's|.*/||')
if [[ -n "${SAMPLE_DEPLOY}" ]]; then
  TID="$(kubectl get deployment -n "${NS_WORKLOAD}" "${SAMPLE_DEPLOY}" \
    -o jsonpath='{.metadata.annotations.argocd\.argoproj\.io/tracking-id}')"
  echo "${SAMPLE_DEPLOY} tracking-id: ${TID}" | tee "${ARTEFACT_DIR}/sample-tracking-id.txt"
  if [[ "${TID}" != "${APP_MATRIX}:"* ]]; then
    red "  ✗ Sample Deployment still tracked by '${TID}' — re-adoption incomplete"
    yellow "    May resolve on next reconcile; check ArgoCD UI"
  else
    green "  ✓ Sample Deployment re-adopted by ${APP_MATRIX}"
  fi
fi

# Full tracking-id audit
{
  echo "# kind/name → tracking-id (after)"
  for kind in deployment service configmap secret ingress replicaset; do
    while IFS= read -r name; do
      [[ -z "${name}" ]] && continue
      tid="$(kubectl get "${kind}" -n "${NS_WORKLOAD}" "${name}" \
        -o jsonpath='{.metadata.annotations.argocd\.argoproj\.io/tracking-id}' 2>/dev/null || true)"
      echo "${kind}/${name} → ${tid:-<none>}"
    done < <(kubectl get "${kind}" -n "${NS_WORKLOAD}" -o name 2>/dev/null | sed 's|.*/||')
  done
} > "${ARTEFACT_DIR}/tracking-ids-after.txt"

# ─── Phase 6: remove manifest from git ─────────────────────────
blue "[6/6] Remove manifest from git"
if [[ -f "${MANIFEST}" ]]; then
  confirm "About to git rm ${MANIFEST} and commit. Final destructive step."
  cp "${MANIFEST}" "${ARTEFACT_DIR}/argocd-app.yaml.removed"
  git rm "${MANIFEST}"
  git commit -m "fix(p4): remove duplicate llm-gateway ArgoCD Application

Standalone Application in 04-llm-gateway/argocd-app.yaml was racing
the ApplicationSet-generated llm-gateway-in-cluster for ownership of
resources in the llm-gateway namespace, causing persistent OutOfSync.

- Stripped resources-finalizer to prevent cascade prune during handover
- Deleted Application CR with --cascade=orphan
- Removed 04-llm-gateway/argocd-app.yaml from git

WU-3 will follow up with chart deduplication.

Artefacts: scripts/wu-2/artefacts/execute/${TS}/"
  green "  ✓ Manifest removed and committed"
else
  yellow "  ! Manifest already absent — skipping"
fi

# ─── Final state ───────────────────────────────────────────────
blue "═══════════════════════════════════════════════════════════"
green "WU-2 execution complete"
blue "Artefacts: ${ARTEFACT_DIR}"
blue ""
blue "Manual verification before declaring WU-2 done:"
blue "  - diff scripts/wu-2/artefacts/preflight/latest/tracking-ids-before.txt \\"
blue "         ${ARTEFACT_DIR}/tracking-ids-after.txt"
blue "  - Watch ${APP_MATRIX} in ArgoCD UI for 10min — must stay Synced/Healthy"
blue "  - git push origin main"
blue "  - Update BLS-STATUS.md and PHASE-2-HANDOFF.md (WU-2 → Done)"
blue "═══════════════════════════════════════════════════════════"
