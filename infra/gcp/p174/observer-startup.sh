#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y ca-certificates curl gnupg jq
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" >/etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

systemctl enable --now docker

cat >/usr/local/sbin/p174-block-container-metadata.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

iptables -N DOCKER-USER 2>/dev/null || true
iptables -C DOCKER-USER -d 169.254.169.254/32 -j REJECT 2>/dev/null \
  || iptables -I DOCKER-USER 1 -d 169.254.169.254/32 -j REJECT
iptables -C DOCKER-USER -j RETURN 2>/dev/null \
  || iptables -A DOCKER-USER -j RETURN
EOF
chmod 0755 /usr/local/sbin/p174-block-container-metadata.sh

cat >/etc/systemd/system/p174-block-container-metadata.service <<'EOF'
[Unit]
Description=Block P174 containers from reaching the GCP metadata IP
After=docker.service
Wants=docker.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/p174-block-container-metadata.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now p174-block-container-metadata.service

cat >/etc/systemd/system/p174-expiry-shutdown.service <<'EOF'
[Unit]
Description=Stop the disposable P174 VM at the credit-expiry boundary

[Service]
Type=oneshot
ExecStart=/sbin/shutdown -h now
EOF
cat >/etc/systemd/system/p174-expiry-shutdown.timer <<'EOF'
[Unit]
Description=Schedule P174 VM shutdown for 2026-08-01 UTC

[Timer]
OnCalendar=2026-08-01 00:00:00 UTC
Persistent=true
Unit=p174-expiry-shutdown.service

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now p174-expiry-shutdown.timer

install -d -m 0755 /opt/opscat/p174

cat >/opt/opscat/p174/README.txt <<'EOF'
P174 observer host bootstrap complete.
Observer and evaluator deployment is supplied by the later P174 workload ticket.
This script installs host runtime prerequisites and blocks container access to the metadata IP.
EOF
