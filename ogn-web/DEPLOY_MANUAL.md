# Manual Deployment to flarm2.local

Since the automated script has SSH config issues, follow these manual steps:

## Step 1: Build Frontend

```bash
cd /Users/simone/Apps/hfss-pi-flarm-rx/ogn-web/frontend
npm install
npm run build
```

## Step 2: Create Deployment Package

```bash
cd /Users/simone/Apps/hfss-pi-flarm-rx/ogn-web
tar -czf ogn-web-deploy.tar.gz backend/ frontend/dist/ ../.env
```

## Step 3: Copy to Raspberry Pi

```bash
scp ogn-web-deploy.tar.gz hfss@flarm2.local:/tmp/
```

## Step 4: Setup on Raspberry Pi

SSH into the Pi:
```bash
ssh hfss@flarm2.local
```

Then run:
```bash
# Create directory
mkdir -p /home/hfss/ogn-web
cd /home/hfss/ogn-web

# Extract
tar -xzf /tmp/ogn-web-deploy.tar.gz
rm /tmp/ogn-web-deploy.tar.gz

# Setup Python environment
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
```

## Step 5: Test Backend

```bash
cd /home/hfss/ogn-web/backend
source ../venv/bin/activate
python3 main.py
```

Test in browser: `http://flarm2.local:8082/api/config`

Press `Ctrl+C` to stop.

## Step 6: Create Systemd Service

```bash
sudo nano /etc/systemd/system/ogn-web.service
```

Paste:
```ini
[Unit]
Description=OGN Web Configuration Interface
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=hfss
Group=hfss
WorkingDirectory=/home/hfss/ogn-web/backend
Environment="PATH=/home/hfss/ogn-web/venv/bin"
ExecStart=/home/hfss/ogn-web/venv/bin/python3 main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=ogn-web

[Install]
WantedBy=multi-user.target
```

Save (`Ctrl+O`, `Enter`, `Ctrl+X`)

## Step 7: Enable and Start Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable ogn-web
sudo systemctl start ogn-web
sudo systemctl status ogn-web
```

## Step 8: Configure Sudo Permissions

```bash
sudo nano /etc/sudoers.d/ogn-web
```

Paste:
```
hfss ALL=(ALL) NOPASSWD: /usr/sbin/ip link set wlan0 *
hfss ALL=(ALL) NOPASSWD: /usr/sbin/ip link set eth1 *
hfss ALL=(ALL) NOPASSWD: /sbin/wpa_cli *
hfss ALL=(ALL) NOPASSWD: /usr/sbin/service rtlsdr-ogn *
```

Save and set permissions:
```bash
sudo chmod 440 /etc/sudoers.d/ogn-web
```

## Step 9: Access the Interface

Open in browser:
- **Direct API**: `http://flarm2.local:8082`
- **Frontend (if using nginx)**: `http://flarm2.local`

## Logs

```bash
# View service logs
sudo journalctl -u ogn-web -f

# Check service status
sudo systemctl status ogn-web

# Restart service
sudo systemctl restart ogn-web
```

## Troubleshooting

### Backend won't start
```bash
# Check Python version
python3 --version  # Should be 3.9+

# Check dependencies
cd /home/hfss/ogn-web/backend
source ../venv/bin/activate
pip list

# Test manually
python3 main.py
```

### Config file not found
Update paths in `backend/main.py`:
```python
CONFIG_FILE = '/home/hfss/ogn-pi34/rtlsdr-ogn-0.3.2/Template.conf'
WPA_SUPPLICANT = '/etc/wpa_supplicant/wpa_supplicant.conf'
```

### Permission denied errors
Check sudo configuration:
```bash
sudo -l
```

Should show NOPASSWD entries.
