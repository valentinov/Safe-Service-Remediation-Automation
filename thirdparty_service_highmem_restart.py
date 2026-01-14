#!/usr/bin/env python3
"""
thirdparty_service_highmem_restart.py

Manager-node job
----------------
- Reads hosts from INVENTORY_FILE (if present + non-empty) else INVENTORY list
- SSH to each host and collects:
    - whether ONE specific systemd service is running (MainPID != 0)
    - %MEM of that service process (ps %mem, integer)
- Safety rule (HA):
    - Before restarting the service on a node, ensure at least
      MIN_OTHER_RUNNING_NODES *other* nodes are currently running the service.
- If restart happens:
    - Write a timestamped marker file on the MANAGER node
- Always:
    - Write a per-run log file on the MANAGER node

Target node prerequisites
-------------------------
- systemd must be available on target nodes
- SSH user must be allowed to run (passwordless sudo):
    /bin/systemctl restart <SERVICE_NAME>

  Example (sudo visudo):
    vagrant ALL=(root) NOPASSWD: /bin/systemctl restart memhog

Scheduling (cron)
-----------------
Example: run every 10 minutes

    crontab -e

    */10 * * * * /usr/bin/python3 \
      /opt/thirdparty_highmem_restart/thirdparty_service_highmem_restart.py \
      >> /var/log/thirdparty_highmem_restart/cron.log 2>&1
"""

import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# =========================
# CONFIG
# =========================
INVENTORY = ["192.168.56.11", "192.168.56.12"]
INVENTORY_FILE = "/opt/thirdparty_highmem_restart/inventory.txt"

SSH_USER = "vagrant"
SSH_KEY = "/home/vagrant/.ssh/highmem_ed25519"
CONNECT_TIMEOUT_SEC = 8

SERVICE_NAME = "memhog"   # systemd unit on target node (for testing used a custom service called memhog)
MEM_THRESHOLD = 60        # % of total RAM (ps %mem)

MIN_OTHER_RUNNING_NODES = 1

BASE_DIR = Path("/var/log/thirdparty_highmem_restart")
RUNS_DIR = BASE_DIR / "runs"
TRIGGERS_DIR = BASE_DIR / "triggers"

# Remote probe: read-only (no restart)
REMOTE_PROBE = r"""
set -euo pipefail

SERVICE="__SERVICE__"

PID=$(systemctl show -p MainPID --value "$SERVICE" || true)
if [ -z "$PID" ] || [ "$PID" = "0" ]; then
  echo "STATE stopped service=${SERVICE}"
  exit 0
fi

PMEM_RAW=$(ps -p "$PID" -o %mem= || true)
PMEM_INT=$(echo "$PMEM_RAW" | awk '{printf("%d\n",$1)}')

echo "STATE running service=${SERVICE} pid=${PID} mem=${PMEM_INT}"
"""

REMOTE_RESTART = r"""
set -euo pipefail
SERVICE="__SERVICE__"
sudo systemctl restart "$SERVICE"
echo "RESTARTED service=${SERVICE}"
"""


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_hosts() -> tuple[list[str], str]:
    """
    Return (hosts, source) where source is 'file' or 'array'.
    """
    if INVENTORY_FILE and os.path.exists(INVENTORY_FILE):
        with open(INVENTORY_FILE, "r", encoding="utf-8") as f:
            hosts = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
        if hosts:
            return hosts, "file"
    return INVENTORY, "array"


def parse_int_kv(output: str, key: str):
    """
    Parse key=<digits> from output; returns int or None.
    """
    m = re.search(rf"\b{re.escape(key)}=([0-9]+)\b", output)
    return int(m.group(1)) if m else None


def ssh(host: str, script: str) -> tuple[int, str]:
    """
    Run a bash script on the host by sending it over STDIN.
    This avoids 'bash -c requires an argument' caused by quoting issues.
    """
    cmd = [
        "ssh",
        "-i", SSH_KEY,
        "-o", "BatchMode=yes",
        "-o", f"ConnectTimeout={CONNECT_TIMEOUT_SEC}",
        "-o", "StrictHostKeyChecking=accept-new",
        f"{SSH_USER}@{host}",
        "bash", "-s",
    ]
    p = subprocess.run(cmd, input=script, capture_output=True, text=True)
    output = (p.stdout + p.stderr).strip()
    return p.returncode, output

def write_marker(host: str, run_id: str, mem: int | None, pid: int | None, note: str) -> Path:
    TRIGGERS_DIR.mkdir(parents=True, exist_ok=True)
    mem_part = f"mem{mem}" if mem is not None else "mem_unknown"

    host_safe = host.replace(":", "_").replace("/", "_").replace(" ", "_")
    filename = f"{host_safe}_{run_id}_{mem_part}.txt"

    path = TRIGGERS_DIR / filename
    path.write_text(
        "\n".join([
            f"timestamp_utc={run_id}",
            f"host={host}",
            f"service={SERVICE_NAME}",
            f"threshold_percent={MEM_THRESHOLD}",
            f"memory_percent={mem if mem is not None else 'unknown'}",
            f"pid={pid if pid is not None else 'unknown'}",
            "action=restart",
            f"note={note}",
            "",
        ]),
        encoding="utf-8",
    )
    return path


def main() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    TRIGGERS_DIR.mkdir(parents=True, exist_ok=True)

    run_id = utc_stamp()
    hosts, source = load_hosts()

    run_log = RUNS_DIR / f"run_{run_id}.log"
    lines: list[str] = [
        f"run_id={run_id}",
        f"nodes_source={source}",
        f"service={SERVICE_NAME}",
        f"threshold_percent={MEM_THRESHOLD}",
        f"min_other_running_nodes={MIN_OTHER_RUNNING_NODES}",
        f"nodes={len(hosts)}",
        "",
    ]

    # 1) Probe all nodes: running + pid + mem
    states: dict[str, dict] = {}
    probe_script = REMOTE_PROBE.replace("__SERVICE__", SERVICE_NAME)

    for host in hosts:
        rc, out = ssh(host, probe_script)

        if rc == 0 and "STATE running" in out:
            states[host] = {
                "running": True,
                "pid": parse_int_kv(out, "pid"),
                "mem": parse_int_kv(out, "mem"),
                "raw": out,
                "rc": rc,
            }
        else:
            states[host] = {
                "running": False,
                "pid": None,
                "mem": None,
                "raw": out,
                "rc": rc,
            }

        status = "RUNNING" if states[host]["running"] else f"NOT_RUNNING(rc={rc})"
        lines.append(f"[{host}] PROBE {status} :: {out}")

    running_hosts = [h for h, s in states.items() if s["running"]]
    lines.append("")
    lines.append(f"running_hosts={len(running_hosts)} :: {', '.join(running_hosts) if running_hosts else '(none)'}")
    lines.append("")

    # 2) Decide + restart safely
    restart_script_tpl = REMOTE_RESTART.replace("__SERVICE__", SERVICE_NAME)

    for host in hosts:
        s = states[host]
        if not s["running"]:
            continue

        mem = s["mem"]
        if mem is None:
            lines.append(f"[{host}] SKIP restart - mem unknown :: {s['raw']}")
            continue

        if mem <= MEM_THRESHOLD:
            lines.append(f"[{host}] OK - mem={mem}% <= {MEM_THRESHOLD}%")
            continue

        other_running = [h for h in running_hosts if h != host]
        if len(other_running) < MIN_OTHER_RUNNING_NODES:
            lines.append(
                f"[{host}] SKIP restart - high mem={mem}% but only {len(other_running)} other nodes running "
                f"(min required {MIN_OTHER_RUNNING_NODES})"
            )
            continue

        lines.append(f"[{host}] RESTART allowed - high mem={mem}% and other_running={len(other_running)}")
        rc, out = ssh(host, restart_script_tpl)
        status = "SUCCESS" if rc == 0 else f"FAIL(rc={rc})"
        lines.append(f"[{host}] RESTART {status} :: {out}")

        if rc == 0:
            marker = write_marker(
                host=host,
                run_id=run_id,
                mem=mem,
                pid=s["pid"],
                note=f"Restarted because mem={mem}% > {MEM_THRESHOLD}%, other_running={len(other_running)}",
            )
            lines.append(f"[{host}] manager_marker={marker}")

    run_log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote manager run log: {run_log}")


if __name__ == "__main__":
    main()
