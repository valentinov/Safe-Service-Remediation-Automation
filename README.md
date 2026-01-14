# Safe Service Remediation Automation (Demo)

## Overview

This repository demonstrates a **manager-based remediation automation** that safely restarts a `systemd` service **only when memory usage exceeds a defined threshold and high-availability (HA) conditions are met**.

The goal is to show a **production-grade automation pattern**, not just a script:

* Deterministic triggering (no random load)
* Fleet-aware safety and quorum enforcement
* Explicit, auditable decision logging
* Fully reproducible local validation

> All names, services, and environments are intentionally generic and anonymized.
> This repository demonstrates the *pattern*, not a production deployment.

---

## Architecture

### Nodes

* **Manager node (1)**

  * Runs the Python remediation automation
  * Probes fleet state over SSH
  * Makes restart decisions
  * Writes structured run logs and trigger markers

* **Target nodes (2)**

  * Run the monitored `systemd` service (`memhog`)
  * Allow passwordless restart **for that service only**

### Communication

* SSH (key-based authentication)
* No agents
* No inbound access required on target nodes

```
manager
 ├─ SSH → node1
 └─ SSH → node2
```

---

## What the Automation Does

1. Reads target nodes from an inventory file
2. Probes each node to determine:

   * Whether the service is running (`MainPID != 0`)
   * Memory usage (`%MEM`) of the service process
3. Builds a **fleet-wide state view**
4. Applies a safety rule:

   * Restart is allowed **only if at least N other nodes are healthy**
5. If a restart occurs:

   * A timestamped **trigger marker** is written on the manager
6. Always:

   * A **per-run structured log** is written on the manager

At no point can the automation restart the **last healthy node**.

---

## Deterministic Test Service (`memhog`)

To avoid stressing real services, a **dedicated test service** is used.

`memhog` is a simple `systemd` unit that:

* Allocates memory in a predictable way
* Behaves like a normal long-running service
* Can be restarted independently on each node

This enables:

* Repeatable memory threshold testing
* Safe quorum validation
* Predictable restart behavior

---

## Local Validation Environment

The solution is validated locally using **Vagrant + VirtualBox**:

* 1× Ubuntu manager node
* 2× Ubuntu target nodes
* `systemd` enabled on all nodes
* Automatic SSH trust bootstrapping

This mirrors **real VM behavior**, not containers or mocks.

---

## SSH Trust (Automatic)

During provisioning:

* A **dedicated SSH key** is generated on the manager node
* The public key is automatically added to:

  ```
  ~vagrant/.ssh/authorized_keys
  ```

  on both target nodes
* Existing SSH keys are preserved

No manual SSH setup is required.

The automation uses this key:

```
/home/vagrant/.ssh/highmem_ed25519
```

---

## Repository Structure

```
.
├── Vagrantfile
│   Creates manager + target nodes and bootstraps SSH trust
│
├── thirdparty_service_highmem_restart.py
│   Manager-side remediation automation
│
├── memhog.bash
│   Deterministic memory-consuming test service
│
├── inventory.txt (optional)
│   Target node IPs (defaults provided if missing)
│
├── screenshots/
│   Demonstrates behavior under different fleet states
│
└── README.md
```

---

## Demonstrated Scenarios

### Restart One by One (Both Nodes Over Threshold)

**Screenshot:**
`test-run01-service-runs-both-restart-one-by-one-treshold-gt60-on-both.png`

**Scenario**

* Service running on both nodes
* Memory usage exceeds threshold (>60%) on both

**Expected behavior**

* Nodes are restarted **one at a time**
* Quorum is preserved at all times
* No simultaneous restarts

---

### No Restart Without Quorum

**Screenshot:**
`test-run02-service-runs-one-node-no-restart.png`

**Scenario**

* Service running on only one node
* Other node unavailable or stopped

**Expected behavior**

* No restart performed
* Automation detects lack of quorum
* Logs clearly explain the decision

---

### Targeted Restart Only

**Screenshot:**
`test-run03-service-runs-both-restart-only-where-treshold-gt60.png`

**Scenario**

* Service running on both nodes
* Threshold exceeded on only one node

**Expected behavior**

* Restart performed **only on affected node**
* Healthy node untouched
* Availability preserved

---

## Logs & Observability

All logs are written **on the manager node**.

* **Per-run logs**

  ```
  /var/log/thirdparty_highmem_restart/runs/
  ```

* **Restart trigger markers**

  ```
  /var/log/thirdparty_highmem_restart/triggers/
  ```

Logs are:

* Human-readable
* Timestamped
* Explicit about *why* a restart was or was not performed

This makes the automation **audit-friendly**.

---

## Scheduling

Designed to run periodically via `cron`.

**Example: run every 10 minutes**

```bash
*/10 * * * * /usr/bin/python3 \
  /opt/thirdparty_highmem_restart/thirdparty_service_highmem_restart.py \
  >> /var/log/thirdparty_highmem_restart/cron.log 2>&1
```

---

## System Requirements

### Manager Node

* Ubuntu
* Python 3
* OpenSSH client

### Target Nodes

* Ubuntu
* systemd
* OpenSSH server
* `sudo` (scoped to a single systemctl command)

> No web servers (Apache/Nginx) are used or required.

---

## Key Design Principles

* **Safety first**
  Never restart the last healthy node

* **Deterministic testing**
  Predictable, repeatable triggers

* **Minimal privileges**
  Passwordless sudo limited to:

  ```
  systemctl restart memhog
  ```

* **Operational clarity**
  Logs explain decisions, not just actions

* **Reproducibility**
  `vagrant up` is sufficient to run the demo

---

## How to Run

```bash
vagrant up
vagrant ssh manager
python3 /opt/thirdparty_highmem_restart/thirdparty_service_highmem_restart.py
```

---

## Intended Audience

This repository is suitable for:

* DevOps
* HA remediation discussions
* Safe automation design reviews
* Fleet-aware operations demos
* Regulated-environment examples
