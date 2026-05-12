#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(pwd)"
ECC_TMP="/tmp/ecc-install"

echo "==> [1/4] Verifying repo..."
if [[ ! -f ".git/config" ]]; then
  echo "ERROR: Not in a git repo."
  exit 1
fi

echo "==> [2/4] Cloning ECC..."
rm -rf "$ECC_TMP"
git clone --depth=1 https://github.com/affaan-m/everything-claude-code.git "$ECC_TMP"

echo "==> [3/4] Installing ECC agents, rules, skills..."
mkdir -p ~/.claude/rules/ecc ~/.claude/agents ~/.claude/skills/ecc

cp -r "$ECC_TMP/rules/common" ~/.claude/rules/ecc/ 2>/dev/null || echo "WARN: common rules not found"
cp -r "$ECC_TMP/rules/python" ~/.claude/rules/ecc/ 2>/dev/null || echo "WARN: python rules not found"
cp -r "$ECC_TMP/rules/golang" ~/.claude/rules/ecc/ 2>/dev/null || echo "WARN: golang rules not found"

for agent in architect code-reviewer security-reviewer database-reviewer go-reviewer go-build-resolver tdd-guide; do
  if [[ -f "$ECC_TMP/agents/${agent}.md" ]]; then
    cp "$ECC_TMP/agents/${agent}.md" ~/.claude/agents/
    echo "    + agent: ${agent}"
  else
    echo "    ! WARN: ${agent}.md not found"
  fi
done

for skill in postgres-patterns docker-patterns deployment-patterns api-design tdd-workflow security-review; do
  if [[ -d "$ECC_TMP/skills/${skill}" ]]; then
    cp -r "$ECC_TMP/skills/${skill}" ~/.claude/skills/ecc/
    echo "    + skill: ${skill}"
  else
    echo "    ! WARN: skill ${skill} not found"
  fi
done

rm -rf "$ECC_TMP"

echo "==> [4/4] Creating CLAUDE.md and docs..."
mkdir -p docs/playbook docs/adr

if [[ -f "$REPO_DIR/CLAUDE.md" ]]; then
  echo "    CLAUDE.md already exists — skipping (delete it first if you want a fresh copy)"
else
  cat > "$REPO_DIR/CLAUDE.md" << 'CLAUDEMD'
# BLS-DevOps — Claude Code Context

> Auto-loaded every session. Operator profile: docs/playbook/about-me.md

## Portfolio State

| Project | What | Status |
|---|---|---|
| P1 | Azure Landing Zone — Terraform, hub-spoke, NSGs, Log Analytics, GitHub Actions | Done |
| P2 | k3s HA Platform — 3-node, Longhorn, ArgoCD GitOps | Done |
| P3 | Multi-cluster GitOps — ArgoCD ApplicationSets, Helm | Done |
| P4 | LLM Gateway — FastAPI + LiteLLM + Redis, Helm, ArgoCD, Ollama on Proxmox | Done |
| P5 | Observability + Security — kube-prometheus-stack, Grafana, Sealed Secrets, NetworkPolicy | In Progress |
| P6 | Platform Engineering — OPA/Gatekeeper, Azure OpenAI, GCP Terraform, BLS site widget | In Progress |

## Engineering Standards
- Everything in Git. Conventional commits. PRs only, no direct main commits.
- Pre-commit hooks: terraform fmt, validate, tflint, Checkov, detect-secrets.
- Pipeline gates: Semgrep SAST, Trivy, unit + integration + E2E tests.
- Idempotent by default. No destructive ops without explicit confirmation.
- No hardcoded secrets. No credentials in Git. Ever.
- Every architectural decision = ADR in docs/adr/.
- Mandatory tagging on every Azure resource.
- Tenant isolation: adversarial RLS tests on every PR touching tenant data.

## Instructions for Claude Code
1. Skip openers. Verdict first, then rationale, trade-offs, failure modes, implementation.
2. Stress-test designs. Identify blast radius. Surface risks not yet considered.
3. If something is wrong or inefficient — say so immediately and say why.
4. Production context assumed. Peer-level depth. No 101 unless asked.
5. Idempotent scripts only. Risks before commands. No destructive ops without confirmation.
6. Every deliverable is public-repo quality — treat as code review material.
7. Bootstrap-first on platform work. Challenge architecture and build sequence.
8. Tenant isolation is highest blast-radius failure. Adversarial tests non-negotiable.
CLAUDEMD
fi

if [[ -f "$REPO_DIR/docs/adr/000-template.md" ]]; then
  echo "    ADR template already exists — skipping"
else
  cat > "$REPO_DIR/docs/adr/000-template.md" << 'ADRMD'
# ADR-000: [Title]
**Date:** YYYY-MM-DD
**Status:** Proposed | Accepted | Superseded

## Context
## Decision
## Rationale
## Alternatives considered
## Consequences
## Review trigger
ADRMD
fi

echo ""
echo "===================================="
echo "DONE."
echo "~/.claude/agents/ — 7 agents installed"
echo "~/.claude/rules/  — 3 rule sets installed"
echo "~/.claude/skills/ — 6 skills installed"
echo "CLAUDE.md         — present (auto-loaded every session)"
echo "docs/playbook/    — operator profile"
echo "docs/adr/         — ADR template ready"
echo ""
echo "Setup complete. Review changes with 'git status', commit when ready."
echo "Launch: cd $REPO_DIR && claude"
echo "===================================="
