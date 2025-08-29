# Deployment guide — Ubuntu (systemd + nginx)

This document explains how to deploy the `tbuddy_translation_TG-tool` Flask relay on an Ubuntu server using a Python virtualenv, Gunicorn, systemd and nginx with TLS (Let's Encrypt / certbot). It also includes Git commit and push instructions for pushing your local changes to GitHub.

## Assumptions
- You have root or sudo access on the server.
- You will run the service as a dedicated user `tbuddy`.
- Your repo will be checked out to `/opt/tbuddy` on the server.
- You have a domain name pointing to the server's public IP.

## 1) Prepare server (Ubuntu 22.04+)

1. Update and install dependencies:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.11 python3.11-venv python3-pip nginx certbot python3-certbot-nginx build-essential
```

2. Create a system user and directories:

```bash
sudo useradd -r -s /bin/false tbuddy
sudo mkdir -p /opt/tbuddy
sudo chown tbuddy:tbuddy /opt/tbuddy
```

3. Clone your repo into /opt/tbuddy (or rsync/upload the project)

```bash
sudo -u tbuddy git clone https://github.com/<your-user>/tbuddy_translation_TG-tool.git /opt/tbuddy
cd /opt/tbuddy
```

4. Create Python venv and install requirements

```bash
python3.11 -m venv /opt/tbuddy/venv
source /opt/tbuddy/venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate
```

## 2) Configure environment secrets

Create an environment file for systemd (kept out of Git):

```bash
sudo mkdir -p /etc/tbuddy
sudo tee /etc/tbuddy/env > /dev/null <<'ENV'
TELEGRAM_API_TOKEN=<your_telegram_token>
DIRECT_LINE_SECRET=<your_direct_line_secret>
PORT=8080
USE_WAITRESS=0
DEBUG_LOCAL=0
DEBUG_VERBOSE=0
ENV

sudo chown -R root:root /etc/tbuddy
sudo chmod 640 /etc/tbuddy/env
```

Replace placeholders with your real secrets. Using an EnvironmentFile keeps secrets out of the unit file.

## 3) Install systemd unit and nginx config

1. Copy the systemd unit into place:

```bash
sudo cp deploy/tbuddy.service /etc/systemd/system/tbuddy.service
sudo systemctl daemon-reload
sudo systemctl enable --now tbuddy
sudo systemctl status tbuddy
```

2. Copy nginx site configuration and enable it (edit server_name first):

```bash
sudo cp deploy/tbuddy.nginx.conf /etc/nginx/sites-available/tbuddy
sudo ln -s /etc/nginx/sites-available/tbuddy /etc/nginx/sites-enabled/tbuddy
sudo nginx -t && sudo systemctl reload nginx
```

3. Obtain TLS cert via certbot:

```bash
sudo certbot --nginx -d your-domain.example.com
```

## 4) Telegram webhook

Set webhook URL (after TLS is configured):

```bash
curl -F "url=https://your-domain.example.com/webhook" "https://api.telegram.org/bot${TELEGRAM_API_TOKEN}/setWebhook"
curl "https://api.telegram.org/bot${TELEGRAM_API_TOKEN}/getWebhookInfo"
```

## 5) Notes on SQLite and concurrency

- SQLite is fine for a single-worker setup. If you choose to run multiple Gunicorn workers, either run a single worker (`--workers 1`) or migrate to Postgres (recommended for production/high concurrency).

## 6) Healthchecks & logs

- Use `systemctl status tbuddy` and `journalctl -u tbuddy -f` to follow logs. Nginx logs are in `/var/log/nginx/`.
- Consider logrotate for `journalctl` or configure app logging to a file and rotate.

## 7) Git: commit and push your changes

From your local Windows machine (inside project root):

1. Review changed files:

```powershell
git status --porcelain
git add -A
git commit -m "Improve Direct Line parsing, add local debug, add deploy configs"
git push origin main
```

If you need to split commits, use `git add <file>` selectively before `git commit`.

If you haven't set your Git remote yet, run:

```powershell
git remote add origin https://github.com/<your-user>/tbuddy_translation_TG-tool.git
git push -u origin main
```

## 8) Quick rollback plan

- If the service misbehaves, stop the service and inspect logs:

```bash
sudo systemctl stop tbuddy
sudo journalctl -u tbuddy -n 200 --no-pager
```

Then revert to previous commit and redeploy.

---
If you want, I can create the exact `systemd` file and `nginx` site in the repo (done), and also prepare a compact `deploy.sh` script. Say "Add deploy script" and I'll add it.
