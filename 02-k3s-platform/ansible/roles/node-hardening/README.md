# node-hardening Role

This role applies a security baseline to Ubuntu 24.04 nodes. "Security baseline" means bringing a fresh server from its out-of-the-box defaults — which are designed for compatibility, not security — to a state where it is measurably harder to attack.

The role covers eight areas: packages, SSH, firewall (UFW), kernel parameters (sysctl), resource limits, brute-force protection (fail2ban), audit logging (auditd), and time synchronisation (chrony). Every task is idempotent: you can run the playbook ten times and get the same result, with no side effects on subsequent runs.

**Supported platform:** Ubuntu 24.04 LTS (Noble). The role asserts this at the start and fails fast if the target is different.

---

## Variable Reference

All variables live in `ansible/group_vars/all/vars.yml`. They are passed to the role via Ansible's variable precedence system — `group_vars/all/` applies to every host in the inventory unless a more specific `host_vars` file overrides it.

### SSH

| Variable | Default | What it controls |
|---|---|---|
| `ssh_port` | `22` | The port sshd listens on. Referenced by UFW and fail2ban automatically — change it in one place and it propagates everywhere. |
| `ssh_permit_root_login` | `"no"` | Whether the root account can log in over SSH. Setting to `"no"` forces attackers to first compromise a regular account before escalating. |
| `ssh_password_authentication` | `"no"` | Whether password logins are accepted. Disabling this means only SSH key holders can log in — a brute-forced password becomes useless. |
| `ssh_pubkey_authentication` | `"yes"` | Whether SSH key authentication is accepted. Must be `"yes"` if passwords are disabled, or you lock yourself out. |
| `ssh_allow_users` | `"dev"` | Space-separated list of users permitted to log in over SSH. Any user not on this list is rejected by sshd before reaching PAM. |
| `ssh_max_auth_tries` | `3` | Number of authentication attempts per connection before sshd closes the connection. Limits the window for online brute force. |
| `ssh_client_alive_interval` | `300` | Seconds between keepalive probes sent to an idle client. After this many seconds of silence, sshd sends a probe. |
| `ssh_client_alive_count_max` | `2` | Number of unanswered keepalive probes before sshd disconnects. At defaults: 300s × 2 = 10 minutes maximum idle session. |
| `ssh_login_grace_time` | `30` | Seconds a connection is allowed to stay open without completing authentication. Reduces exposure to slow connection attacks. |

### UFW (Firewall)

| Variable | Default | What it controls |
|---|---|---|
| `ufw_default_input_policy` | `deny` | Default action for incoming traffic with no matching rule: drop it. |
| `ufw_default_output_policy` | `allow` | Default action for outgoing traffic: allow it. Most servers need unrestricted outbound. |
| `ufw_default_forward_policy` | `deny` | Default action for forwarded traffic (packets routed through this host): drop it. |
| `ufw_allowed_ports` | SSH only | List of `{port, proto, comment}` dicts. Add entries here to open additional ports. Each entry generates a `ufw allow` rule. |

### Sysctl (Kernel Parameters)

The `sysctl_settings` dict maps Linux kernel parameter names to their required values. These are written to `/etc/sysctl.d/99-bls-hardening.conf` and applied via `sysctl --system`. The file is numbered `99-` so it loads after Ubuntu's default `10-*` files and its values win any conflict.

| Parameter | Value | What it prevents |
|---|---|---|
| `net.ipv4.tcp_syncookies` | `1` | SYN flood attacks, which exhaust connection queues by sending half-open TCP connections. |
| `net.ipv4.conf.all.accept_source_route` | `0` | Source routing, where an attacker embeds a route in the packet to bypass routing decisions. |
| `net.ipv4.conf.default.accept_source_route` | `0` | Same as above, applied to new interfaces as they come up. |
| `net.ipv4.conf.all.accept_redirects` | `0` | ICMP redirect attacks, where a rogue host tricks the node into changing its routing table. |
| `net.ipv4.conf.default.accept_redirects` | `0` | Same, for new interfaces. |
| `net.ipv4.conf.all.secure_redirects` | `0` | Even "secure" ICMP redirects (from gateways in the routing table). Disabled entirely. |
| `net.ipv4.conf.all.log_martians` | `1` | Enables logging of packets with impossible source addresses (e.g. loopback addresses arriving from the network). Useful for detecting spoofing. |
| `net.ipv4.conf.default.log_martians` | `1` | Same, for new interfaces. |
| `net.ipv4.icmp_echo_ignore_broadcasts` | `1` | Smurf attacks, which amplify traffic by bouncing ICMP pings off broadcast addresses. |
| `net.ipv4.icmp_ignore_bogus_error_responses` | `1` | Prevents logging of malformed ICMP error responses that can flood logs. |
| `net.ipv4.conf.all.rp_filter` | `1` | Reverse-path filtering: drops packets whose source address is not reachable via the interface they arrived on. Mitigates spoofing. |
| `net.ipv4.conf.default.rp_filter` | `1` | Same, for new interfaces. |
| `net.ipv6.conf.all.accept_ra` | `0` | IPv6 Router Advertisement acceptance. Disabling prevents rogue devices from redirecting IPv6 traffic. |
| `net.ipv6.conf.default.accept_ra` | `0` | Same, for new interfaces. |
| `kernel.randomize_va_space` | `2` | Address space layout randomisation (ASLR), full mode. Makes it much harder for exploit code to find its targets in memory. |
| `kernel.sysrq` | `0` | The SysRq magic key combination, which can trigger reboots or memory dumps on a keyboard. Disabled on servers. |
| `fs.protected_hardlinks` | `1` | Prevents unprivileged users from creating hard links to files they do not own, which can be used in privilege escalation. |
| `fs.protected_symlinks` | `1` | Prevents following symlinks in world-writable directories unless the link owner matches the process. Blocks a class of TOCTOU attacks. |

### Resource Limits

The `limits_settings` list configures `/etc/security/limits.d/99-bls-hardening.conf` via PAM. Each entry specifies a domain (who it applies to), type (soft or hard), item (what resource), and value.

**nofile (open file descriptors):** Soft 65536, Hard 65536. A server process that opens many network connections or files hits the default limit of 1024 quickly. Setting this higher prevents "too many open files" errors under load.

**nproc (max processes):** Soft 4096, Hard 4096. Prevents a runaway process or a fork bomb from consuming all available process slots.

The soft limit is the default; a process can raise it to the hard limit itself. The hard limit can only be raised by root.

### fail2ban

| Variable | Default | What it controls |
|---|---|---|
| `fail2ban_bantime` | `3600` | Seconds a banned IP is blocked (1 hour). After this, the IP is automatically unbanned. |
| `fail2ban_findtime` | `600` | The lookback window in seconds. fail2ban counts failures within this window. |
| `fail2ban_maxretry` | `5` | Number of failures within `findtime` before an IP is banned. |
| `fail2ban_ignoreip` | `"127.0.0.1/8 ::1"` | Space-separated list of IPs never to ban. Always includes localhost to prevent self-locking. |

### NTP

| Variable | Default | What it controls |
|---|---|---|
| `ntp_servers` | UK NTP pool (0–3.uk.pool.ntp.org) | List of NTP pool addresses passed to chrony. The pool addresses are round-robin DNS entries that distribute load across many stratum-1 servers. |

### Packages

`packages_install` lists packages that must be present. `packages_remove` lists packages that must be absent (legacy tools with known vulnerabilities that no modern server needs).

---

## Task Files

### `tasks/main.yml` — Entry point and OS guard

This file does two things: it asserts that the target is Ubuntu 24.04 or later, and it imports all other task files. The OS assertion uses the `always` tag, meaning it runs even when you scope the playbook to a specific tag. If you accidentally point the playbook at a non-Ubuntu host, it fails immediately with a clear message rather than making unexpected changes.

### `tasks/packages.yml` — Package management

Refreshes the apt cache (but only if it is older than one hour, to avoid unnecessary network calls on repeated runs), removes legacy insecure packages (`telnet`, `rsh-client`, `nis`, etc.), installs the hardening tools (`ufw`, `fail2ban`, `chrony`, `auditd`, `libpam-pwquality`, `unattended-upgrades`), and enables automatic security upgrades via `debconf`.

The package removal uses `purge: true`, which also removes configuration files. This is intentional: a removed-but-configured `telnet` daemon is not meaningfully different from an installed one.

### `tasks/ssh.yml` — SSH daemon hardening

Deploys the hardened `sshd_config` from a Jinja2 template. The template task has `validate: /usr/sbin/sshd -t -f %s`, which runs `sshd`'s built-in config test against the file before it is written to disk. If the generated config is invalid for any reason, the task fails and the existing config is left untouched. It also sets `backup: true`, creating a timestamped `.bak` file as a recovery option.

After the config is deployed, the task ensures SSH is running and enabled. It then filters `/etc/ssh/moduli` to remove Diffie-Hellman groups shorter than 3072 bits. Weak DH groups (historically, 1024-bit) have been demonstrated to be factorable with nation-state resources (the Logjam attack). The filtering is done once and a sentinel file `/etc/ssh/.moduli_hardened` is written to prevent it running again.

### `tasks/ufw.yml` — Firewall rules

Sets default policies (deny inbound, allow outbound, deny forwarded) and opens only the ports listed in `ufw_allowed_ports`. The `community.general.ufw` module is natively idempotent: it checks whether a rule already exists before creating it, and returns `ok` rather than `changed` if the rule is already in place.

### `tasks/sysctl.yml` — Kernel parameter hardening

Writes `/etc/sysctl.d/99-bls-hardening.conf` from the `sysctl-hardening.conf.j2` template and notifies the `apply sysctl settings` handler if the file changed. The handler calls `sysctl --system`, which reloads all sysctl files in `/etc/sysctl.d/` in lexicographic order. Because our file is named `99-`, it is loaded last and its values take precedence over any conflicting defaults in Ubuntu's `10-*` files.

### `tasks/limits.yml` — Resource limits

Writes entries to `/etc/security/limits.d/99-bls-hardening.conf` via the `community.general.pam_limits` module and ensures `pam_limits.so` is referenced in both PAM session files. Without the PAM reference, the limits file exists but is never consulted at login time.

### `tasks/fail2ban.yml` — Brute-force protection

Deploys `/etc/fail2ban/jail.local` from a template, starts and enables the service, and verifies it is responding to `fail2ban-client status`. The `jail.local` file is the correct place for local overrides — it takes precedence over `/etc/fail2ban/jail.conf` (the package default) and survives package upgrades without being overwritten.

### `tasks/auditd.yml` — Audit logging

Deploys `/etc/audit/rules.d/99-bls-hardening.rules` with rules that record: privilege escalation (`setuid`/`setgid` calls), changes to identity files (`/etc/passwd`, `/etc/shadow`, `/etc/sudoers`), SSH config changes, cron changes, and failed login events. The rules file ends with `-e 2`, which puts auditd into immutable mode — the rules cannot be changed at runtime without a reboot. This protects the audit trail from being silenced by an attacker who has gained root.

After deploying the rules, `augenrules --load` is called to apply them without rebooting. This is best-effort (`failed_when: false`) because immutable mode from a previous run will prevent live reloading, requiring a reboot to pick up changes to the rules themselves.

### `tasks/ntp.yml` — Time synchronisation

Deploys the chrony configuration pointing at the UK NTP pool, ensures the service is running, and disables `systemd-timesyncd` (which conflicts with chrony if both are running). Accurate time is a security requirement: log timestamps, audit records, certificate validity checks, and Kerberos all depend on clocks being within a few seconds of each other.

---

## Templates

### `sshd_config.j2` → `/etc/ssh/sshd_config`

The generated SSH daemon configuration. Key settings:

- **`PermitRootLogin no`** — Forces attackers to escalate from a regular account rather than hitting root directly.
- **`PasswordAuthentication no`** — Only SSH keys work. A stolen password grants nothing.
- **`AllowUsers dev`** — sshd rejects any username not on this list at the protocol level, before PAM or any other check.
- **`KexAlgorithms`, `Ciphers`, `MACs`, `HostKeyAlgorithms`** — Restricted to algorithms considered strong as of OpenSSH 9.x (Curve25519, ChaCha20-Poly1305, AES-GCM, Ed25519). Older clients using legacy algorithms will be rejected. This is intentional on a server you control.
- **`X11Forwarding no`, `AllowTcpForwarding no`, `AllowAgentForwarding no`** — Closes tunnelling capabilities that are rarely needed on a server and can be abused to pivot through the SSH connection.
- **`LogLevel VERBOSE`** — Records the fingerprint of every key used to authenticate, which is essential for audit trails.

The template is validated by `sshd -t` before it reaches disk. An invalid config causes the task to fail without touching the live configuration.

### `sysctl-hardening.conf.j2` → `/etc/sysctl.d/99-bls-hardening.conf`

A straightforward template that iterates over the `sysctl_settings` dict and writes one `key = value` line per parameter. The file format is standard sysctl.d syntax. Adding a new parameter is as simple as adding it to `group_vars/all/vars.yml`; no template editing is needed.

### `fail2ban-jail.local.j2` → `/etc/fail2ban/jail.local`

Configures the global fail2ban defaults and the SSH jail. Notable settings:

- **`backend = systemd`** — Reads SSH failures from the systemd journal rather than a log file. This is the correct backend for Ubuntu 24.04, where sshd logs to journald by default.
- **`banaction = ufw`** — When an IP is banned, fail2ban uses UFW (`ufw deny from <IP>`) rather than iptables directly. This keeps firewall management in one place and makes ban rules visible in `ufw status`.
- **`logtarget = /var/log/fail2ban.log`** — Writes fail2ban's own log to a file for easy inspection.

### `chrony.conf.j2` → `/etc/chrony/chrony.conf`

Points chrony at the UK NTP pool (`0–3.uk.pool.ntp.org`) with `iburst` (fast initial sync) and `maxsources 4` (use up to 4 servers from each pool entry for resilience). Key settings:

- **`makestep 1.0 3`** — Allows the clock to be stepped (jumped) rather than slewed (gradually corrected) for the first three updates. Important after initial boot when the clock might be significantly wrong.
- **`rtcsync`** — Keeps the hardware real-time clock in sync with the system clock, so time survives a power cycle without drift.
- **`allow 127.0.0.1 / deny all`** — Only localhost can query chrony's NTP server port. The node is an NTP client, not a server.

---

## Idempotency Bugs Found and Fixed

Idempotency means that running the playbook multiple times produces the same result as running it once. It is a non-negotiable property for any Ansible role used in production: if a playbook shows `changed` on every run, you cannot tell real changes from noise, and automation pipelines that key off change counts will misfire.

Three bugs were found after the initial implementation and fixed. Here is what broke, why, and what the fix was.

### Bug 1: Moduli tasks showed `changed` on every run

**What broke:** After the first successful run, re-running the playbook produced this output — both moduli tasks reporting `changed` when nothing had actually changed on disk:

```
TASK [node-hardening : Disable SSH protocol 1 via moduli (remove small moduli)] ***
changed: [bls-node-01]

TASK [node-hardening : Mark moduli as hardened] ********************************
changed: [bls-node-01]

PLAY RECAP *********************************************************************
bls-node-01  : ok=27  changed=2  unreachable=0  failed=0  skipped=0
```

Expected second-run output (after fix):

```
TASK [node-hardening : Stat moduli sentinel file] ******************************
ok: [bls-node-01]

TASK [node-hardening : Remove weak Diffie-Hellman moduli (< 3072 bits)] ********
skipping: [bls-node-01]

TASK [node-hardening : Mark moduli as hardened] ********************************
skipping: [bls-node-01]
```

**Root cause:** The original code used `ansible.builtin.shell` with `creates: /etc/ssh/.moduli_hardened` to skip the task if a sentinel file existed. The `creates:` parameter works correctly, but a separate `changed_when: moduli_result.rc == 0` directive was evaluating the task's return code on every execution and unconditionally marking the result as `changed`. Separately, the "Mark moduli as hardened" task used `state: touch`, which always updates the file's modification time — the `file` module detects the mtime change and reports `changed`, even when the file already existed.

**Fix:** Three changes. First, replace `creates:` with an explicit `ansible.builtin.stat` check that records whether the sentinel file exists. Second, gate both the awk command and the marker task on `not moduli_sentinel.stat.exists`, so neither runs if the sentinel is already present. Third, replace `state: touch` with `ansible.builtin.copy` (using a fixed content string), which is genuinely idempotent — it compares file content on each run and only shows `changed` if the content differs.

```yaml
# Before (broken)
- name: Disable SSH protocol 1 via moduli
  ansible.builtin.shell:
    cmd: awk '$5 >= 3071' /etc/ssh/moduli > /tmp/moduli.safe && mv /tmp/moduli.safe /etc/ssh/moduli
    creates: /etc/ssh/.moduli_hardened
  register: moduli_result
  changed_when: moduli_result.rc == 0   # ← fires changed even when task is skipped

- name: Mark moduli as hardened
  ansible.builtin.file:
    path: /etc/ssh/.moduli_hardened
    state: touch   # ← always updates mtime, always reports changed
  when: moduli_result.changed

# After (fixed)
- name: Stat moduli sentinel file
  ansible.builtin.stat:
    path: /etc/ssh/.moduli_hardened
  register: moduli_sentinel

- name: Remove weak Diffie-Hellman moduli (< 3072 bits)
  ansible.builtin.shell:
    cmd: awk '$5 >= 3071' /etc/ssh/moduli > /tmp/moduli.safe && mv /tmp/moduli.safe /etc/ssh/moduli
  when: not moduli_sentinel.stat.exists
  changed_when: not moduli_sentinel.stat.exists   # ← only true when actually running

- name: Mark moduli as hardened
  ansible.builtin.copy:
    content: "hardened by ansible bls node-hardening role\n"
    dest: /etc/ssh/.moduli_hardened
    mode: "0600"
  when: not moduli_sentinel.stat.exists   # ← skipped if sentinel already exists
```

### Bug 2: UFW tasks showed `changed` on every run

**What broke:** On every run, all five UFW tasks reported `changed` — the PLAY RECAP always showed `changed=5` for the UFW block regardless of how many times the playbook had previously been applied:

```
TASK [node-hardening : Set UFW default input policy to deny] *******************
changed: [bls-node-01]

TASK [node-hardening : Set UFW default output policy to allow] *****************
changed: [bls-node-01]

TASK [node-hardening : Set UFW default forward policy to deny] *****************
changed: [bls-node-01]

TASK [node-hardening : Allow defined ports through UFW] ************************
changed: [bls-node-01] => (item={'port': 22, 'proto': 'tcp', 'comment': 'SSH'})

TASK [node-hardening : Enable UFW] *********************************************
changed: [bls-node-01]
```

The `state: reset` task above these was hiding in the PLAY RECAP because of `changed_when: false`, making it look like the reset wasn't running. It was running every time, silently wiping all rules.

**Root cause:** The original code included a `state: reset` task at the top of `ufw.yml`, intended to give UFW a clean starting state on first run. The bug: `state: reset` is not idempotent. It completely destroys all UFW rules and disables the firewall on every run, regardless of whether it has already been configured. The `changed_when: false` directive hid this from the PLAY RECAP, but the actual effect of wiping all rules forced every subsequent task to re-add everything, making them all show `changed`. The module saw "policy is currently ACCEPT but we want DENY" (because reset set it to default-accept), so it changed it — every time.

**Fix:** Remove the reset task entirely. The `community.general.ufw` module is natively idempotent for all the operations we need: it checks current default policies before setting them and checks existing rules before adding them. If the desired state already matches the current state, it returns `ok`. There is no need to start from a blank slate.

```yaml
# Before (broken) — reset wipes everything, forcing re-application on every run
- name: Reset UFW to defaults
  community.general.ufw:
    state: reset
  changed_when: false   # ← hides the reset, but damage is already done

- name: Set UFW default input policy to deny   # always changed because reset ran
  ...

# After (fixed) — rely on native idempotency
- name: Set UFW default input policy to deny   # ok on second run if already set
  community.general.ufw:
    default: deny
    direction: incoming
  notify: reload ufw
```

### Bug 3: `net.ipv4.conf.all.log_martians` showed `changed` on every run

**What broke:** On every run, the sysctl loop reported `changed` for `log_martians` despite having applied the value on the previous run. The relevant task output:

```
TASK [node-hardening : Apply kernel hardening sysctl parameters] ***************
changed: [bls-node-01] => (item={'key': 'net.ipv4.conf.all.log_martians', 'value': 1})
```

And running `sysctl --system` manually (without root) showed the `permission denied` lines and why the value wasn't sticking:

```
* Applying /etc/sysctl.d/99-bls-hardening.conf ...
sysctl: permission denied on key "net.ipv4.conf.all.log_martians", ignoring
net.ipv4.conf.all.log_martians = 1
```

The live kernel value read back as `0` even though the config file said `1`:

```bash
$ sysctl net.ipv4.conf.all.log_martians
net.ipv4.conf.all.log_martians = 0      # reads 0 even after writing 1
```

**Root cause:** The original code used `ansible.posix.sysctl` in a per-item loop with `reload: true`. This module works by reading the live kernel value via `sysctl -n`, comparing it to the desired value, and applying if different. The problem is specific to `net.ipv4.conf.all.*` parameters.

The `conf.all.*` namespace in the Linux networking stack is a **write aggregator**. Here is the clearest way to understand it: imagine your server has three network interfaces — `lo`, `eth0`, and `ens19`. Each interface has its own `log_martians` setting stored independently in the kernel. Writing to `net.ipv4.conf.all.log_martians = 1` is a shortcut that simultaneously sets all three. But reading it back does not return what you wrote — it returns the *minimum* of all individual interface values. If `lo` still has its per-interface value at `0` (the kernel default for loopback), reading `conf.all.log_martians` returns `0`, regardless of what you just wrote.

This means `sysctl -w net.ipv4.conf.all.log_martians=1` followed immediately by `sysctl -n net.ipv4.conf.all.log_martians` can return `0`. The `ansible.posix.sysctl` module performs exactly this write-then-read-back cycle. It always sees a mismatch, always marks the task `changed`, and perpetually re-applies — never converging.

This is a well-known quirk of the Linux networking sysctl namespace. It surfaces most visibly with `log_martians`, `accept_redirects`, and `rp_filter` on hosts with loopback-only or unassigned interfaces.

**Fix:** Replace the per-item `ansible.posix.sysctl` loop with a `template` task that writes the entire sysctl file at once, and move the application into a handler that calls `sysctl --system`. With this approach, Ansible's idempotency check is on the file contents (not the live kernel value): if the file matches the template, the task returns `ok` and the handler never fires. `sysctl --system` loads all files in lexicographic order, so `99-bls-hardening.conf` is loaded after Ubuntu's `10-*` files and wins any conflict.

```yaml
# Before (broken) — reads live kernel value, perpetually detects mismatch
- name: Apply kernel hardening sysctl parameters
  ansible.posix.sysctl:
    name: "{{ item.key }}"
    value: "{{ item.value | string }}"
    sysctl_file: /etc/sysctl.d/99-bls-hardening.conf
    reload: true
  loop: "{{ sysctl_settings | dict2items }}"

# After (fixed) — idempotency on file content, not live kernel value
- name: Deploy sysctl kernel hardening configuration
  ansible.builtin.template:
    src: sysctl-hardening.conf.j2
    dest: /etc/sysctl.d/99-bls-hardening.conf
    mode: "0644"
  notify: apply sysctl settings   # handler calls: sysctl --system
```

---

## Handlers

A handler in Ansible is a task that only runs if something notified it. Handlers are deduped — no matter how many tasks notify the same handler, it runs exactly once, at the end of the play. This is important for service restarts: if three different tasks all change files that require `sshd` to restart, sshd restarts once, not three times.

Handlers are defined in `handlers/main.yml`. A task notifies a handler by name using `notify: <handler name>`.

| Handler | Notified by | What it does |
|---|---|---|
| `restart sshd` | `ssh.yml` (template task) | Restarts the SSH daemon to pick up the new `sshd_config`. Runs at end of play, after all tasks complete, so sshd is never in a half-configured state. |
| `reload ufw` | `ufw.yml` (policy and rule tasks) | Reloads UFW rule state without tearing down existing connections. Used instead of `restart` because a full restart would briefly drop all connections. |
| `apply sysctl settings` | `sysctl.yml` (template task) | Calls `sysctl --system` to reload all `/etc/sysctl.d/` files in order. Only fires when the hardening config file actually changed. |
| `reload systemd daemon` | Available for future tasks that install unit files | Tells systemd to re-read its unit definitions. Required before `systemctl start` on a newly installed unit. |
| `restart fail2ban` | `fail2ban.yml` (template task) | Restarts fail2ban to load the new `jail.local`. Unlike `reload`, a restart clears all active bans. Bear this in mind during testing. |
| `restart auditd` | `auditd.yml` (rules task) | Restarts the audit daemon to pick up new rules. Note: because the rules file ends with `-e 2` (immutable mode), this restart will fail if rules are already loaded — use a reboot instead to change rules on a running system. |
| `restart chrony` | `ntp.yml` (template task) | Restarts the chrony NTP client to use the new server configuration. |

---

## Security Rationale

### SSH hardening — mitigates remote access attacks

The most common attack against an internet-connected server is SSH brute force: automated scripts try thousands of username/password combinations per minute. Disabling password authentication (`PasswordAuthentication no`) makes this class of attack completely ineffective — there is no password to guess. Restricting `AllowUsers` to `dev` means a valid key for `root` or any other account cannot be used even if someone obtains it. Restricting key exchange and cipher algorithms to modern, peer-reviewed cryptography closes the door to downgrade attacks where an attacker forces a connection to use a weaker algorithm they can break.

The DH moduli filter addresses the Logjam vulnerability (2015), which showed that 1024-bit Diffie-Hellman parameters were within reach of nation-state computation resources. By requiring groups of at least 3072 bits, we ensure that key exchange parameters are beyond feasible factoring attacks.

### UFW — implements a default-deny perimeter

A default-deny inbound policy means every inbound connection attempt is silently dropped unless there is an explicit rule allowing it. Compared to the Ubuntu default (no active firewall), this reduces the attack surface from all listening ports to only the ports explicitly opened. Any service that accidentally starts listening on an unexpected port cannot be reached from outside without a deliberate rule change.

### Sysctl — hardens the kernel's network stack and memory layout

These parameters address specific, well-documented attack techniques:

- **SYN cookies** prevent SYN flood DoS attacks that exhaust connection tables.
- **Source routing and ICMP redirects disabled** prevent man-in-the-middle attacks via routing manipulation.
- **Martian logging** aids forensics: if an attacker is spoofing source addresses, the packets appear in the kernel log.
- **Reverse-path filtering** drops spoofed packets at the kernel level, before they reach any application.
- **ASLR (randomize_va_space=2)** makes memory-based exploits unreliable by randomising the location of code and data in the address space. This is a core mitigation against buffer overflow exploitation.
- **Protected hardlinks and symlinks** block a class of local privilege escalation attacks where an unprivileged process creates filesystem references into privileged file paths.

### fail2ban — rate-limits authentication attempts

Even with password authentication disabled, a determined attacker may try to exhaust connection resources or probe for valid usernames. fail2ban watches the SSH log for repeated failures and instructs UFW to block the offending IP for one hour after five failed attempts within ten minutes. The IPs are blocked at the firewall level, so the connection is dropped before it reaches sshd. This reduces noise in logs, conserves server resources, and raises the cost of credential stuffing significantly.

### auditd — creates a tamper-evident audit trail

Auditd records specific system calls and file accesses to a kernel-level log that cannot be silenced by a process running as root (because immutable mode `-e 2` locks the ruleset after boot). The rules capture: privilege escalation attempts (`setuid`/`setgid` syscalls), modifications to `/etc/passwd`, `/etc/shadow`, `/etc/sudoers` (identity changes), changes to `/etc/ssh/sshd_config` (configuration tampering), and cron modifications (persistence mechanisms). In the event of a compromise, these records allow forensic reconstruction of what the attacker did and when.

### NTP (chrony) — ensures accurate time for logs and cryptography

Time accuracy is a prerequisite for several security functions. Log correlation across hosts becomes impossible if clocks drift. Certificate validation compares timestamps and will reject valid certificates whose time window has passed. Some authentication protocols (Kerberos, TOTP) reject tokens more than a few seconds old. Chrony replaces `systemd-timesyncd` (which is less configurable and less accurate) and synchronises against four UK NTP pool servers for resilience.

---

## Troubleshooting

### SSH and sshd

**Locked out after the playbook runs — SSH refuses connection**

The most likely cause is that `AllowUsers` does not include your username, or the public key you are connecting with is not in `~/.ssh/authorized_keys` on the node. You cannot recover this over SSH — you need console access.

**Recovery path on Proxmox (this node runs as a Proxmox VM):**

1. Open the Proxmox web UI: `https://<proxmox-host>:8006`
2. In the left panel: Datacenter → your node → the VM (look for the VM name or ID)
3. Click **Console** in the top toolbar — this opens a noVNC terminal directly on the VM, bypassing SSH entirely
4. Log in as `dev` at the console prompt
5. Restore the backup that Ansible created automatically:

```bash
# List the available backups (Ansible writes one per change with a timestamp)
ls /etc/ssh/sshd_config*.bak

# Restore the most recent backup
sudo cp /etc/ssh/sshd_config.2026-05-01@21:00~.bak /etc/ssh/sshd_config

# Verify it is valid before restarting
sudo sshd -t && echo "Config OK"

# Restart SSH — your next SSH connection should work
sudo systemctl restart ssh
```

If no `.bak` file exists (e.g. the template task failed before writing the backup), restore the Ubuntu shipped default:

```bash
sudo cp /usr/share/openssh/sshd_config /etc/ssh/sshd_config
sudo systemctl restart ssh
# Then re-run the playbook from scratch to re-apply hardening
```

**"Permission denied (publickey)" immediately after the role applies**

The role configured `AllowUsers dev`. If you are connecting as a different user, or your key is not present, the connection will be rejected with this message.

```bash
# Confirm what user you are connecting as
ssh -v dev@<homelab-subnet>.50   # check the username in the debug output

# Confirm your key is in authorized_keys on the node
cat ~/.ssh/authorized_keys
```

**sshd_config validation fails during the template task**

The `validate:` parameter runs `sshd -t` against the candidate file before writing it. If this step fails, it usually means a variable expanded to an invalid value (e.g. `ssh_allow_users` containing a character sshd does not accept).

```bash
# Validate the current live config
sudo sshd -t

# Generate what the template would produce and test it manually
ansible bls-node-01 -m template -a "src=roles/node-hardening/templates/sshd_config.j2 dest=/tmp/sshd_config_test"
sudo sshd -t -f /tmp/sshd_config_test
```

**SSH log location**

```bash
journalctl -u ssh -f           # live tail
journalctl -u ssh -n 100       # last 100 lines
journalctl -u ssh --since "1 hour ago"
```

### UFW

**UFW blocked your SSH session mid-run**

If the playbook runs the UFW tasks but your source IP is not covered by an allow rule, you will be disconnected. This cannot happen in the current setup because `ansible_connection: local` runs entirely on the node itself. For remote SSH-based connections, always run in `--check` mode first:

```bash
./scripts/bls-run.sh check -t ufw
```

Before applying, confirm your IP is in `ufw_allowed_ports` or that the SSH rule is correct:

```bash
sudo ufw status numbered
```

**A port you need is not open after apply**

Add it to `ufw_allowed_ports` in `group_vars/all/vars.yml` and re-run:

```bash
./scripts/bls-run.sh run -t ufw
sudo ufw status numbered   # verify
```

**Docker bridge networks blocked after UFW is enabled**

UFW's default FORWARD policy (`deny`) blocks forwarded packets, which breaks Docker's inter-container routing. Docker creates a bridge network interface (typically `docker0`) and expects to route packets between containers through it — UFW silently drops those packets.

This node has a secondary interface `ens19` that is currently unassigned. If Docker is added later and binds to `ens19`, all container traffic on that interface will be dropped by the default-deny FORWARD policy. The symptom is containers that can reach the host but cannot reach each other or the internet.

Do not change `ufw_default_forward_policy` to `allow` — that weakens protection for all non-Docker traffic. Instead, add interface-scoped FORWARD rules:

```bash
# Allow inter-container routing on Docker's bridge
sudo ufw route allow in on docker0

# If Docker binds to ens19 and routes out through eth0
sudo ufw route allow in on ens19 out on eth0
```

Add these as a dedicated task in `tasks/docker.yml` when Docker is introduced, so they are tracked in version control and not forgotten.

**"ERROR: problem running ufw" during the enable task**

This usually means UFW is in a partially initialised state. Check:

```bash
sudo ufw --force reset   # WARNING: clears all rules
sudo systemctl restart ufw
./scripts/bls-run.sh run -t ufw
```

**UFW log location**

```bash
sudo tail -f /var/log/ufw.log
journalctl -u ufw -f
```

### fail2ban

**fail2ban fails to start — "Failed to start fail2ban"**

Check the journal for the actual error:

```bash
journalctl -u fail2ban -n 50 --no-pager
```

Common cause: `jail.local` references a filter or action that does not exist. The BLS config uses `backend = systemd` — if systemd journal support is not compiled into the installed fail2ban, this will fail:

```bash
# Check if systemd backend is available
fail2ban-client --version
# If systemd is missing from the output, switch backend to "auto" in vars.yml
```

**You banned yourself during testing**

```bash
# List banned IPs in the sshd jail
sudo fail2ban-client status sshd

# Unban your IP
sudo fail2ban-client set sshd unbanip <your-ip>

# Or unban everything
sudo fail2ban-client unban --all
```

**"Could not find the requested service fail2ban" in check mode**

This is expected. In `--check` mode, the playbook simulates changes without applying them. If the service start task is simulated as `ok` but the service is not actually running, the `fail2ban-client status` verification task will fail. This is a known limitation of check mode with service-dependent verification tasks. Run in `run` mode on an actual node.

**Journal backend errors in fail2ban log**

```bash
# Check the fail2ban log
sudo tail -50 /var/log/fail2ban.log

# Common fix: ensure the systemd Python binding is installed
sudo apt install python3-systemd
sudo systemctl restart fail2ban
```

**fail2ban log location**

```bash
sudo tail -f /var/log/fail2ban.log
journalctl -u fail2ban -f
```

### sysctl

**"permission denied on key" when applying sysctl**

This appears when `sysctl --system` or `sysctl -w` is run without root. The Ansible play uses `become: true`, so this should not occur during a normal run. If you see it when running sysctl manually:

```bash
sudo sysctl --system   # requires root
```

**Settings not surviving a reboot**

If values reset after reboot, confirm that `/etc/sysctl.d/99-bls-hardening.conf` exists and contains the expected values:

```bash
cat /etc/sysctl.d/99-bls-hardening.conf
```

If the file is missing, re-run the playbook. If it exists but values are still reset, check whether a later-loaded service is calling `sysctl -w` to override specific parameters:

```bash
grep -r "sysctl" /etc/networkd-dispatcher/ /etc/NetworkManager/dispatcher.d/ 2>/dev/null
```

**Conflicting values from other sysctl.d files (the log_martians case)**

Ubuntu ships `/etc/sysctl.d/10-network-security.conf` which sets `rp_filter=2`. The BLS file sets it to `1`. Because `99-bls-hardening.conf` is loaded last (`99 > 10` in lexicographic order), the BLS value wins at boot.

To verify the final effective value:

```bash
# What is live in the kernel right now
sysctl net.ipv4.conf.all.rp_filter

# What each sysctl.d file says
grep rp_filter /etc/sysctl.d/*.conf

# Simulate the full load order (requires root to apply)
sudo sysctl --system 2>&1 | grep rp_filter
```

**Check what value is live vs what is in config**

```bash
# Live kernel value
sysctl net.ipv4.conf.all.log_martians

# What the config file says
grep log_martians /etc/sysctl.d/99-bls-hardening.conf

# Apply the config file immediately
sudo sysctl -p /etc/sysctl.d/99-bls-hardening.conf

# Or reload all sysctl.d files
sudo sysctl --system
```

### auditd

**auditd fails to restart after rule changes**

This is expected when the rules include `-e 2` (immutable mode). Once immutable mode is active, the ruleset is locked until reboot. `auditd restart` succeeds (the daemon restarts), but `augenrules --load` will fail because the running kernel refuses to accept new rules.

```bash
# Check if immutable mode is active
sudo auditctl -s | grep enabled
# enabled = 2 means immutable — reboot required to change rules

# After reboot, the new rules file is loaded automatically
sudo reboot
sudo auditctl -l   # verify after reboot
```

**"backlog limit exceeded" in the kernel log**

Auditd's kernel-side queue is filling up. Increase the backlog buffer in the rules file:

```bash
sudo grep -n "backlog" /etc/audit/rules.d/99-bls-hardening.rules
# Add near the top of the rules file if missing:
# -b 8192
```

Then reboot (required because of immutable mode).

**Rules not loading after reboot**

```bash
# Check which rules files exist
ls /etc/audit/rules.d/

# Manually compile and load (if not immutable)
sudo augenrules --load

# Check for syntax errors in the rules file
sudo auditctl -R /etc/audit/rules.d/99-bls-hardening.rules

# Check the audit log for errors
sudo tail -50 /var/log/audit/audit.log
```

**auditd log location**

```bash
sudo tail -f /var/log/audit/audit.log
sudo ausearch -k identity         # search by key (identity changes)
sudo ausearch -k privilege_escalation
sudo ausearch -k sshd_config
```

### Chrony

**chrony is not synchronising**

```bash
# Check tracking status
chronyc tracking

# Check source health
chronyc sources -v

# Check the service log
journalctl -u chrony -n 50 --no-pager
```

If `Reference ID` shows `7F7F0101` (127.127.1.1), chrony has fallen back to the local clock because it cannot reach any NTP servers. Check network connectivity from the node.

**chrony log location**

```bash
journalctl -u chrony -f
ls /var/log/chrony/
chronyc tracking
```

---

## Quick Diagnostic Runbook

Run these commands in order when something looks broken after the playbook has been applied. Each command is read-only and safe to run at any time.

```bash
# 1. Check that all managed services are active
systemctl status ssh fail2ban auditd chrony --no-pager -l

# 2. Check firewall rules — should show port 22 allowed, default DENY
sudo ufw status numbered

# 3. Check fail2ban is running and which jails are active
sudo fail2ban-client status
sudo fail2ban-client status sshd

# 4. Look for recent authentication failures
sudo journalctl -u ssh -n 50 --no-pager

# 5. Compare live sysctl values against what the config file says
sysctl net.ipv4.conf.all.log_martians net.ipv4.tcp_syncookies kernel.randomize_va_space
grep -v "^#" /etc/sysctl.d/99-bls-hardening.conf | grep -v "^$"

# 6. Check whether any IPs are currently banned
sudo fail2ban-client status sshd | grep "Banned IP"

# 7. Check UFW log for recent connection drops
sudo tail -30 /var/log/ufw.log

# 8. Verify sshd_config is syntactically valid (no error = good)
sudo sshd -t && echo "sshd_config is valid"

# 9. Confirm PAM file-descriptor limit is active (should be 65536)
ulimit -n

# 10. Verify auditd rules are loaded
sudo auditctl -l | grep -E "identity|privilege|sudoers|sshd_config"

# 11. Check chrony is synchronised (look for "System time" offset < 1ms)
chronyc tracking

# 12. Ping all inventory hosts from the control node
cd ~/Desktop/BLS-DevOps && ./scripts/bls-run.sh ping

# 13. Dry-run the playbook to detect drift from desired state
./scripts/bls-run.sh check

# 14. Check the system error log for anything unusual in the last hour
sudo journalctl -p err --since "1 hour ago" --no-pager
```
