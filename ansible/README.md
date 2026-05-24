# Ansible — BLS Portfolio Week 3

This directory contains the Ansible automation for the BLS homelab portfolio. Its job is to apply a security baseline to Ubuntu 24.04 nodes in a repeatable, auditable way. Every time the playbook runs, it checks the node against the desired state and corrects any drift — without you having to remember which commands to run.

The design decision to use Ansible over Cloud-Init is explained in [ADR-003](../docs/adr/ADR-003-ansible-over-cloud-init.md). The short version: Cloud-Init runs once at first boot and cannot be re-run. Ansible runs on demand, is idempotent (safe to run repeatedly), and shows you exactly what it changed.

---

## Prerequisites

Before running the playbook, confirm the following.

**Ansible version.** This role requires Ansible 2.15 or later (ships with Ubuntu 24.04's `ansible` package or via pip).

```bash
ansible --version
```

**Required collections.** Two Galaxy collections are needed. They are likely already installed on the homelab, but run this to be sure:

```bash
ansible-galaxy collection install community.general ansible.posix
```

**Passwordless sudo.** The playbook uses `become: true` to elevate to root. The `dev` user must be able to run `sudo` without a password prompt. Check with:

```bash
sudo -n true && echo "OK"
```

If that prints `sudo: a password is required`, see the Troubleshooting section below before proceeding.

**SSH key on the node.** Because the role disables password authentication, you must have an SSH public key in `~/.ssh/authorized_keys` on the node before running. If you are running locally (the default), this is already satisfied.

---

## Quick Start

From a fresh clone to a hardened node:

```bash
# 1. Enter the repo
cd ~/Desktop/BLS-DevOps

# 2. Install required Ansible collections (one-time; safe to re-run)
ansible-galaxy collection install community.general ansible.posix

# 3. Dry-run first — see what will change without touching anything
./scripts/bls-run.sh check

# 4. Apply
./scripts/bls-run.sh run
```

Run again immediately to confirm idempotency — the PLAY RECAP must show `changed=0`:

```bash
./scripts/bls-run.sh run
# Expected: ok=28   changed=0   unreachable=0   failed=0
```

> **Before step 3:** confirm `sudo -n true` succeeds (passwordless sudo is required), and that your SSH public key is in `~/.ssh/authorized_keys`. See [Prerequisites](#prerequisites) for the full checklist. If either is missing, the playbook will fail early — see Troubleshooting below.

---

## bls-run.sh — Full Usage Reference

`scripts/bls-run.sh` is a thin wrapper around `ansible-playbook`. It sets the working directory correctly regardless of where you call it from, and exposes a consistent interface for all day-2 operations.

**Synopsis**

```
./scripts/bls-run.sh <command> [options]
```

**Commands**

| Command  | What it does |
|----------|--------------|
| `run`    | Run the full playbook. Applies all hardening tasks. |
| `check`  | Dry-run. Shows what *would* change without touching the system. Combine with `-v` to see diffs. |
| `syntax` | Parse the playbook YAML and role imports for syntax errors. Does not connect to any host. |
| `ping`   | Send an Ansible ping to all inventory hosts. Confirms connectivity and privilege escalation work. |
| `tags`   | List all available tags, so you know which subsystems you can target individually. |

**Options**

| Flag       | Meaning |
|------------|---------|
| `-t TAGS`  | Run only tasks with these tags, comma-separated. Example: `-t ssh,ufw` |
| `-l LIMIT` | Target only specific hosts or groups. Example: `-l bls-node-01` |
| `-v`       | Enable verbose output (`-vvv`). Shows module arguments, return values, and diff for every task. |
| `-h`       | Print the help message. |

**Examples**

```bash
# Full apply
./scripts/bls-run.sh run

# Dry-run with diff — see exactly what sysctl.d file would change
./scripts/bls-run.sh check -t sysctl -v

# Re-apply only SSH and firewall after editing group_vars
./scripts/bls-run.sh run -t ssh,ufw

# Check one specific host in a multi-node inventory
./scripts/bls-run.sh run -l bls-node-01

# Confirm the inventory is reachable before a full run
./scripts/bls-run.sh ping

# Syntax-check before committing a role change
./scripts/bls-run.sh syntax
```

---

## Directory Structure

```
ansible/
├── ansible.cfg                    # Ansible settings: inventory path, become, callback format
├── site.yml                       # Top-level playbook — maps the nodes group to the role
├── inventory/
│   └── hosts.yml                  # Host definitions: IPs, connection type, user
├── group_vars/
│   └── all/
│       └── vars.yml               # All tunable variables: SSH port, UFW rules, sysctl values, NTP, etc.
└── roles/
    └── node-hardening/
        ├── defaults/
        │   └── main.yml           # Low-priority defaults (overridden by group_vars)
        ├── vars/
        │   └── main.yml           # Role-internal constants (file paths, etc.)
        ├── meta/
        │   └── main.yml           # Galaxy metadata: platform, min Ansible version
        ├── handlers/
        │   └── main.yml           # Service restart/reload triggers (only fire when notified)
        ├── tasks/
        │   ├── main.yml           # Entry point: imports all task files in order
        │   ├── packages.yml       # Install / remove packages, enable auto-updates
        │   ├── ssh.yml            # Deploy hardened sshd_config, filter weak DH moduli
        │   ├── ufw.yml            # Set firewall default policies, open allowed ports
        │   ├── sysctl.yml         # Write /etc/sysctl.d/99-bls-hardening.conf
        │   ├── limits.yml         # Set file descriptor and process limits via PAM
        │   ├── fail2ban.yml       # Deploy jail config, enable and verify service
        │   ├── auditd.yml         # Deploy audit rules for privilege escalation and config changes
        │   └── ntp.yml            # Configure chrony with UK NTP pool, disable timesyncd
        └── templates/
            ├── sshd_config.j2           # Hardened SSH daemon config
            ├── sysctl-hardening.conf.j2 # Kernel parameter file for /etc/sysctl.d/
            ├── fail2ban-jail.local.j2   # fail2ban SSH jail with UFW ban action
            └── chrony.conf.j2           # NTP client config pointing at UK pool
```

The companion scripts live outside `ansible/` at the repo root level:

```
scripts/
├── bls-run.sh        # Ansible wrapper (run/check/syntax/ping/tags)
└── bls-cost-check.sh # Azure CLI cost summary for the subscription
```

---

## How to Extend the Role

### Adding a new allowed port

Open `ansible/group_vars/all/vars.yml` and add an entry to `ufw_allowed_ports`:

```yaml
ufw_allowed_ports:
  - { port: "{{ ssh_port }}", proto: tcp, comment: SSH }
  - { port: 443,              proto: tcp, comment: HTTPS }
  - { port: 9090,             proto: tcp, comment: Prometheus }
```

Then apply only the firewall tasks:

```bash
./scripts/bls-run.sh run -t ufw
```

### Adding a new sysctl parameter

Open `ansible/group_vars/all/vars.yml` and add to the `sysctl_settings` dict:

```yaml
sysctl_settings:
  # ... existing entries ...
  net.core.somaxconn: 1024
```

Apply:

```bash
./scripts/bls-run.sh run -t sysctl
```

### Adding a new task file

Create `ansible/roles/node-hardening/tasks/your-area.yml`, write your tasks, then import it in `tasks/main.yml`:

```yaml
- name: Include your-area tasks
  ansible.builtin.import_tasks: your-area.yml
  tags: [your-tag]
```

Any new handler your tasks notify must be added to `handlers/main.yml`. Always test with `check` before `run`, and verify the second run shows `changed=0`.

---

## Running Against Multiple Nodes

The current inventory targets a single node. To add more, edit `ansible/inventory/hosts.yml`:

```yaml
all:
  children:
    nodes:
      hosts:
        bls-node-01:
          ansible_host: <homelab-subnet>.50
          ansible_connection: local
          ansible_user: dev
        bls-node-02:
          ansible_host: <homelab-subnet>.51
          ansible_user: dev
          # no ansible_connection: local — reaches node-02 over SSH from node-01
```

Remove `ansible_connection: local` for remote nodes so Ansible connects over SSH. The `remote_user: dev` in `ansible.cfg` applies by default; override per-host by setting `ansible_user` in the inventory entry.

To run against one node only:

```bash
./scripts/bls-run.sh run -l bls-node-01
```

Per-host variable overrides (e.g. a different SSH port) go in `ansible/host_vars/<hostname>/vars.yml`.

---

## Troubleshooting

### Ansible Connectivity

**"sudo: a password is required"**

The `dev` user is not configured for passwordless sudo, which `become: true` requires.

```bash
# Check whether passwordless sudo works
sudo -n true && echo "OK" || echo "NEEDS PASSWORD"

# Fix: add dev to the sudoers file (run as root or an existing sudoer)
echo "dev ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/dev-nopasswd
sudo chmod 0440 /etc/sudoers.d/dev-nopasswd

# Verify
sudo -n true && echo "OK"
```

**"UNREACHABLE — Connection refused"**

Ansible cannot reach the host. For `ansible_connection: local` this should never happen unless the task runner is on a different machine. For SSH-based connections:

```bash
# Test raw connectivity first
ssh dev@<homelab-subnet>.50

# Check that sshd is listening
ss -tlnp | grep :22

# Check UFW isn't blocking port 22
sudo ufw status | grep 22
```

**"FAILED — MODULE FAILURE" on gather_facts**

Python is not available on the target at the expected path, or there is a library version mismatch.

```bash
# Check Python version on the node
python3 --version

# Confirm Ansible can find it
ansible bls-node-01 -m raw -a "python3 --version"
```

**Permission denied (publickey) after the role applies**

The role disables password authentication. If your public key was not in `~/.ssh/authorized_keys` before the run, you will be locked out over SSH.

Recovery: use the physical console or out-of-band access, then:

```bash
# Add your public key manually
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo "<your-public-key>" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

**Locked out after sshd_config change**

The template task deploys with `validate: /usr/sbin/sshd -t -f %s`, which refuses to write an invalid config. A valid-but-wrong config (wrong AllowUsers, wrong port) can still lock you out.

The template task also writes `backup: true`, which creates a timestamped `.bak` file alongside the deployed config:

```bash
# Restore the backup (use physical console if SSH is down)
ls /etc/ssh/sshd_config*.bak
sudo cp /etc/ssh/sshd_config.2026-05-01@21:00~.bak /etc/ssh/sshd_config
sudo systemctl restart ssh

# Or restore the Ubuntu default
sudo cp /usr/share/openssh/sshd_config /etc/ssh/sshd_config
sudo systemctl restart ssh
```

### General Ansible Operations

**Run a single area when something breaks**

Each task file has a tag. Use `-t` to scope the run:

```bash
./scripts/bls-run.sh run -t ssh        # SSH config and moduli only
./scripts/bls-run.sh run -t ufw        # Firewall only
./scripts/bls-run.sh run -t sysctl     # Kernel parameters only
./scripts/bls-run.sh run -t fail2ban   # fail2ban only
./scripts/bls-run.sh run -t auditd     # Audit rules only
./scripts/bls-run.sh run -t ntp        # NTP/chrony only
./scripts/bls-run.sh run -t packages   # Package install/remove only
```

**See exactly what changed (diff mode)**

```bash
./scripts/bls-run.sh check -v
```

The `-v` flag passes `-vvv` to ansible-playbook, which activates `--diff` output for template and file tasks. You will see a unified diff of every file change before it is applied.

**Increase verbosity to debug a specific failure**

| Level | What it shows |
|-------|---------------|
| `-v`  | Module arguments, return values, diff output |
| (no flag) | Default: task names and PLAY RECAP only |

`bls-run.sh -v` always uses `-vvv`. For a lower verbosity, run ansible-playbook directly:

```bash
cd ~/Desktop/BLS-DevOps/ansible
ansible-playbook site.yml -v    # module args only
ansible-playbook site.yml -vv   # + connection info
ansible-playbook site.yml -vvv  # + full return values and diffs
```

**Where Ansible logs live**

Ansible does not write a log file by default. All output goes to stdout, which `bls-run.sh` prints directly to your terminal. To save a log, redirect:

```bash
./scripts/bls-run.sh run 2>&1 | tee ~/bls-run-$(date +%Y%m%d-%H%M%S).log
```

To add persistent logging, set `log_path` in `ansible.cfg`:

```ini
[defaults]
log_path = ~/Desktop/BLS-DevOps/logs/ansible.log
```

---

## Quick Diagnostic Runbook

Run these commands in order when something looks broken after the playbook has been applied. Each command is safe and read-only.

```bash
# 1. Confirm core services are active
systemctl status ssh fail2ban auditd chrony --no-pager -l

# 2. Check firewall rules and status
sudo ufw status numbered

# 3. Check fail2ban is running and which jails are active
sudo fail2ban-client status
sudo fail2ban-client status sshd

# 4. Look for recent authentication failures in SSH logs
sudo journalctl -u ssh -n 50 --no-pager

# 5. Check live sysctl values vs what the config file says
sysctl net.ipv4.conf.all.log_martians net.ipv4.tcp_syncookies kernel.randomize_va_space
grep -v "^#" /etc/sysctl.d/99-bls-hardening.conf | grep -v "^$"

# 6. Check if you or anyone is currently banned by fail2ban
sudo fail2ban-client status sshd | grep "Banned IP"

# 7. Check the UFW log for recent blocks
sudo tail -30 /var/log/ufw.log

# 8. Verify sshd_config is syntactically valid
sudo sshd -t && echo "sshd_config OK"

# 9. Confirm PAM file descriptor limit is in effect (should be 65536)
ulimit -n

# 10. Check auditd rules are loaded
sudo auditctl -l | grep -E "bls|privilege|identity|sudoers"

# 11. Check chrony is synchronised
chronyc tracking

# 12. Ping all inventory hosts
cd ~/Desktop/BLS-DevOps && ./scripts/bls-run.sh ping

# 13. Dry-run to detect any drift from desired state
./scripts/bls-run.sh check

# 14. Check system error log for anything unusual in the last hour
sudo journalctl -p err --since "1 hour ago" --no-pager
```
