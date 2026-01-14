# Create a simple memory consumer script
sudo tee /usr/local/bin/memhog.py >/dev/null <<'EOF'
#!/usr/bin/env python3
import time

# Allocate ~600MB
data = bytearray(600 * 1024 * 1024)

print("Memory allocated, sleeping...")
while True:
    time.sleep(10)
EOF

sudo chmod +x /usr/local/bin/memhog.py

# Create a systemd service
sudo tee /etc/systemd/system/memhog.service >/dev/null <<'EOF'
[Unit]
Description=Intentional Memory Hog Test Service
After=network.target

[Service]
ExecStart=/usr/bin/python3 /usr/local/bin/memhog.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Reload + start
sudo systemctl daemon-reload
sudo systemctl enable --now memhog