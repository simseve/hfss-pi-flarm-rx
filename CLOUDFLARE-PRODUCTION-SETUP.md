# Cloudflare Zero Trust - Production Setup for OGN IoT Devices

Complete production-ready deployment guide for thousands of OGN Raspberry Pi receivers with Cloudflare Zero Trust.

## Overview

This setup provides three critical capabilities:

1. **Secure API Access** - Service token authentication for heartbeat/registration APIs
2. **Remote SSH Access** - SSH into any Raspberry Pi from your Alpium server
3. **Web Interface Access** - Access device web interfaces via Cloudflare Tunnel

## Architecture

```
┌─────────────────┐      HTTPS + Service Token      ┌──────────────────┐
│  Raspberry Pi   │ ──────────────────────────────▶ │  ogn.alpium.io   │
│   (Thousands)   │    Heartbeat + Registration     │   API Server     │
└─────────────────┘                                  └──────────────────┘
        │
        │ Cloudflare Tunnel (outbound only)
        │
        ▼
┌─────────────────┐
│   Cloudflare    │
│   Zero Trust    │
│   - SSH Tunnel  │
│   - Web Tunnel  │
└─────────────────┘
        │
        │ SSH / HTTPS
        ▼
┌─────────────────┐
│  Alpium Server  │
│  - SSH Access   │
│  - Web Access   │
└─────────────────┘
```

---

## Part 1: Cloudflare Dashboard Configuration

### 1.1 Service Token for API Authentication

**Purpose**: Allows Raspberry Pis to authenticate to `ogn.alpium.io` API

1. Go to https://one.dash.cloudflare.com/
2. Navigate: **Access controls** → **Service credentials** → **Service Tokens**
3. Click **Create Service Token**
4. Name: `OGN Raspberry Pi Devices`
5. **Save these credentials** (shown only once):
   ```
   Client ID: 3e7da9e5eb83a5ffc00d6abb7aa6ab7a.access
   Client Secret: 64806145af6fd811d2f9db3e1b130761b87f4667a41bbcfc1532be31a6039157
   ```

### 1.2 Access Application for OGN API

**Purpose**: Protects API endpoint with service token authentication

1. Navigate: **Access** → **Applications**
2. Click **Add an application** → **Self-hosted**
3. Configure:
   - **Application name**: `Ogn`
   - **Session duration**: `24 hours`
   - **Application domain**:
     - Subdomain: (empty or `ogn`)
     - Domain: `alpium.io`
4. Add policy:
   - **Policy name**: `Service auth`
   - **Action**: `Service Auth`
5. Save application

### 1.3 Cloudflare Tunnel for Device Access

**Purpose**: Enables SSH and web access to Raspberry Pis from anywhere

1. Navigate: **Networks** → **Tunnels**
2. Click **Create a tunnel**
3. Select **Cloudflared** tunnel type
4. Name: `ogn-devices`
5. **Save tunnel token**:
   ```
   eyJhIjoiMDBiNmU2MzZjNDZhODgwNjUyOWZmNzljOWY4YThhYWQiLCJ0IjoiNDA1MTRiNjEtYTVjNy00NjM0LWI5YTgtODVmY2YxYTJkNDRjIiwicyI6Ik5URmlZVGRrWWpBdFpqbGpZUzAwTkdFeExUaGtPRE10T0dOaU05OHhaVFEzWVdGbSJ9
   ```

6. **Add Public Hostnames** (click **Public Hostname** tab):

   **a) SSH Access**:
   - Subdomain: `ssh_ogn`
   - Domain: `alpium.io`
   - Service Type: `SSH`
   - URL: `localhost:22`

   **b) Configuration Web Server (port 8082)**:
   - Subdomain: `web_ogn`
   - Domain: `alpium.io`
   - Service Type: `HTTP`
   - URL: `localhost:8082`

   **c) OGN Status Page (port 8080)**:
   - Subdomain: `ogn_ogn`
   - Domain: `alpium.io`
   - Service Type: `HTTP`
   - URL: `localhost:8080`

---

## Part 2: Raspberry Pi Configuration

### 2.1 Environment Configuration

Create/update `.env` file with API endpoint and service token:

```bash
cd ~/hfss-pi-flarm-rx

cat > .env << 'EOF'
MANUFACTURER_SECRET_OGN=DpJGWXuPInyF7LXtiTlLt7tWgB_A0sUtNpL0km4Tyb4
HFSS_SERVER_URL=https://ogn.alpium.io/api/v1
CF_ACCESS_CLIENT_ID=3e7da9e5eb83a5ffc00d6abb7aa6ab7a.access
CF_ACCESS_CLIENT_SECRET=64806145af6fd811d2f9db3e1b130761b87f4667a41bbcfc1532be31a6039157
EOF
```

### 2.2 Python Script Updates

The `ogn-config-web-hfss.py` script has been updated with:

1. **Cloudflare headers function** (added after line 41):
```python
def get_cloudflare_headers():
    """Get Cloudflare Access service token headers if configured"""
    headers = {}
    client_id = load_env_var('CF_ACCESS_CLIENT_ID')
    client_secret = load_env_var('CF_ACCESS_CLIENT_SECRET')

    if client_id and client_secret:
        headers['CF-Access-Client-Id'] = client_id
        headers['CF-Access-Client-Secret'] = client_secret

    return headers
```

2. **Updated heartbeat API call** to include Cloudflare headers
3. **Updated registration API call** to include Cloudflare headers
4. **Updated heartbeat payload** to report tunnel-based URLs instead of VPN IPs:
   - `device_serial`: Raspberry Pi CPU serial number
   - `ssh_hostname`: `ssh_{serial}.alpium.io` (for future unique SSH access)
   - `web_server_url`: `https://web_ogn.alpium.io`
   - `ogn_web_ui_url`: `https://ogn_ogn.alpium.io`

### 2.3 Install Cloudflare Tunnel

```bash
# Download cloudflared
curl -L --output cloudflared.deb \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb

# Install
sudo dpkg -i cloudflared.deb

# Install tunnel with token
sudo cloudflared service install eyJhIjoiMDBiNmU2MzZjNDZhODgwNjUyOWZmNzljOWY4YThhYWQiLCJ0IjoiNDA1MTRiNjEtYTVjNy00NjM0LWI5YTgtODVmY2YxYTJkNDRjIiwicyI6Ik5URmlZVGRrWWpBdFpqbGpZUzAwTkdFeExUaGtPRE10T0dOaU05OHhaVFEzWVdGbSJ9

# Start and enable service
sudo systemctl start cloudflared
sudo systemctl enable cloudflared

# Verify tunnel is connected
sudo systemctl status cloudflared
```

### 2.4 Restart OGN Web Manager

```bash
cd ~/hfss-pi-flarm-rx
sudo pkill -f ogn-config-web-hfss.py
nohup sudo python3 ogn-config-web-hfss.py > /dev/null 2>&1 &
```

---

## Part 3: Alpium Server Setup

### 3.1 Install cloudflared on Alpium

```bash
# Download for AMD64 (Ubuntu server)
curl -L --output cloudflared.deb \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb

sudo dpkg -i cloudflared.deb
```

### 3.2 SSH to Raspberry Pi via Tunnel

From your Alpium server:

```bash
# Method 1: Direct SSH with ProxyCommand
ssh -o 'ProxyCommand=~/cloudflared access ssh --hostname ssh_ogn.alpium.io' hfss@ssh_ogn.alpium.io

# Method 2: Add to ~/.ssh/config for convenience
cat >> ~/.ssh/config << 'EOF'
Host ogn-pi
    HostName ssh_ogn.alpium.io
    User hfss
    ProxyCommand /usr/local/bin/cloudflared access ssh --hostname %h
EOF

# Then simply:
ssh ogn-pi
```

### 3.3 Access Web Interfaces

From your Alpium server or any browser:

```bash
# Configuration web interface (port 8082)
curl https://web_ogn.alpium.io

# OGN status page (port 8080)
curl https://ogn_ogn.alpium.io
```

Or open in browser:
- https://web_ogn.alpium.io
- https://ogn_ogn.alpium.io

---

## Part 4: Testing & Verification

### 4.1 Test Service Token Enforcement

```bash
# Should return 403 Forbidden (no token)
curl https://ogn.alpium.io/api/v1/gps/

# Should return 200 OK or proper API response (with token)
curl -H "CF-Access-Client-Id: 3e7da9e5eb83a5ffc00d6abb7aa6ab7a.access" \
     -H "CF-Access-Client-Secret: 64806145af6fd811d2f9db3e1b130761b87f4667a41bbcfc1532be31a6039157" \
     https://ogn.alpium.io/api/v1/gps/
```

### 4.2 Test Heartbeat Logs

On Raspberry Pi:

```bash
# Check recent heartbeats
tail -50 ~/hfss-pi-flarm-rx/heartbeat.log

# Look for 200 status codes indicating successful authentication
grep '"status": 200' ~/hfss-pi-flarm-rx/heartbeat.log | tail -5
```

### 4.3 Test SSH Access

From Alpium server:

```bash
# Test SSH connection
ssh -o 'ProxyCommand=~/cloudflared access ssh --hostname ssh_ogn.alpium.io' hfss@ssh_ogn.alpium.io 'hostname && echo "✓ SSH works!"'
```

### 4.4 Test Web Access

```bash
# Test configuration web server (port 8082)
curl -I https://web_ogn.alpium.io

# Test OGN status page (port 8080)
curl -I https://ogn_ogn.alpium.io
```

---

## Part 5: Mass Deployment Script

For deploying to thousands of Raspberry Pis, use this automated script:

```bash
#!/bin/bash
# deploy-ogn-cloudflare.sh - Deploy Cloudflare Zero Trust to OGN Raspberry Pi

set -e

TUNNEL_TOKEN="eyJhIjoiMDBiNmU2MzZjNDZhODgwNjUyOWZmNzljOWY4YThhYWQiLCJ0IjoiNDA1MTRiNjEtYTVjNy00NjM0LWI5YTgtODVmY2YxYTJkNDRjIiwicyI6Ik5URmlZVGRrWWpBdFpqbGpZUzAwTkdFeExUaGtPRE10T0dOaU05OHhaVFEzWVdGbSJ9"

echo "=== Cloudflare Zero Trust Deployment for OGN ==="

# 1. Update .env file
echo "1/5 Updating environment configuration..."
cd ~/hfss-pi-flarm-rx
cat > .env << 'EOF'
MANUFACTURER_SECRET_OGN=DpJGWXuPInyF7LXtiTlLt7tWgB_A0sUtNpL0km4Tyb4
HFSS_SERVER_URL=https://ogn.alpium.io/api/v1
CF_ACCESS_CLIENT_ID=3e7da9e5eb83a5ffc00d6abb7aa6ab7a.access
CF_ACCESS_CLIENT_SECRET=64806145af6fd811d2f9db3e1b130761b87f4667a41bbcfc1532be31a6039157
EOF
echo "   ✓ .env configured"

# 2. Install cloudflared
echo "2/5 Installing cloudflared..."
if ! command -v cloudflared &> /dev/null; then
    curl -L --output /tmp/cloudflared.deb \
      https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
    sudo dpkg -i /tmp/cloudflared.deb
    rm /tmp/cloudflared.deb
    echo "   ✓ cloudflared installed"
else
    echo "   ✓ cloudflared already installed"
fi

# 3. Configure tunnel
echo "3/5 Configuring Cloudflare Tunnel..."
if systemctl is-active --quiet cloudflared; then
    sudo cloudflared service uninstall
fi
sudo cloudflared service install "$TUNNEL_TOKEN"
sudo systemctl start cloudflared
sudo systemctl enable cloudflared
echo "   ✓ Tunnel configured and started"

# 4. Update Python script (if needed)
echo "4/5 Updating OGN web manager..."
# Copy updated ogn-config-web-hfss.py from deployment repo
# (Assumes you have the updated version in same directory)
if [ -f "./ogn-config-web-hfss.py" ]; then
    cp ogn-config-web-hfss.py ~/hfss-pi-flarm-rx/
    sudo pkill -f ogn-config-web-hfss.py || true
    sleep 2
    cd ~/hfss-pi-flarm-rx
    nohup sudo python3 ogn-config-web-hfss.py > /dev/null 2>&1 &
    echo "   ✓ OGN web manager restarted"
else
    echo "   ! Warning: ogn-config-web-hfss.py not found, skipping update"
fi

# 5. Verify setup
echo "5/5 Verifying deployment..."
sleep 5
if systemctl is-active --quiet cloudflared; then
    echo "   ✓ Cloudflare Tunnel: RUNNING"
else
    echo "   ✗ Cloudflare Tunnel: FAILED"
    exit 1
fi

if pgrep -f ogn-config-web-hfss.py > /dev/null; then
    echo "   ✓ OGN Web Manager: RUNNING"
else
    echo "   ✗ OGN Web Manager: NOT RUNNING"
fi

echo ""
echo "=== Deployment Complete! ==="
echo ""
echo "Device Serial: $(cat /proc/cpuinfo | grep Serial | awk '{print $3}' | tail -c 9)"
echo "SSH Hostname: ssh_ogn.alpium.io"
echo "Web Interface: https://web_ogn.alpium.io"
echo "OGN Status: https://ogn_ogn.alpium.io"
echo ""
echo "Test SSH from Alpium server:"
echo "  ssh -o 'ProxyCommand=~/cloudflared access ssh --hostname ssh_ogn.alpium.io' hfss@ssh_ogn.alpium.io"
```

**Usage**:
```bash
# On each Raspberry Pi
curl -O https://your-repo.com/deploy-ogn-cloudflare.sh
chmod +x deploy-ogn-cloudflare.sh
./deploy-ogn-cloudflare.sh
```

---

## Security Considerations

### Service Token Security
- **NEVER commit** `.env` file to git
- Store service token securely (password manager, secrets vault)
- Rotate tokens periodically via Cloudflare dashboard
- Each token can be revoked instantly if compromised

### Tunnel Token Security
- Single tunnel token works for all devices (scalable)
- Token only allows devices to connect to tunnel, not access it
- Revoke token via Cloudflare dashboard to disconnect all devices
- No inbound firewall rules needed on Raspberry Pis

### SSH Security
- SSH keys required (password auth disabled)
- Cloudflare Access provides audit logs of all SSH sessions
- Can add additional policies (require Okta/Google login, IP restrictions, etc.)

---

## Troubleshooting

### Heartbeat Fails with 403 Forbidden

**Cause**: Service token not being sent or invalid

**Check**:
```bash
# Verify .env file exists and has correct credentials
cat ~/hfss-pi-flarm-rx/.env

# Check heartbeat logs for actual headers being sent
tail -20 ~/hfss-pi-flarm-rx/heartbeat.log
```

**Fix**:
```bash
# Ensure .env has correct service token
# Restart web manager to reload .env
sudo pkill -f ogn-config-web-hfss.py
cd ~/hfss-pi-flarm-rx
nohup sudo python3 ogn-config-web-hfss.py > /dev/null 2>&1 &
```

### Cloudflare Tunnel Not Connecting

**Symptoms**:
```
ERR  error="Unable to reach the origin service. The service may be down or it may not be responding to traffic from cloudflared"
```

**Check**:
```bash
# Verify tunnel is running
sudo systemctl status cloudflared

# Check tunnel logs
sudo journalctl -u cloudflared -n 50
```

**Fix**:
```bash
# Reinstall tunnel with correct token
sudo cloudflared service uninstall
sudo cloudflared service install <TUNNEL_TOKEN>
sudo systemctl start cloudflared
```

### SSH Connection Refused

**Cause**: SSH service not running on Raspberry Pi

**Check**:
```bash
# Verify SSH is running
sudo systemctl status ssh

# Check if SSH port is listening
netstat -tuln | grep :22
```

**Fix**:
```bash
sudo systemctl start ssh
sudo systemctl enable ssh
```

### Web Interface Shows 502 Bad Gateway

**Cause**: Web server not running on Raspberry Pi

**Check**:
```bash
# Verify OGN web manager is running
ps aux | grep ogn-config-web-hfss.py

# Check if port 8082 is listening
netstat -tuln | grep :8082
```

**Fix**:
```bash
cd ~/hfss-pi-flarm-rx
sudo pkill -f ogn-config-web-hfss.py
nohup sudo python3 ogn-config-web-hfss.py > /dev/null 2>&1 &
```

---

## Monitoring & Maintenance

### Check Tunnel Health

From Cloudflare Dashboard:
1. Go to **Networks** → **Tunnels**
2. Find **ogn-devices** tunnel
3. Status should show **HEALTHY**
4. Click to see connected devices count

### Monitor Heartbeats

On Raspberry Pi:
```bash
# Watch live heartbeats
tail -f ~/hfss-pi-flarm-rx/heartbeat.log

# Count successful heartbeats today
grep "$(date +%Y-%m-%d)" ~/hfss-pi-flarm-rx/heartbeat.log | grep '"status": 200' | wc -l
```

### Access Logs

All access via Cloudflare is logged:
1. Go to **Logs** → **Access Requests**
2. Filter by application: `Ogn`
3. View all API requests with timestamps, IPs, and authentication status

---

## Scaling to Thousands of Devices

### Current Limitation: Shared Tunnel Hostname

All devices currently share:
- `ssh_ogn.alpium.io` → connects to random device
- `web_ogn.alpium.io` → connects to random device

### Solution for Unique Device Access

**Option A: Individual DNS Records** (up to ~500 devices)
- Create DNS record per device: `ssh_4d8db6ad.alpium.io`
- Manually or via Cloudflare API
- Each device reports its unique hostname in heartbeat

**Option B: Cloudflare for Teams with Device Posture** (1000+ devices)
- Upgrade to Cloudflare for Teams
- Use device posture checks and certificates
- Centralized device management dashboard

**Option C: SSH Bastion Pattern** (Recommended for 1000+ devices)
- Keep single shared tunnel
- Build management interface on Alpium server
- Server maintains database of device serials
- Admin selects device from UI → server SSHs via tunnel
- Scales to unlimited devices with zero DNS complexity

---

## Future Enhancements

1. **Unique SSH Access Per Device**
   - Automate DNS record creation via Cloudflare API
   - Script to create `ssh_{serial}.alpium.io` on device registration

2. **Device Dashboard**
   - React app showing all connected devices
   - Click device → open web interface or SSH
   - Real-time tunnel health monitoring

3. **Automated Deployment**
   - Ansible playbook for mass deployment
   - Zero-touch provisioning on SD card image
   - Automatic device registration on first boot

4. **Enhanced Security**
   - Require Okta/Google authentication for SSH
   - IP-based access restrictions
   - Automated SSH key rotation

---

## Support & Documentation

- **Cloudflare Zero Trust Docs**: https://developers.cloudflare.com/cloudflare-one/
- **Cloudflare Tunnel Guide**: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
- **OGN Project**: http://wiki.glidernet.org
- **This Repository**: Complete code and configuration examples

## Credentials Reference

**Service Token** (for API authentication):
```
Client ID: 3e7da9e5eb83a5ffc00d6abb7aa6ab7a.access
Client Secret: 64806145af6fd811d2f9db3e1b130761b87f4667a41bbcfc1532be31a6039157
```

**Tunnel Token** (for device connectivity):
```
eyJhIjoiMDBiNmU2MzZjNDZhODgwNjUyOWZmNzljOWY4YThhYWQiLCJ0IjoiNDA1MTRiNjEtYTVjNy00NjM0LWI5YTgtODVmY2YxYTJkNDRjIiwicyI6Ik5URmlZVGRrWWpBdFpqbGpZUzAwTkdFeExUaGtPRE10T0dOaU05OHhaVFEzWVdGbSJ9
```

**Tunnel UUID**:
```
40514b61-a5c7-4634-b9a8-85fcf1a2d44c
```

**Hostnames**:
- API: `ogn.alpium.io`
- SSH: `ssh_ogn.alpium.io`
- Web Config: `web_ogn.alpium.io`
- OGN Status: `ogn_ogn.alpium.io`

---

**Last Updated**: 2025-12-06
**Status**: Production Ready ✅
