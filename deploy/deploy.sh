#!/usr/bin/env bash
set -euo pipefail

echo "This is a helper script with suggestions for deploying the tbuddy service."
echo "It does not modify remote servers. Run the printed commands on the target Ubuntu host as sudo."

cat <<'CMD'
# On Ubuntu server (run as root or with sudo):
apt update && apt install -y python3 python3-venv python3-pip nginx certbot python3-certbot-nginx
useradd -r -s /bin/false tbuddy || true
mkdir -p /opt/tbuddy
# clone repo into /opt/tbuddy, create venv, install deps:
cd /opt/tbuddy
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate

# Create environment file:
mkdir -p /etc/tbuddy
echo "TELEGRAM_API_TOKEN=..." > /etc/tbuddy/env
echo "DIRECT_LINE_SECRET=..." >> /etc/tbuddy/env
chmod 640 /etc/tbuddy/env

# Copy systemd unit and nginx config from repo deploy/
cp deploy/tbuddy.service /etc/systemd/system/tbuddy.service
cp deploy/tbuddy.nginx.conf /etc/nginx/sites-available/tbuddy
ln -s /etc/nginx/sites-available/tbuddy /etc/nginx/sites-enabled/tbuddy || true
systemctl daemon-reload
systemctl enable --now tbuddy
nginx -t && systemctl reload nginx

CMD

echo "Script finished. Review commands above and run them on the target server." 
