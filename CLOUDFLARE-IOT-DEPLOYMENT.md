# Cloudflare Zero Trust Deployment for OGN IoT Devices

Complete guide for deploying thousands of OGN Raspberry Pi receivers with Cloudflare Zero Trust for secure API access and remote SSH management.

## Overview

This setup provides two security layers for your OGN IoT devices:

1. **Secure API Access** - Raspberry Pis authenticate to `ogn.alpium.io` API using service tokens
2. **Remote SSH Access** - SSH into any Raspberry Pi from anywhere via Cloudflare Tunnel

**Key Benefits:**
- ✅ Single configuration replicates to thousands of devices
- ✅ No inbound firewall rules needed
- ✅ No VPN required
- ✅ Access devices behind NAT/CGNAT
- ✅ Zero Trust security model

---

## Prerequisites

### On Cloudflare Dashboard
- Cloudflare account with Zero Trust enabled
- Domain managed by Cloudflare (e.g., `alpium.io`)
- Zero Trust organization name (e.g., `hfss`)

### On Each Raspberry Pi
- Debian-based OS (tested on Debian 13 Trixie, arm64)
- Internet connectivity
- SSH access for initial setup

---

## Part 1: Cloudflare Dashboard Setup (One-Time)

### Step 1.1: Create Service Token for API Authentication

This token allows Raspberry Pis to authenticate to your API without browser login.

1. Go to **https://one.dash.cloudflare.com/**
2. Navigate to: **Access controls** → **Service credentials** → **Service Tokens**
3. Click **Create Service Token**
4. **Name**: `OGN Raspberry Pi Devices`
5. **Copy and save**:
   - **Client ID**: `3e7da9e5eb83a5ffc00d6abb7aa6ab7a.access`
   - **Client Secret**: `64806145af6fd811d2f9db3e1b130761b87f4667a41bbcfc1532be31a6039157`

   ⚠️ **IMPORTANT**: Client Secret is only shown once! Save it securely.

### Step 1.2: Create Access Application for OGN API

Protect your API endpoint with the service token.

1. Navigate to: **Access** → **Applications**
2. Click **Add an application** → **Self-hosted**
3. Configure:
   - **Application name**: `Ogn`
   - **Session duration**: `24 hours`
   - **Application domain**:
     - **Subdomain**: (leave empty or `ogn`)
     - **Domain**: `alpium.io`
     - **Path**: (leave empty)
4. Click **Next**
5. **Add a policy**:
   - **Policy name**: `Service auth`
   - **Action**: `Service Auth`
   - **Configure rules**: (Cloudflare will automatically allow your service token)
6. Click **Next** → **Add application**

### Step 1.3: Create Cloudflare Tunnel for SSH Access

This tunnel allows SSH connections to all your Raspberry Pis.

1. Navigate to: **Networks** → **Tunnels**
2. Click **Create a tunnel**
3. **Select tunnel type**: Click **Cloudflared** (recommended)
4. **Name your tunnel**: `ogn-devices`
5. Click **Save tunnel**
6. **Copy the tunnel token** - it looks like:
   ```
   eyJhIjoiMDBiNmU2MzZjNDZhODgwNjUyOWZmNzljOWY4YThhYWQiLCJ0IjoiNDA1MTRiNjEtYTVjNy00NjM0LWI5YTgtODVmY2YxYTJkNDRjIiwicyI6Ik5URmlZVGRrWWpBdFpqbGpZUzAwTkdFeExUaGtPRE10T0dOaU9UZ3haVFEzWVdGbSJ9
   ```

   ⚠️ **Save this token** - you'll use it on every Raspberry Pi!

7. **Configure the tunnel route**:
   - Click **Public Hostname** tab
   - Click **Add a public hostname**
   - **Subdomain**: `ssh_ogn` (or any name)
   - **Domain**: Select `alpium.io`
   - **Path**: (leave empty)
   - **Service**:
     - **Type**: `SSH`
     - **URL**: `localhost:22`
   - Click **Save**

8. The tunnel will show as **HEALTHY** once devices connect

---

## Part 2: Raspberry Pi Configuration

### Step 2.1: Update `.env` File for API Access

On each Raspberry Pi, configure the API endpoint and service token credentials.

```bash
cd ~/hfss-pi-flarm-rx

# Backup existing .env
cp .env .env.backup

# Create/update .env file
cat > .env << 'EOF'
MANUFACTURER_SECRET_OGN=DpJGWXuPInyF7LXtiTlLt7tWgB_A0sUtNpL0km4Tyb4
HFSS_SERVER_URL=https://ogn.alpium.io/api/v1
CF_ACCESS_CLIENT_ID=3e7da9e5eb83a5ffc00d6abb7aa6ab7a.access
CF_ACCESS_CLIENT_SECRET=64806145af6fd811d2f9db3e1b130761b87f4667a41bbcfc1532be31a6039157
EOF

echo "✓ .env configured"
```

**Important Notes:**
- Replace the `CF_ACCESS_CLIENT_ID` and `CF_ACCESS_CLIENT_SECRET` with your actual service token from Step 1.1
- The `MANUFACTURER_SECRET_OGN` should already exist in your `.env`
- `HFSS_SERVER_URL` points to the secured `ogn.alpium.io` endpoint

### Step 2.2: Update Python Script to Send Service Token Headers

The OGN web manager needs to send Cloudflare Access headers with every API request.

**Add this function** to `ogn-config-web-hfss.py` after the `load_env_var()` function (around line 42):

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

**Update API requests** to include the headers:

1. **Heartbeat POST request** (around line 541):
   ```python
   response = requests.post(
       f"{creds['server_url']}/api/v1/gps/",
       headers={
           "Authorization": f"Bearer {creds['api_key']}",
           **get_cloudflare_headers()
       },
       json=payload,
       timeout=10
   )
   ```

2. **Registration POST request** (around line 708):
   ```python
   response = requests.post(
       f"{d['server_url']}/api/v1/devices/register",
       headers=get_cloudflare_headers(),
       json=payload,
       timeout=30
   )
   ```

### Step 2.3: Restart OGN Web Manager

```bash
sudo systemctl restart ogn-web-manager
```

### Step 2.4: Verify API Authentication

Test that the Raspberry Pi can authenticate to the API:

```bash
curl -H "CF-Access-Client-Id: 3e7da9e5eb83a5ffc00d6abb7aa6ab7a.access" \
     -H "CF-Access-Client-Secret: 64806145af6fd811d2f9db3e1b130761b87f4667a41bbcfc1532be31a6039157" \
     https://ogn.alpium.io/health/
```

Expected output:
```json
{"status":"healthy","timestamp":"..."}
```

If you get `HTTP 403 Forbidden` without headers, authentication is working correctly!

### Step 2.5: Install Cloudflare Tunnel for SSH Access

Install `cloudflared` and configure the tunnel:

```bash
# Download cloudflared for arm64
curl -L --output cloudflared.deb \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb

# Install
sudo dpkg -i cloudflared.deb
rm cloudflared.deb

# Verify installation
cloudflared --version
```

### Step 2.6: Configure and Start the Tunnel

Replace `YOUR_TUNNEL_TOKEN` with the token from Step 1.3:

```bash
# Install tunnel as a service
sudo cloudflared service install eyJhIjoiMDBiNmU2MzZjNDZhODgwNjUyOWZmNzljOWY4YThhYWQiLCJ0IjoiNDA1MTRiNjEtYTVjNy00NjM0LWI5YTgtODVmY2YxYTJkNDRjIiwicyI6Ik5URmlZVGRrWWpBdFpqbGpZUzAwTkdFeExUaGtPRE10T0dOaU9UZ3haVFEzWVdGbSJ9

# Start the tunnel
sudo systemctl start cloudflared
sudo systemctl enable cloudflared

# Check status
sudo systemctl status cloudflared
```

Expected output should show:
```
Active: active (running)
...
INF Registered tunnel connection ... location=ams19 protocol=quic
```

---

## Part 3: Remote SSH Access Setup

### Step 3.1: Install cloudflared on Management Server

On your management server (e.g., Alpium server), install `cloudflared`:

```bash
# Download for amd64 (adjust if different architecture)
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
  -o ~/cloudflared

chmod +x ~/cloudflared
~/cloudflared --version
```

### Step 3.2: Set Up SSH Keys

Generate SSH key on management server if not already present:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ''
```

Copy the public key to each Raspberry Pi:

```bash
ssh-copy-id hfss@<raspberry-pi-ip>
```

Or manually add to `~/.ssh/authorized_keys` on the Pi.

### Step 3.3: SSH via Cloudflare Tunnel

From your management server, SSH to any Raspberry Pi:

```bash
ssh -o 'ProxyCommand=~/cloudflared access ssh --hostname ssh_ogn.alpium.io' \
    hfss@ssh_ogn.alpium.io
```

**Simplify with SSH config** (`~/.ssh/config`):

```
Host ogn-devices
    HostName ssh_ogn.alpium.io
    User hfss
    ProxyCommand /home/alpium/cloudflared access ssh --hostname ssh_ogn.alpium.io
    StrictHostKeyChecking no
```

Then simply:
```bash
ssh ogn-devices
```

---

## Scaling to Thousands of Devices

### Automated Deployment Script

Create `deploy-ogn-cloudflare.sh`:

```bash
#!/bin/bash
# OGN Raspberry Pi Cloudflare Deployment Script
# Run on each Raspberry Pi for automated setup

set -e

TUNNEL_TOKEN="eyJhIjoiMDBiNmU2MzZjNDZhODgwNjUyOWZmNzljOWY4YThhYWQiLCJ0IjoiNDA1MTRiNjEtYTVjNy00NjM0LWI5YTgtODVmY2YxYTJkNDRjIiwicyI6Ik5URmlZVGRrWWpBdFpqbGpZUzAwTkdFeExUaGtPRE10T0dOaS05OHhaVFEzWVdGbSJ9"
SERVICE_TOKEN_ID="3e7da9e5eb83a5ffc00d6abb7aa6ab7a.access"
SERVICE_TOKEN_SECRET="64806145af6fd811d2f9db3e1b130761b87f4667a41bbcfc1532be31a6039157"

echo "=== OGN Cloudflare Zero Trust Deployment ==="

# 1. Update .env
cd ~/hfss-pi-flarm-rx
cp .env .env.backup || true
cat > .env << EOF
MANUFACTURER_SECRET_OGN=DpJGWXuPInyF7LXtiTlLt7tWgB_A0sUtNpL0km4Tyb4
HFSS_SERVER_URL=https://ogn.alpium.io/api/v1
CF_ACCESS_CLIENT_ID=$SERVICE_TOKEN_ID
CF_ACCESS_CLIENT_SECRET=$SERVICE_TOKEN_SECRET
EOF
echo "✓ .env configured"

# 2. Install cloudflared
if ! command -v cloudflared &> /dev/null; then
    curl -sL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb \
      -o /tmp/cloudflared.deb
    sudo dpkg -i /tmp/cloudflared.deb
    rm /tmp/cloudflared.deb
    echo "✓ cloudflared installed"
else
    echo "✓ cloudflared already installed"
fi

# 3. Configure tunnel
sudo cloudflared service install $TUNNEL_TOKEN
sudo systemctl start cloudflared
sudo systemctl enable cloudflared
echo "✓ Tunnel configured and started"

# 4. Restart OGN web manager
sudo systemctl restart ogn-web-manager
echo "✓ OGN web manager restarted"

# 5. Verify
echo ""
echo "=== Verification ==="
sudo systemctl status cloudflared --no-pager | head -10
echo ""
echo "✓ Deployment complete!"
echo ""
echo "SSH access: ssh_ogn.alpium.io"
echo "API endpoint: https://ogn.alpium.io/api/v1"
```

### Mass Deployment

Deploy to multiple Raspberry Pis:

```bash
# From management server
for pi in pi1.local pi2.local pi3.local; do
  scp deploy-ogn-cloudflare.sh hfss@$pi:~/
  ssh hfss@$pi 'bash ~/deploy-ogn-cloudflare.sh'
done
```

Or use Ansible/Salt/your preferred automation tool.

---

## Verification and Monitoring

### Check API Authentication

On Raspberry Pi:
```bash
tail -f ~/.ogn_heartbeat_log.json
```

Look for `"response_status": 200` - indicates successful authentication.

### Check Tunnel Status

```bash
sudo systemctl status cloudflared
sudo journalctl -u cloudflared -n 50
```

Expected: `Registered tunnel connection` with `protocol=quic`

### Check Cloudflare Dashboard

1. **Networks** → **Tunnels** → `ogn-devices`
   - Should show **HEALTHY** status
   - Shows number of connected devices

2. **Logs** → **Access** → **Access requests**
   - View API authentication logs
   - Monitor failed authentication attempts

---

## Troubleshooting

### API Returns 403 Forbidden

**Problem**: Raspberry Pi cannot access the API

**Solutions**:
1. Verify service token is correct in `.env`
2. Check Python script is sending headers (see Step 2.2)
3. Verify Access application exists in dashboard
4. Check `ogn-web-manager` is running: `sudo systemctl status ogn-web-manager`

### Tunnel Not Connecting

**Problem**: `cloudflared` service fails or shows errors

**Solutions**:
```bash
# Check logs
sudo journalctl -u cloudflared -n 100

# Restart service
sudo systemctl restart cloudflared

# Verify tunnel token is correct
sudo systemctl status cloudflared | grep token

# Check network connectivity
ping 1.1.1.1
```

### SSH Connection Fails

**Problem**: Cannot SSH via Cloudflare Tunnel

**Checks**:
1. Tunnel is running on Raspberry Pi: `sudo systemctl status cloudflared`
2. DNS resolves: `nslookup ssh_ogn.alpium.io`
3. SSH keys are configured: `ssh-copy-id hfss@<local-pi-ip>`
4. Try with verbose: `ssh -vvv -o 'ProxyCommand=~/cloudflared ...'`

---

## Security Best Practices

### Service Token Rotation

Rotate service tokens every 90 days:

1. Create new service token in dashboard
2. Update `.env` on all Raspberry Pis
3. Restart `ogn-web-manager` on all devices
4. Delete old service token after migration

### SSH Key Management

- Use unique SSH keys per management server
- Regularly audit `~/.ssh/authorized_keys` on Raspberry Pis
- Remove keys for decommissioned servers

### Monitoring

- Enable Cloudflare Access logs
- Set up alerts for failed authentication attempts
- Monitor tunnel health in dashboard

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│         Raspberry Pi OGN Receivers (Thousands)               │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ ogn-config-web-hfss.py                                 │ │
│  │ • Sends heartbeats to ogn.alpium.io/api/v1             │ │
│  │ • Includes CF-Access-Client-Id/Secret headers          │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ cloudflared (Tunnel)                                   │ │
│  │ • Connects to Cloudflare network                       │ │
│  │ • Exposes SSH (port 22) via ssh_ogn.alpium.io         │ │
│  └────────────────────────────────────────────────────────┘ │
└───────────────────────────────┬─────────────────────────────┘
                                │
                    Outbound HTTPS (443)
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│              Cloudflare Zero Trust Network                   │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Cloudflare Access (ogn.alpium.io)                     │ │
│  │ • Validates service token headers                      │ │
│  │ • Blocks requests without valid token (403)            │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Cloudflare Tunnel (ssh_ogn.alpium.io)                 │ │
│  │ • Routes SSH connections to Raspberry Pis              │ │
│  │ • Load-balances across all connected devices           │ │
│  └────────────────────────────────────────────────────────┘ │
└───────────────────────────────┬─────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│                  Backend API Server                          │
│                  (alpium@alpium)                             │
│                                                               │
│  • Receives authenticated API requests                       │
│  • Processes OGN heartbeat data                              │
│  • No direct public exposure                                 │
│                                                               │
│  SSH Management:                                             │
│  • Uses cloudflared to connect via ssh_ogn.alpium.io        │
│  • Access all Raspberry Pis through single hostname          │
└─────────────────────────────────────────────────────────────┘
```

---

## Costs

Cloudflare Zero Trust Free Plan includes:
- ✅ Up to 50 users
- ✅ Unlimited service tokens
- ✅ Unlimited tunnels
- ✅ Unlimited devices in tunnels

**Perfect for IoT at scale with zero cost!**

---

## Summary

✅ **API Security**: Service token authentication protects `ogn.alpium.io`
✅ **Remote Access**: SSH to any Raspberry Pi via Cloudflare Tunnel
✅ **Scalable**: Same configuration for 1 or 10,000 devices
✅ **No VPN**: Works behind NAT/CGNAT without port forwarding
✅ **Zero Cost**: Free Cloudflare plan supports unlimited IoT devices

**Key Credentials to Secure:**
- Service Token ID and Secret
- Tunnel Token
- SSH Private Keys

Store these in a password manager or secrets vault!
