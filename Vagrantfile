Vagrant.configure("2") do |config|
  config.vm.box = "ubuntu/jammy64"

  # ==================
  # MANAGER NODE
  # ==================
  config.vm.define "manager" do |mgr|
    mgr.vm.hostname = "manager"
    mgr.vm.network "private_network", ip: "192.168.56.10"

    mgr.vm.provider "virtualbox" do |vb|
      vb.memory = 1024
      vb.cpus = 1
    end

    mgr.vm.provision "shell", inline: <<-SHELL
      set -euo pipefail

      apt-get update
      apt-get install -y python3 openssh-client

      mkdir -p /opt/thirdparty_highmem_restart
      mkdir -p /var/log/thirdparty_highmem_restart/{runs,triggers}
      chown -R vagrant:vagrant /opt/thirdparty_highmem_restart
      chown -R vagrant:vagrant /var/log/thirdparty_highmem_restart

      # Copy automation + inventory from repo into manager
      if [ -f /vagrant/thirdparty_service_highmem_restart.py ]; then
        cp -f /vagrant/thirdparty_service_highmem_restart.py /opt/thirdparty_highmem_restart/
        chown vagrant:vagrant /opt/thirdparty_highmem_restart/thirdparty_service_highmem_restart.py
        chmod 755 /opt/thirdparty_highmem_restart/thirdparty_service_highmem_restart.py
      fi

      if [ -f /vagrant/inventory.txt ]; then
        cp -f /vagrant/inventory.txt /opt/thirdparty_highmem_restart/inventory.txt
        chown vagrant:vagrant /opt/thirdparty_highmem_restart/inventory.txt
        chmod 644 /opt/thirdparty_highmem_restart/inventory.txt
      else
        cat > /opt/thirdparty_highmem_restart/inventory.txt <<'EOF'
192.168.56.11
192.168.56.12
EOF
        chown vagrant:vagrant /opt/thirdparty_highmem_restart/inventory.txt
        chmod 644 /opt/thirdparty_highmem_restart/inventory.txt
      fi

      # ---- SSH automation key (dedicated) ----
      install -d -m 700 /home/vagrant/.ssh

      if [ ! -f /home/vagrant/.ssh/highmem_ed25519 ]; then
        ssh-keygen -t ed25519 -N "" -f /home/vagrant/.ssh/highmem_ed25519
      fi

      chown -R vagrant:vagrant /home/vagrant/.ssh
      chmod 600 /home/vagrant/.ssh/highmem_ed25519
      chmod 644 /home/vagrant/.ssh/highmem_ed25519.pub

      # Expose public key to other nodes via synced folder
      cp -f /home/vagrant/.ssh/highmem_ed25519.pub /vagrant/manager_highmem_ed25519.pub
    SHELL
  end

  # ==================
  # TARGET NODE SETUP (shared)
  # ==================
  TARGET_PROVISION = <<-SHELL
    set -euo pipefail

    apt-get update
    apt-get install -y openssh-server sudo python3

    # Place memhog script
    install -d /opt/memhog
    if [ -f /vagrant/memhog.bash ]; then
      cp -f /vagrant/memhog.bash /opt/memhog/memhog.bash
    else
      # Fallback (keeps provisioning working even if file missing)
      cat > /opt/memhog/memhog.bash <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import time
x = []
while True:
  x.append(bytearray(10 * 1024 * 1024))
  time.sleep(1)
PY
EOF
    fi
    chmod 755 /opt/memhog/memhog.bash

    # Create systemd unit
    cat > /etc/systemd/system/memhog.service <<'EOF'
[Unit]
Description=Deterministic memory-consuming test service (memhog)
After=network.target

[Service]
Type=simple
ExecStart=/opt/memhog/memhog.bash
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable --now memhog.service

    # Scoped sudo: allow restarting ONLY memhog
    cat > /etc/sudoers.d/highmem <<'EOF'
vagrant ALL=(root) NOPASSWD: /bin/systemctl restart memhog
EOF
    chmod 440 /etc/sudoers.d/highmem

    # ---- Trust manager SSH key (automation key) ----
    install -d -m 700 /home/vagrant/.ssh
    touch /home/vagrant/.ssh/authorized_keys
    chmod 600 /home/vagrant/.ssh/authorized_keys

    if [ -f /vagrant/manager_highmem_ed25519.pub ]; then
      grep -qxF "$(cat /vagrant/manager_highmem_ed25519.pub)" /home/vagrant/.ssh/authorized_keys \
        || cat /vagrant/manager_highmem_ed25519.pub >> /home/vagrant/.ssh/authorized_keys
    fi

    chown -R vagrant:vagrant /home/vagrant/.ssh
  SHELL

  # ==================
  # NODE 1
  # ==================
  config.vm.define "node1" do |n1|
    n1.vm.hostname = "node1"
    n1.vm.network "private_network", ip: "192.168.56.11"

    n1.vm.provider "virtualbox" do |vb|
      vb.memory = 1024
      vb.cpus = 1
    end

    n1.vm.provision "shell", inline: TARGET_PROVISION
  end

  # ==================
  # NODE 2
  # ==================
  config.vm.define "node2" do |n2|
    n2.vm.hostname = "node2"
    n2.vm.network "private_network", ip: "192.168.56.12"

    n2.vm.provider "virtualbox" do |vb|
      vb.memory = 1024
      vb.cpus = 1
    end

    n2.vm.provision "shell", inline: TARGET_PROVISION
  end
end
