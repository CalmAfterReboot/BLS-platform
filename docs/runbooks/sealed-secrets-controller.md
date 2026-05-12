# Runbook — Sealed Secrets controller

> Defensive backup, restart test, and known-gap notes for the Bitnami Sealed Secrets controller running on the k3s cluster. Update this runbook whenever the controller is rotated, restored, or migrated.

## Why the master key matters

The controller decrypts `SealedSecret` resources into Kubernetes `Secret` resources using an RSA keypair held inside the controller's namespace. If the cluster is rebuilt and the keypair is not restored first, every existing `SealedSecret` in Git becomes permanently undecryptable. There is no recovery path — the encryption is asymmetric and the controller-side private key is the only material that can recover the plaintext.

Treat the master key as the single highest-blast-radius secret on the cluster. Back it up before any work that could destroy the controller's namespace.

## Where the key lives

- **Namespace:** `sealed-secrets` (not `kube-system` — this deployment pins the controller into its own namespace via `k8s/apps/sealed-secrets.yaml`).
- **Label selector:** `sealedsecrets.bitnami.com/sealed-secrets-key`. The active key carries the value `=active`; rotated-out keys retain the label without the value and the controller will still load them at startup to decrypt previously-sealed material.
- **kubeseal invocation:** always pass `--controller-namespace sealed-secrets --controller-name sealed-secrets`. The defaults assume `kube-system / sealed-secrets-controller` and will fail silently against this deployment.

## Backup procedure

### 1. Discover all keys (read-only)

```bash
# Prefer the wider selector — it catches both active and rotated-out keys.
kubectl -n sealed-secrets get secret \
  -l sealedsecrets.bitnami.com/sealed-secrets-key \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.metadata.creationTimestamp}{"\n"}{end}'
```

If the output is empty, the controller may not have generated a key yet (fresh install) or the label scheme has drifted. Investigate before continuing — do not export and assume.

### 2. Export to a dated, mode-600 file

```bash
DATE=$(date +%Y-%m-%d)
OUT=~/bls-sealed-secrets-master.${DATE}.key.yaml

kubectl -n sealed-secrets get secret \
  -l sealedsecrets.bitnami.com/sealed-secrets-key \
  -o yaml > "$OUT"
chmod 600 "$OUT"
```

`-o yaml` against a label selector returns a `List` object containing every matching `Secret` in one file. That is the desired behaviour — capture all keys, not just `=active`, so the file survives a future rotation.

### 3. Move off the workstation

The exported file must end up in **encrypted off-workstation storage** before the runbook step is closed. Acceptable destinations:

- A password manager with end-to-end encryption — store as a secure note or attachment.
- An encrypted USB drive (LUKS, VeraCrypt, or platform-equivalent).
- An encrypted cloud-backup target with key material the workstation does not hold.

Not acceptable: any Git repository (public or private), any unencrypted cloud sync folder, any "I'll clean it up later" temporary location.

### 4. Verify the off-workstation copy is readable

Before removing the local copy, verify the destination copy parses as YAML on a fresh session:

```bash
# Inspect the structure without exposing key material:
head -5 <destination-copy>
# Expected: apiVersion: v1, items: ... data: with tls.crt / tls.key fields.
```

A diff of the destination copy against the local original should return empty bytes.

### 5. Remove the local copy — honest caveat

```bash
shred -u ~/bls-sealed-secrets-master.${DATE}.key.yaml
```

**`shred` is not a perfect wipe on modern filesystems.** It overwrites file contents and unlinks, but several factors limit its effectiveness:

- **Journalled filesystems (ext3, ext4, XFS, NTFS):** the filesystem journal may have already recorded blocks of the original file. `shred` cannot reach the journal.
- **Copy-on-write filesystems (btrfs, ZFS, APFS):** old blocks are not overwritten; new writes go to new blocks. The original blocks remain until garbage-collected, which `shred` cannot trigger.
- **SSDs and flash storage:** wear-levelling writes new blocks to different physical cells. The "old" blocks may persist in the flash controller's free pool for an indefinite time.
- **Snapshots, backups, swap, and OS-level file caches:** if the file was ever paged out or backed up, `shred` does not touch those copies.

`shred -u` is still the correct tool. It hardens against casual recovery (`undelete`, file scrapers, accidental backup inclusion). It does **not** harden against a determined forensic attacker with physical disk access. The defence in depth for that threat model is: keep the key on disk for the shortest possible time, on an encrypted volume where possible, and treat the workstation as compromised if it leaves your physical control.

### 6. Verify local copy is gone

```bash
ls ~/bls-sealed-secrets-master.*.key.yaml
# Expected: "No such file or directory"
```

## Controller-restart test (limited-scope restore-path test)

Tests that the controller can be cleanly scaled down and back up without losing decryption capability. Does **not** test the full restore-from-backup path against a fresh cluster — see "Known gaps" below.

### Why this test exists

If `shred` failed silently, or the off-workstation copy was corrupted during transit, the next cluster rebuild would be the wrong moment to discover that. A restart test catches a narrower failure: "did the in-cluster key actually persist and reload correctly?" If it didn't, the off-workstation backup is the only copy and the test surfaces that gap immediately.

### Test procedure

Pre-flight:

```bash
# 1 — kubeseal client and controller versions must match within a minor.
kubeseal --version
kubectl -n sealed-secrets get deployment sealed-secrets \
  -o jsonpath='{.spec.template.spec.containers[0].image}'

# 2 — the controller is managed by ArgoCD with selfHeal: true.
#     Suspend the Application's automated sync before scaling, or ArgoCD
#     will fight the scale-down. Save the current sync policy first.
kubectl -n argocd get application sealed-secrets \
  -o jsonpath='{.spec.syncPolicy}' > /tmp/saved-syncpolicy.json
kubectl -n argocd patch application sealed-secrets --type=merge \
  -p '{"spec":{"syncPolicy":{"automated":null}}}'

# 3 — verify automated block is gone before scaling
kubectl -n argocd get application sealed-secrets \
  -o json | jq '.spec.syncPolicy.automated.selfHeal // null'
# Expected: null
```

Test:

```bash
# Create a throwaway SealedSecret in a dedicated namespace.
kubectl create namespace sealed-test --dry-run=client -o yaml | kubectl apply -f -

MARKER="restart-test-$(date +%s)"
cat <<EOF | kubeseal \
  --controller-namespace sealed-secrets --controller-name sealed-secrets \
  --format yaml > /tmp/throwaway-sealed.yaml
apiVersion: v1
kind: Secret
metadata:
  name: throwaway
  namespace: sealed-test
type: Opaque
stringData:
  marker: "$MARKER"
EOF

kubectl apply -f /tmp/throwaway-sealed.yaml
sleep 5
# Confirm the controller decrypted it pre-restart.
kubectl -n sealed-test get secret throwaway \
  -o jsonpath='{.data.marker}' | base64 -d  # should match $MARKER

# Scale the controller to zero, wait for pod gone, delete the throwaway.
kubectl -n sealed-secrets scale deployment/sealed-secrets --replicas=0
until [[ -z "$(kubectl -n sealed-secrets get pods \
  -l app.kubernetes.io/name=sealed-secrets --no-headers 2>/dev/null)" ]]; do
  sleep 2
done
kubectl -n sealed-test delete sealedsecret throwaway
kubectl -n sealed-test delete secret throwaway --ignore-not-found

# Scale back up, wait for ready, confirm the log shows key registration.
kubectl -n sealed-secrets scale deployment/sealed-secrets --replicas=1
kubectl -n sealed-secrets rollout status deployment/sealed-secrets --timeout=60s
kubectl -n sealed-secrets logs deployment/sealed-secrets --tail=20 \
  | grep -i "registered private key"
# Expected: a log line naming the sealed-secrets-key* secret.

# Real-world check: confirm existing SealedSecrets cluster-wide still decrypt.
kubectl get sealedsecrets -A
# Pick the oldest, confirm its derived Secret still exists and has the
# expected keys. If zero exist cluster-wide, this step is moot — proceed.

# Re-apply the throwaway, confirm round-trip.
kubectl apply -f /tmp/throwaway-sealed.yaml
sleep 5
kubectl -n sealed-test get secret throwaway \
  -o jsonpath='{.data.marker}' | base64 -d  # must match $MARKER
```

Cleanup:

```bash
kubectl delete namespace sealed-test
rm /tmp/throwaway-sealed.yaml

# Restore the original sync policy byte-identical.
ORIG=$(cat /tmp/saved-syncpolicy.json)
kubectl -n argocd patch application sealed-secrets --type=merge \
  -p "{\"spec\":{\"syncPolicy\":$ORIG}}"
kubectl -n argocd get application sealed-secrets \
  -o jsonpath='{.spec.syncPolicy}'  # must match the saved file
rm /tmp/saved-syncpolicy.json
```

Pass criteria:
- Pre-restart marker round-trip succeeds.
- Controller log records `registered private key` for the expected secret on restart.
- Any pre-existing `SealedSecret`s in the cluster still have populated derived `Secret`s after restart.
- Post-restart marker round-trip succeeds.
- ArgoCD `sealed-secrets` Application returns to `Synced / Healthy`.

## Known gaps in test coverage

This runbook documents two tests with overlapping but not identical scope:

1. **Controller-restart test** (above) — proves the in-cluster key reload works. Cluster, etcd, namespace, and deployment all remain intact during the test.
2. **Full restore-from-backup path** — applying the exported `.key.yaml` against a freshly-created `sealed-secrets` namespace on a cluster that has no prior knowledge of the key, then confirming that previously-sealed material decrypts.

Test (2) is **not** routinely executed. The cleanest moment to validate it is during the next planned cluster rebuild — apply the backup before reinstalling the controller, watch the controller load the key, and confirm that an existing `SealedSecret` (committed to Git, never re-sealed) decrypts cleanly.

When that rebuild happens, the verification steps to run before declaring the restore successful:

```bash
# 1 — apply the backed-up key into the new sealed-secrets namespace BEFORE
#     installing the controller. Controller picks up existing keys at startup.
kubectl create namespace sealed-secrets --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f <backup-file>

# 2 — install the controller (via ArgoCD as normal).

# 3 — confirm key registration in controller logs.
kubectl -n sealed-secrets logs deployment/sealed-secrets \
  | grep "registered private key"

# 4 — sync an existing SealedSecret that pre-dates the rebuild, confirm
#     its derived Secret reappears with the expected keys.
```

If step 4 fails, stop. Do not re-seal anything against a new key until the restore is investigated — re-sealing locks in the new key as the only decrypt-able one and abandons every committed `SealedSecret` that was sealed against the old key.

## Rotation

`sealed-secrets-controller` rotates its key automatically (default: 30-day interval). Rotation produces a new `Secret` carrying the label `sealedsecrets.bitnami.com/sealed-secrets-key=active`; the previously-active key keeps the label without the value and is retained for decryption of older `SealedSecret`s.

Operational consequence: re-run the backup procedure after every rotation. Always use the wider selector (label without value) to capture all retained keys, not just the active one. Date the file. Move it off-workstation.

## References

- Bitnami Sealed Secrets project: https://github.com/bitnami-labs/sealed-secrets
- ArgoCD Application manifest for this deployment: `k8s/apps/sealed-secrets.yaml`
