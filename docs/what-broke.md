# What Broke — BLS Portfolio Incident Log

This document records bugs, misconfigurations, and failures encountered during the BLS DevOps portfolio, along with their root causes, fixes, and lessons. It is written so that someone reading it — a colleague, a future maintainer, or a future version of me — can understand not just what went wrong but why, and what kind of thinking it took to resolve it.

---

## Format

| Field | Contents |
|---|---|
| **Date** | When the issue was discovered |
| **What broke** | Observable symptom |
| **Root cause** | The actual technical reason |
| **Fix** | What was changed and why |
| **Lesson** | What this teaches about Ansible, Linux, or infrastructure in general |

---

## Week 3 — 2026-05-01 — Ansible node-hardening: three idempotency failures

### Entry 1: Moduli filtering showed `changed` on every run

**Date:** 2026-05-01

**What broke:** After the initial role implementation, running the playbook a second time showed the "Disable SSH protocol 1 via moduli" and "Mark moduli as hardened" tasks both reporting `changed`, even though the DH moduli file had already been filtered on the first run and no actual change was occurring on the system.

**Root cause:** Two separate mistakes in the same pair of tasks.

The first mistake: the `ansible.builtin.shell` task used `creates: /etc/ssh/.moduli_hardened` to check whether the sentinel file existed and skip the task if so. This part worked. But the same task also had `changed_when: moduli_result.rc == 0`, which is a directive that overrides Ansible's change detection based on the task's return code. The problem is that `changed_when` is evaluated every time the task actually runs — and on first run, `rc == 0` (the awk command succeeded), so it reports `changed`. On second run, the `creates:` parameter correctly skipped the task. But the symptom the user reported was that it showed `changed` even on the second run, which pointed to the second mistake.

The second mistake: the sentinel-creation task used `ansible.builtin.file` with `state: touch`. The `touch` operation always updates the file's modification time, even if the file already exists. Ansible's `file` module detects the mtime change and reports `changed` every time, making the task non-idempotent regardless of what `when:` condition guards it.

Together: even if the awk task was correctly skipped, if the sentinel file was not properly guarding the `touch` task (e.g. if the `when: moduli_result.changed` condition evaluated incorrectly), the touch task would always fire and always show `changed`.

**Fix:** Replaced the entire pattern with three clean tasks:

1. `ansible.builtin.stat` to check if the sentinel file exists — the result is stored in a variable. This task never reports `changed`.
2. The awk shell command, gated on `not moduli_sentinel.stat.exists` with `changed_when` set to the same expression. It only runs and only reports `changed` on the first pass.
3. `ansible.builtin.copy` (not `touch`) to create the sentinel file, also gated on `not moduli_sentinel.stat.exists`. The `copy` module hashes file content and only reports `changed` when content differs. An existing file with identical content is silently `ok`.

The key insight is that `copy` provides genuine idempotency; `touch` does not. And explicit `stat` + `when:` is more predictable than `creates:`, which has subtle interaction with other directives.

**Lesson:** **Principle: idempotency is a property you design in, not something Ansible provides for free.** Every task's change-detection mechanism must be reasoned through explicitly. When creating sentinel files, always use `copy` or `template` (which use content-hash comparison) rather than `touch` (which uses mtime, which always changes). When combining `creates:` with `changed_when`, trace through what each directive does independently — the interaction is non-obvious and the bugs it produces are hard to see in a single run.

---

### Entry 2: UFW tasks showed `changed` on every run

**Date:** 2026-05-01

**What broke:** All five UFW tasks (set default input policy, set default output policy, set default forward policy, allow ports, enable UFW) reported `changed` on every run of the playbook, even on nodes where the firewall had already been correctly configured.

**Root cause:** The `ufw.yml` task file began with:

```yaml
- name: Reset UFW to defaults (idempotent — only fires on first run)
  community.general.ufw:
    state: reset
  changed_when: false
```

The comment in the task name was wrong in both directions. `state: reset` is not idempotent — it physically destroys all UFW rules and resets default policies to `ACCEPT` on every execution. And `changed_when: false` did not prevent the reset from happening; it only prevented Ansible from reporting it as a change. The firewall was silently being wiped on every run, which meant every subsequent task was starting from an empty state (default ACCEPT, no rules, disabled) and had to re-apply everything from scratch — correctly showing `changed` because the state genuinely differed from what was desired.

The `changed_when: false` made the bug invisible in the PLAY RECAP. The symptom was the five downstream tasks always showing `changed`, which looked superficially like a UFW idempotency problem in the `community.general.ufw` module. The actual problem was upstream.

**Fix:** Remove the `state: reset` task entirely. The `community.general.ufw` module is natively idempotent for all the operations needed:

- `default: deny, direction: incoming` checks the current default policy before setting it.
- `rule: allow, port: 22, proto: tcp` checks whether the rule already exists in `ufw show added` output before creating it.
- `state: enabled` checks whether UFW is already enabled before enabling it.

None of these tasks need a clean slate to be idempotent. Removing the reset task allowed all five tasks to return `ok` on the second run.

**Lesson:** **Principle: `changed_when: false` suppresses the report of a change — it does not prevent the change from happening.** It is only correct on genuinely read-only commands (`fail2ban-client status`, `chronyc tracking`, `sysctl -n`) where the module would otherwise report a false positive. Applying it to a destructive task hides the destruction and makes downstream failures appear unrelated to their actual cause. When a task does something that modifies system state, never silence its change report — fix the task instead.

---

### Entry 3: `net.ipv4.conf.all.log_martians` showed `changed` on every run

**Date:** 2026-05-01

**What broke:** The sysctl task loop was using `ansible.posix.sysctl` to apply kernel parameters. After the first run, every subsequent run showed at least the `log_martians` parameter reporting `changed`, and `sysctl -n net.ipv4.conf.all.log_martians` returned `0` even though the playbook had set it to `1` on the previous run.

**Root cause:** Two contributing factors, one in the Linux kernel and one in the Ansible module's design.

**Linux kernel factor:** `net.ipv4.conf.all.*` parameters are aggregate namespaces in the Linux networking stack. When you write to `net.ipv4.conf.all.log_martians`, it sets the value for all currently active network interfaces. But when you read it back, the kernel returns the logical OR (or AND, depending on the parameter) of all individual interface values. If any interface — including `lo` (loopback) — has its per-interface `log_martians` set to `0`, reading `net.ipv4.conf.all.log_martians` returns `0`, regardless of what you just wrote. This is confirmed:

```
$ sysctl net.ipv4.conf.all.log_martians
net.ipv4.conf.all.log_martians = 0      # reads 0 even after writing 1
```

**Ansible module factor:** `ansible.posix.sysctl` with `reload: true` applies the value and then reads it back to confirm. When it reads `0` after writing `1`, it reports `changed` and tries again next run, perpetually. The module is doing the right thing for most parameters, but this specific class of aggregate parameters breaks its assumption that write-then-read will return the written value.

The sysctl file `/etc/sysctl.d/99-bls-hardening.conf` had the correct content from the first run. The parameter was set correctly at boot time (when `sysctl --system` loads all files in order). But the live kernel value was `0` because loopback had not been explicitly configured, and the module's read-back confirmed this mismatch.

**Fix:** Replace the per-item `ansible.posix.sysctl` loop with a `template` task that writes the entire sysctl file, and move application into a handler that calls `sysctl --system`. With this design:

- Ansible's idempotency check compares file content (not live kernel values). If the file matches the template, the task returns `ok` and the handler never fires.
- When the file does change, `sysctl --system` loads all `/etc/sysctl.d/` files in lexicographic order. `99-bls-hardening.conf` loads last and wins any conflict with Ubuntu's `10-*` files.
- The live kernel value is never read by Ansible. The discrepancy between the live value and the file value does not trigger a false `changed`.

The second run showed `changed=0, failed=0` with this approach.

**Lesson:** **Principle: when a module perpetually reports `changed` despite applying the correct value, investigate whether the system's read and write semantics are the same.** The Linux `conf.all.*` namespace writes to all interfaces at once but reads back an aggregate across interfaces — write and read do not commute. The module was correct to flag the difference; the problem was using a module that reads live values for a parameter that cannot be read back reliably. When you hit this pattern, move the idempotency anchor to a layer that is unambiguous: a file's content hash is always deterministic, whereas a kernel aggregate is not. Template + handler is the general solution whenever a configuration file is the source of truth.

---

---

## Week 3 — 2026-05-01 — Prerequisites: passwordless sudo not configured

### Entry 4: `become: true` failed immediately — sudo required a password

**Date:** 2026-05-01

**What broke:** Attempting to run the playbook for the first time produced an immediate failure on the first task that required privilege escalation:

```
TASK [Gathering Facts] *********************************************************
fatal: [bls-node-01]: FAILED! => {
    "msg": "Missing sudo password"
}
```

Or in some configurations:

```
TASK [node-hardening : Update apt cache if older than 1 hour] ******************
fatal: [bls-node-01]: FAILED! => {
    "module_stderr": "sudo: a password is required\n",
    "msg": "MODULE FAILURE"
}
```

The playbook failed before applying any changes. Nothing was broken on the node — the failure was a pre-flight prerequisite.

**Root cause:** `ansible.cfg` configures `become: true` and `become_method: sudo` globally, which means every task that needs root will attempt `sudo` without a password. The `dev` user was not in the sudoers file with `NOPASSWD`, so sudo prompted for a password — and Ansible, having no terminal to accept a password prompt, failed immediately.

This is a prerequisite failure, not an Ansible bug. The documentation listed it under Prerequisites but the Quick Start section did not explicitly prompt the reader to verify it before running.

**Fix:**

```bash
# Confirm the problem
sudo -n true || echo "passwordless sudo is NOT configured"

# Fix: create a sudoers drop-in file for dev (run as root or existing sudoer)
echo "dev ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/dev-nopasswd
sudo chmod 0440 /etc/sudoers.d/dev-nopasswd

# Verify — this must print nothing (no error, no password prompt)
sudo -n true && echo "OK"
```

**Lesson:** **Principle: always verify all prerequisites with a connectivity test before the first full run.** `./scripts/bls-run.sh ping` sends an Ansible ping that exercises connectivity, Python availability, and privilege escalation in a single read-only operation. If ping fails, diagnose that before touching the playbook. Running the full playbook against a node that fails at step one wastes time and produces confusing error messages that obscure the real problem. Treat "does the control node have everything it needs to reach and control the target?" as a separate, mandatory pre-flight check — not something assumed to be true.

---

## Summary

All three bugs shared a common root cause category: the initial implementation relied on an incorrect mental model of how a module or Linux subsystem behaves. The bugs were not obvious from reading the code in isolation — they required running the playbook twice and observing the second-run output to surface.

The fix for each was to choose a more explicit mechanism with clearer idempotency semantics:

| Bug | Wrong mechanism | Right mechanism |
|---|---|---|
| Moduli sentinel | `state: touch` (mtime) | `copy` with fixed content (content-hash) |
| UFW reset | `state: reset` + `changed_when: false` | No reset; rely on native module idempotency |
| sysctl log_martians | Per-item loop reading live values | Template + handler (idempotency on file content) |

The discipline of running a playbook twice and treating any `changed` on the second run as a bug is a good engineering habit. It forces you to reason through every task's idempotency model before shipping, and it gives you a clear pass/fail criterion that automation (CI/CD) can enforce.
