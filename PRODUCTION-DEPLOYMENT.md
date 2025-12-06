# Production Deployment Guide - OGN IoT Network

Complete production-ready setup for thousands of OGN Raspberry Pi receivers using Cloudflare Zero Trust for API security and Tailscale for device access.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                  OGN Raspberry Pi Fleet                     │
│                  (Thousands of Devices)                     │
└────────┬────────────────────────────────────────────┬───────┘
         │                                            │
         │ HTTPS + Service Token                      │ Tailscale VPN
         │ (Heartbeats & Registration)                │ (Device Access)
         ▼                                            ▼
┌─────────────────────┐                    ┌─────────────────────┐
│  Cloudflare Access  │                    │  Tailscale Network  │
│  ogn.alpium.io      │                    │  VPN Mesh           │
│  - Service Token    │                    │  - Unique IPs       │
│  - Zero Trust       │                    │  - Direct Access    │
└──────────┬──────────┘                    └──────────┬──────────┘
           │                                          │
           ▼                                          ▼
    ┌─────────────────────────────────────────────────────┐
    │            Alpium Management Server                 │
    │  - React Dashboard (view all devices)              │
    │  - Access devices via Tailscale IPs                │
    │  - API receives heartbeats via Cloudflare          │
    └─────────────────────────────────────────────────────┘
```

## Why This Architecture?

### Cloudflare Zero Trust (API Security)
- **Purpose**: Secure API endpoints from unauthorized access
- **For OGN**: Optional (OGN data is public), but adds defense-in-depth
- **Benefits**:
  - Service token authentication (no user login required)
  - DDoS protection
  - Rate limiting
  - Audit logs

### Tailscale (Device Access)
- **Purpose**: Direct access to individual devices
- **Benefits**:
  - Each device gets unique IP (100.x.x.x)
  - No DNS records needed (scales to millions)
  - Encrypted peer-to-peer connections
  - Works through NAT/firewalls
  - React app can directly access device web interfaces

---

## Part 1: Cloudflare Zero Trust Setup

### 1.1 Create Service Token

1. Go to https://one.dash.cloudflare.com/
2. Navigate: **Access controls** → **Service credentials** → **Service Tokens**
3. Click **Create Service Token**
4. Name: `OGN Raspberry Pi Devices`
5. Save credentials:
   ```
   Client ID: 3e7da9e5eb83a5ffc00d6abb7aa6ab7a.access
   Client Secret: 64806145af6fd811d2f9db3e1b130761b87f4667a41bbcfc1532be31a6039157
   ```

### 1.2 Create Access Application

1. Navigate: **Access** → **Applications**
2. Add application → **Self-hosted**
3. Configure:
   - Name: `Ogn`
   - Domain: `ogn.alpium.io`
   - Session: `24 hours`
4. Add policy:
   - Name: `Service auth`
   - Action: `Service Auth`
   - Cloudflare will auto-allow your service token
5. Save

**Result**: API at `ogn.alpium.io` requires service token headers

### 1.3 Optional: SSH via Cloudflare Tunnel

Only needed if you want SSH access without Tailscale.

1. Navigate: **Networks** → **Tunnels**
2. Create tunnel: `ogn-devices`
3. Save tunnel token
4. Add public hostname:
   - Subdomain: `ssh_ogn`
   - Service: `SSH` → `localhost:22`

**Result**: SSH access via `ssh_ogn.alpium.io`

---

## Part 2: Tailscale VPN Setup

### 2.1 Create Tailscale Account

1. Go to https://login.tailscale.com/start
2. Sign up (Google/GitHub/Microsoft/Email)

### 2.2 Generate Auth Key

1. Go to https://login.tailscale.com/admin/settings/keys
2. Click **Generate auth key**
3. Configure:
   - Description: `OGN Raspberry Pi Fleet`
   - **Reusable**: ✅ ON (same key for all devices)
   - **Preauthorized**: ✅ ON (auto-approve devices)
   - Expiration: `90 days`
4. Save key:
   ```
   tskey-auth-kXXXXXXXXXX-XXXXXXXXXXXXXXXXXXXXXXXXXX
   ```

**Note**: Key expires in 90 days, but devices stay connected forever. Only need new key for devices added after expiration.

### 2.3 Optional: Create ACL Tag (Recommended)

For devices that never expire:

1. Go to https://login.tailscale.com/admin/acls
2. Add to policy:
```json
{
  "tagOwners": {
    "tag:ogn": ["autogroup:admin"]
  },
  "acls": [
    {
      "action": "accept",
      "src": ["tag:ogn"],
      "dst": ["*:*"]
    }
  ]
}
```
3. When generating auth key, add tag: `tag:ogn`

---

## Part 3: Raspberry Pi Configuration

### 3.1 Environment Setup

Create `.env` file on each Pi:

```bash
cd ~/hfss-pi-flarm-rx

cat > .env << 'EOF'
MANUFACTURER_SECRET_OGN=DpJGWXuPInyF7LXtiTlLt7tWgB_A0sUtNpL0km4Tyb4
HFSS_SERVER_URL=https://ogn.alpium.io/api/v1
CF_ACCESS_CLIENT_ID=3e7da9e5eb83a5ffc00d6abb7aa6ab7a.access
CF_ACCESS_CLIENT_SECRET=64806145af6fd811d2f9db3e1b130761b87f4667a41bbcfc1532be31a6039157
TS_AUTHKEY=tskey-auth-kXXXXXXXXXX-XXXXXXXXXXXXXXXXXXXXXXXXXX
EOF
```

### 3.2 Install Tailscale

```bash
# Download and install
curl -fsSL https://tailscale.com/install.sh | sh

# Get auth key from .env
TAILSCALE_KEY=$(grep TS_AUTHKEY .env | cut -d'=' -f2)

# Get device serial for hostname
SERIAL=$(cat /proc/cpuinfo | grep Serial | awk '{print $3}' | tail -c 9)

# Connect to Tailscale network
sudo tailscale up --authkey=$TAILSCALE_KEY --hostname=ogn-$SERIAL

# Verify connection
tailscale ip -4
# Output: 100.116.67.11 (example)
```

### 3.3 Install Cloudflare Tunnel (Optional)

Only if using Cloudflare for SSH:

```bash
# Download cloudflared
curl -L --output cloudflared.deb \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb

sudo dpkg -i cloudflared.deb

# Install tunnel
sudo cloudflared service install <TUNNEL_TOKEN>

# Start service
sudo systemctl start cloudflared
sudo systemctl enable cloudflared
```

### 3.4 Deploy OGN Software

The Python script automatically:
- Reads Cloudflare service token from `.env`
- Sends heartbeats with service token headers
- Reports Tailscale IP in `vpn_ip` field
- Reports web URLs using Tailscale IP

```bash
cd ~/hfss-pi-flarm-rx

# Pull latest code
git pull

# Restart service
sudo pkill -f ogn-config-web-hfss.py
nohup sudo python3 ogn-config-web-hfss.py > /dev/null 2>&1 &
```

---

## Part 4: Alpium Server Setup

### 4.1 Install Tailscale (Docker)

**docker-compose.yml:**
```yaml
version: '3.8'

services:
  tailscale:
    image: tailscale/tailscale:latest
    container_name: tailscale
    hostname: alpium
    privileged: true
    network_mode: host
    cap_add:
      - NET_ADMIN
      - SYS_MODULE
    volumes:
      - /dev/net/tun:/dev/net/tun
      - ./tailscale-state:/var/lib/tailscale
      - /lib/modules:/lib/modules
    environment:
      - TS_AUTHKEY=${TS_AUTHKEY}
      - TS_STATE_DIR=/var/lib/tailscale
    restart: unless-stopped
```

**Deploy:**
```bash
# Create .env with Tailscale key
echo "TS_AUTHKEY=tskey-auth-kXXXXXXXXXX-XXXXXXXXXXXXXXXXXXXXXXXXXX" > .env

# Start Tailscale
docker-compose up -d tailscale

# Connect (one-time)
docker exec tailscale tailscale up

# Get IP
docker exec tailscale tailscale ip -4
# Output: 100.91.157.96 (example)
```

### 4.2 Access Devices

From Alpium server (or any machine in Tailscale network):

```bash
# Access device web interface via Tailscale IP
curl http://100.116.67.11:8082

# Or open in browser
open http://100.116.67.11:8082
```

---

## Part 5: React Dashboard Integration

### Heartbeat Payload

Each device reports:

```json
{
  "device_id": "OGN_STATION_2085d06f",
  "device_metadata": {
    "device_serial": "2085d06f",
    "vpn_ip": "100.116.67.11",
    "web_server_url": "http://100.116.67.11:8082",
    "ogn_web_ui_url": "http://100.116.67.11:8080",
    "ssh_hostname": "ssh_2085d06f.alpium.io",
    "cpu_temp": 55.3,
    "uptime": 235786,
    ...
  }
}
```

### React Component Example

```jsx
function DeviceList({ devices }) {
  return (
    <table>
      <thead>
        <tr>
          <th>Device ID</th>
          <th>Tailscale IP</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        {devices.map(device => (
          <tr key={device.device_id}>
            <td>{device.device_id}</td>
            <td>{device.device_metadata.vpn_ip}</td>
            <td>
              <a
                href={device.device_metadata.web_server_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                Open Web Interface
              </a>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

**Result**: Click "Open Web Interface" → Opens `http://100.116.67.11:8082` in new tab

---

## Part 6: Deployment Script for Mass Rollout

**deploy-ogn-production.sh:**

```bash
#!/bin/bash
# Production deployment script for OGN Raspberry Pi with Cloudflare + Tailscale

set -e

echo "=== OGN Production Deployment ==="

# Configuration (set these before running)
CF_CLIENT_ID="3e7da9e5eb83a5ffc00d6abb7aa6ab7a.access"
CF_CLIENT_SECRET="64806145af6fd811d2f9db3e1b130761b87f4667a41bbcfc1532be31a6039157"
MANUFACTURER_SECRET="DpJGWXuPInyF7LXtiTlLt7tWgB_A0sUtNpL0km4Tyb4"
SERVER_URL="https://ogn.alpium.io/api/v1"
TAILSCALE_KEY="tskey-auth-kXXXXXXXXXX-XXXXXXXXXXXXXXXXXXXXXXXXXX"

# 1. Update .env file
echo "1/5 Configuring environment..."
cd ~/hfss-pi-flarm-rx
cat > .env << EOF
MANUFACTURER_SECRET_OGN=$MANUFACTURER_SECRET
HFSS_SERVER_URL=$SERVER_URL
CF_ACCESS_CLIENT_ID=$CF_CLIENT_ID
CF_ACCESS_CLIENT_SECRET=$CF_CLIENT_SECRET
TS_AUTHKEY=$TAILSCALE_KEY
EOF
echo "   ✓ Environment configured"

# 2. Install Tailscale
echo "2/5 Installing Tailscale..."
if ! command -v tailscale &> /dev/null; then
    curl -fsSL https://tailscale.com/install.sh | sh
    echo "   ✓ Tailscale installed"
else
    echo "   ✓ Tailscale already installed"
fi

# 3. Connect to Tailscale
echo "3/5 Connecting to Tailscale network..."
SERIAL=$(cat /proc/cpuinfo | grep Serial | awk '{print $3}' | tail -c 9)
sudo tailscale up --authkey=$TAILSCALE_KEY --hostname=ogn-$SERIAL
TAILSCALE_IP=$(tailscale ip -4)
echo "   ✓ Connected with IP: $TAILSCALE_IP"

# 4. Update OGN software
echo "4/5 Updating OGN software..."
git pull
sudo pkill -f ogn-config-web-hfss.py || true
sleep 2
nohup sudo python3 ogn-config-web-hfss.py > /dev/null 2>&1 &
echo "   ✓ OGN software updated and running"

# 5. Verify deployment
echo "5/5 Verifying deployment..."
sleep 5

# Check Tailscale
if tailscale status | grep -q "logged in"; then
    echo "   ✓ Tailscale: CONNECTED"
else
    echo "   ✗ Tailscale: FAILED"
fi

# Check OGN service
if pgrep -f ogn-config-web-hfss.py > /dev/null; then
    echo "   ✓ OGN Service: RUNNING"
else
    echo "   ✗ OGN Service: NOT RUNNING"
fi

echo ""
echo "=== Deployment Complete! ==="
echo ""
echo "Device Serial: $SERIAL"
echo "Tailscale IP: $TAILSCALE_IP"
echo "Web Interface: http://$TAILSCALE_IP:8082"
echo "OGN Status: http://$TAILSCALE_IP:8080"
echo ""
echo "Device will appear in Tailscale dashboard:"
echo "https://login.tailscale.com/admin/machines"
echo ""
echo "Heartbeats will be sent to: $SERVER_URL/gps/"
```

**Usage:**
```bash
# On each Raspberry Pi
curl -O https://your-repo.com/deploy-ogn-production.sh
chmod +x deploy-ogn-production.sh
./deploy-ogn-production.sh
```

---

## Scaling Considerations

### Free Tier Limits

**Tailscale:**
- Free: Up to 100 devices
- Personal Pro: $48/year (unlimited devices, 1 user)
- Team: $5/device/month

**Cloudflare Zero Trust:**
- Free: 50 users (service tokens don't count as users)
- Service tokens: Unlimited on free tier
- Tunnel: Unlimited traffic

### For 1000+ Devices

**Recommended plan:**
- Tailscale Personal Pro: $48/year
- Cloudflare Free tier: $0/year
- **Total cost: $48/year** for unlimited OGN devices

### For Millions of Devices

At scale, consider:
1. **Tailscale Enterprise**: Custom pricing, advanced management
2. **Self-hosted Headscale**: Open-source Tailscale coordination server (free)
3. **Cloudflare for Teams**: Advanced Zero Trust features

---

## Security Best Practices

### Secrets Management

**DO:**
- ✅ Store tokens in `.env` file (add to `.gitignore`)
- ✅ Use different tokens for dev vs production
- ✅ Rotate tokens every 90 days
- ✅ Revoke compromised tokens immediately

**DON'T:**
- ❌ Commit tokens to git
- ❌ Share tokens publicly
- ❌ Use same token for personal and IoT devices

### Network Security

**Cloudflare Access:**
- Blocks all requests without service token
- Provides audit logs
- Rate limiting protection

**Tailscale:**
- End-to-end encrypted (WireGuard protocol)
- Zero Trust by default
- Can add ACLs to restrict device-to-device access

### Monitoring

**Check device status:**
```bash
# View all devices in Tailscale network
https://login.tailscale.com/admin/machines

# View API access logs
https://one.dash.cloudflare.com/ → Logs → Access requests
```

---

## Troubleshooting

### Device Not Showing in Tailscale

**Check:**
```bash
# Verify Tailscale is running
sudo systemctl status tailscaled

# Check connection status
tailscale status

# View logs
sudo journalctl -u tailscaled -n 50
```

**Fix:**
```bash
# Restart Tailscale
sudo systemctl restart tailscaled
sudo tailscale up --authkey=$TS_AUTHKEY
```

### Heartbeat Fails with 403

**Cause**: Cloudflare service token not being sent or invalid

**Check:**
```bash
# Verify .env file has correct credentials
cat ~/hfss-pi-flarm-rx/.env

# Check heartbeat logs
tail -20 ~/hfss-pi-flarm-rx/heartbeat.log
```

**Fix:**
```bash
# Update .env with correct credentials
# Restart OGN service
sudo pkill -f ogn-config-web-hfss.py
cd ~/hfss-pi-flarm-rx
nohup sudo python3 ogn-config-web-hfss.py > /dev/null 2>&1 &
```

### Cannot Access Device Web Interface

**Check:**
```bash
# Verify Tailscale IP
tailscale ip -4

# Check if web server is running
ps aux | grep ogn-config-web-hfss.py

# Test locally on Pi
curl http://localhost:8082
```

**From Alpium server:**
```bash
# Verify Tailscale is running
docker exec tailscale tailscale status

# Try pinging device
docker exec tailscale ping 100.116.67.11

# Try accessing web interface
curl http://100.116.67.11:8082
```

---

## Architecture Decisions

### Why Cloudflare AND Tailscale?

**Different purposes:**

| Feature | Cloudflare | Tailscale |
|---------|-----------|-----------|
| **Purpose** | Secure public API | Private device access |
| **Use case** | Heartbeats, registration | Web interface, SSH |
| **Access** | Internet (public) | VPN (private) |
| **Authentication** | Service tokens | Network membership |
| **Scalability** | Unlimited | 100+ devices (paid) |

**Why not just one?**

- **Cloudflare only**: Can't access individual devices (shared tunnel)
- **Tailscale only**: API exposed to all Tailscale users (less secure)
- **Both**: API secured by Cloudflare, devices accessed via Tailscale ✅

### Is Cloudflare Access Necessary for OGN?

**Strictly speaking: NO**
- OGN data is public (aviation tracking)
- API could be open to the internet

**But it provides:**
- ✅ DDoS protection (free)
- ✅ Rate limiting
- ✅ Audit logs
- ✅ Defense in depth

**Decision**: Keep it. Adds security with zero cost.

---

## Summary

**Production setup uses TWO systems:**

1. **Cloudflare Zero Trust**
   - Secures API endpoints
   - Service token authentication
   - Free tier (sufficient for OGN)

2. **Tailscale VPN**
   - Direct device access
   - Unique IP per device (100.x.x.x)
   - Scales to thousands of devices

**Result:**
- ✅ Secure API (Cloudflare protected)
- ✅ Direct device access (Tailscale IPs)
- ✅ No DNS record explosion
- ✅ Simple React integration
- ✅ Scales to millions

**Total cost for 1000+ devices: $48/year** (Tailscale Personal Pro)

---

**Last Updated**: 2025-12-06
**Status**: Production Ready ✅
