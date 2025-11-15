# Docker Deployment Guide

Deploy the OGN Web Configuration interface using Docker on flarm2.local.

## Prerequisites

On the Raspberry Pi, ensure Docker is installed:

```bash
# Check if Docker is installed
docker --version

# If not installed:
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker hfss
# Logout and login again
```

## Deployment Steps

### 1. Copy Project to Raspberry Pi

From your Mac:

```bash
cd /Users/simone/Apps/hfss-pi-flarm-rx
rsync -avz --exclude 'node_modules' --exclude 'dist' --exclude '.git' \
  ogn-web/ hfss@flarm2.local:/home/hfss/ogn-web/
```

### 2. SSH into Raspberry Pi

```bash
ssh hfss@flarm2.local
cd /home/hfss/ogn-web
```

### 3. Create credentials directory

```bash
mkdir -p credentials
chmod 700 credentials
```

### 4. Stop old services (if any)

```bash
# Stop old Flask service
sudo systemctl stop ogn-config-web 2>/dev/null || true
sudo systemctl disable ogn-config-web 2>/dev/null || true

# Stop old Python service
sudo systemctl stop ogn-web 2>/dev/null || true
sudo systemctl disable ogn-web 2>/dev/null || true

# Remove old service files
sudo rm -f /etc/systemd/system/ogn-config-web.service
sudo rm -f /etc/systemd/system/ogn-web.service
sudo systemctl daemon-reload
```

### 5. Build and Start with Docker Compose

```bash
# Build the image (this will take a few minutes)
docker compose build

# Start the service
docker compose up -d

# Check logs
docker compose logs -f
```

### 6. Verify it's Running

```bash
# Check container status
docker compose ps

# Test API
curl http://localhost:8082/health

# View logs
docker compose logs ogn-web
```

## Access the Interface

Open in browser:
- **Direct API**: `http://flarm2.local:8082`
- **Frontend**: `http://flarm2.local:8082` (serves static files)

## Management Commands

```bash
# View logs
docker compose logs -f

# Restart
docker compose restart

# Stop
docker compose down

# Rebuild after code changes
docker compose down
docker compose build --no-cache
docker compose up -d

# View resource usage
docker stats ogn-web
```

## Auto-start on Boot

Docker Compose with `restart: unless-stopped` will automatically start the container on boot.

To verify:
```bash
docker compose ps
```

## Troubleshooting

### Container won't start

```bash
# Check logs
docker compose logs ogn-web

# Check if config files exist
ls -la /home/hfss/ogn-pi34/rtlsdr-ogn-0.3.2/Template.conf
ls -la /etc/wpa_supplicant/wpa_supplicant.conf
```

### Permission issues

```bash
# Ensure volumes are accessible
sudo chmod 644 /home/hfss/ogn-pi34/rtlsdr-ogn-0.3.2/Template.conf
sudo chmod 644 /etc/wpa_supplicant/wpa_supplicant.conf
```

### Network interface management not working

Docker needs privileged mode for network management. Check `docker-compose.yml`:
```yaml
privileged: true
network_mode: host
```

### Can't access system info

Ensure volumes are mounted:
```yaml
volumes:
  - /sys/class/thermal:/sys/class/thermal:ro
  - /proc:/host/proc:ro
```

### Rebuild from scratch

```bash
docker compose down
docker rmi ogn-web:latest
docker compose build --no-cache
docker compose up -d
```

## Environment Variables

Edit `.env` file in the project root:

```bash
MANUFACTURER_SECRET_OGN=your_secret_here
```

Docker Compose will automatically load this file.

## Updating the Application

### Update code from Mac

```bash
# On Mac
cd /Users/simone/Apps/hfss-pi-flarm-rx
rsync -avz --exclude 'node_modules' --exclude 'dist' --exclude '.git' \
  ogn-web/ hfss@flarm2.local:/home/hfss/ogn-web/
```

### Rebuild and restart on Pi

```bash
# On Pi
cd /home/hfss/ogn-web
docker compose down
docker compose build
docker compose up -d
```

## Remove Old Installation

If you had the old Flask/systemd setup:

```bash
# Remove old files
rm -f /home/hfss/ogn-config-web.py
rm -rf /home/hfss/ogn-web/venv

# Remove old service
sudo systemctl stop ogn-web 2>/dev/null || true
sudo systemctl disable ogn-web 2>/dev/null || true
sudo rm -f /etc/systemd/system/ogn-web.service
sudo systemctl daemon-reload
```

## Benefits of Docker Deployment

1. **Isolated environment** - No Python version conflicts
2. **Easy updates** - Just rebuild and restart
3. **Auto-restart** - Container restarts automatically
4. **Resource limits** - Can set memory/CPU limits
5. **Portable** - Same setup works on any system
6. **Clean uninstall** - Just `docker compose down`

## Monitoring

```bash
# Real-time logs
docker compose logs -f ogn-web

# Resource usage
docker stats ogn-web

# Container details
docker inspect ogn-web

# Check health
docker compose ps
curl http://localhost:8082/health
```
