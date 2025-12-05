# WireGuard VPN Setup for Alpium OGN Stations

This guide explains how to set up and auto-provision OGN stations with the Alpium WireGuard VPN server.

## Architecture

```
OGN Station (Raspberry Pi)
    ↓ WireGuard VPN (10.13.13.0/24)
Alpium Server (87.106.51.54)
    ↓ Docker Container (alpium-wireguard)
    ↓ VPN Gateway (10.13.13.1)
```

## Server Setup (One-Time)

### 1. Ensure WireGuard Container is Running

On the Alpium server (`alpium@alpium`):

```bash
cd ~/alpium
docker compose up -d wireguard
```

### 2. Fix Server Interface Configuration

The server's `wg0` interface must have the `/24` subnet mask:

```bash
cd ~/alpium/wireguard/config/wg_confs
# Backup
cp wg0.conf wg0.conf.backup

# Fix Address line
sed -i 's/^Address = 10.13.13.1$/Address = 10.13.13.1\/24/' wg0.conf

# Restart WireGuard
cd ~/alpium
docker compose restart wireguard
```

### 3. Configure Firewall

**CRITICAL**: The VPS firewall must allow UDP port 51820.

**Cloudflare Issue**: If using Cloudflare, note that:
- ✅ **DNS-only (gray cloud)**: Works for direct connections
- ❌ **Proxied (orange cloud)**: Blocks UDP traffic
- ❌ **Argo Tunnel**: Only supports HTTP/HTTPS

**Recommended DNS Setup**:
```
# Add A record (NOT CNAME, NOT proxied)
wg.alpium.io → 87.106.51.54 (DNS only, gray cloud)
```

### 4. Verify Server Status

```bash
# Check container
docker ps | grep wireguard

# Check interface
docker exec alpium-wireguard ip addr show wg0
# Should show: inet 10.13.13.1/24

# Check WireGuard status
docker exec alpium-wireguard wg show
```

## Client Setup (Per Station)

### Method 1: Auto-Provisioning (Recommended)

On the OGN Raspberry Pi:

```bash
# 1. First, register the station at http://<pi-ip>:8082
#    with Alpium server (https://app.alpium.io)

# 2. Set up SSH key authentication to Alpium server
ssh-copy-id alpium@alpium

# 3. Run auto-provisioning script
cd ~/hfss-pi-flarm-rx
git pull  # Get latest version
sudo ./ogn-autoprovision.sh
```

**What the script does**:
1. Reads device ID from `/home/hfss/.ogn_credentials.json`
2. Derives unique station ID and VPN IP
3. SSH to Alpium server and runs provisioning
4. Downloads WireGuard config
5. Installs and starts WireGuard service
6. Tests connectivity

### Method 2: Manual Provisioning

#### On Alpium Server:

```bash
cd ~/alpium
# Copy existing provisioning script
cp /path/to/wireguard-docker-provision-station.sh .

# Run for station ID 42
./wireguard-docker-provision-station.sh 42 ogn-flarm2

# This creates: ~/alpium/wireguard/peers/ogn-flarm2.conf
```

#### On OGN Station:

```bash
# Copy config from server
scp alpium@alpium:~/alpium/wireguard/peers/ogn-flarm2.conf /tmp/

# Install WireGuard
sudo apt update
sudo apt install -y wireguard resolvconf

# Install config
sudo cp /tmp/ogn-flarm2.conf /etc/wireguard/wg0.conf
sudo chmod 600 /etc/wireguard/wg0.conf

# Start WireGuard
sudo systemctl enable wg-quick@wg0
sudo systemctl start wg-quick@wg0

# Test
ping 10.13.13.1
sudo wg show
```

## Configuration Details

### Client Config Format

```ini
[Interface]
Address = 10.13.13.X/24        # Unique IP for each station
PrivateKey = <client-private>
DNS = 10.13.13.1

[Peer]
PublicKey = <server-public>
PresharedKey = <preshared>
Endpoint = 87.106.51.54:51820  # Direct IP (NOT vpn.alpium.io)
AllowedIPs = 10.13.13.0/24     # Only route VPN subnet
PersistentKeepalive = 25       # NAT traversal
```

### IP Address Allocation

- `10.13.13.1` - VPN server
- `10.13.13.2-11` - Reserved for peer1-peer10 (existing)
- `10.13.13.12-244` - Available for OGN stations
- Auto-provisioning script maps device ID hash to this range

### Key Configuration Points

1. **Endpoint must be direct IP**, not `vpn.alpium.io` (Cloudflare blocks UDP)
2. **AllowedIPs = 10.13.13.0/24** (not 0.0.0.0/0) - only route VPN traffic
3. **PersistentKeepalive = 25** - maintains connection through NAT
4. **Server needs /24 subnet** on interface (not /32)

## Troubleshooting

### VPN Not Connecting

```bash
# Client side
sudo systemctl status wg-quick@wg0
sudo wg show
sudo journalctl -u wg-quick@wg0 -n 50

# Check if sending data
sudo wg show  # Look for "transfer: X B sent"

# If sending but not receiving → server firewall issue
```

### Server Side Checks

```bash
# On Alpium server
ssh alpium@alpium

# Check container
docker ps | grep wireguard
docker logs alpium-wireguard --tail 50

# Check WireGuard status
docker exec alpium-wireguard wg show

# Look for peer endpoint and handshake
docker exec alpium-wireguard wg show | grep -A 5 "<client-public-key>"

# Should show:
#   endpoint: <client-ip>:51820
#   latest handshake: X seconds ago
#   transfer: X B received, Y B sent
```

### Common Issues

**1. Client sends but server doesn't receive**
- **Cause**: VPS firewall blocking UDP 51820
- **Fix**: Configure firewall to allow UDP 51820 inbound

**2. Server shows /32 instead of /24**
- **Cause**: Missing subnet mask in wg0.conf
- **Fix**: Edit `Address = 10.13.13.1/24` and restart

**3. "Destination Host Unreachable" from server**
- **Cause**: Routing issue, server can't reach 10.13.13.0/24
- **Fix**: Verify interface has /24 mask

**4. Cannot use vpn.alpium.io as endpoint**
- **Cause**: Cloudflare Tunnel only supports HTTP/HTTPS
- **Fix**: Use direct IP (87.106.51.54:51820) or create DNS-only A record

### Test UDP Connectivity

```bash
# From any machine to test port accessibility
nc -vuz 87.106.51.54 51820

# Expected: "Connection to 87.106.51.54 51820 port [udp/*] succeeded!"
```

## Firewall Configuration

### VPS Provider (Hetzner/DigitalOcean/etc.)

Check your VPS provider's firewall:

**Hetzner Cloud**:
```bash
# Via web console: Add firewall rule
Protocol: UDP
Port: 51820
Source: 0.0.0.0/0
```

**DigitalOcean**:
```bash
# Via web console: Networking → Firewalls
Inbound Rules: UDP 51820 from All sources
```

### UFW (If used on server)

```bash
sudo ufw allow 51820/udp
sudo ufw status
```

### iptables Check

```bash
# List rules
sudo iptables -L INPUT -n -v | grep 51820

# If needed, add rule
sudo iptables -A INPUT -p udp --dport 51820 -j ACCEPT
```

## Verification

### Successful Connection Signs

**Client**:
```bash
$ sudo wg show
interface: wg0
  public key: <key>
  private key: (hidden)
  listening port: 51820

peer: <server-key>
  endpoint: 87.106.51.54:51820
  allowed ips: 10.13.13.0/24
  latest handshake: 30 seconds ago          ← Important!
  transfer: 1.23 KiB received, 892 B sent   ← Both directions
  persistent keepalive: every 25 seconds
```

**Server**:
```bash
$ docker exec alpium-wireguard wg show | grep -A 5 <client-key>
peer: <client-public-key>
  preshared key: (hidden)
  endpoint: <client-public-ip>:51820        ← Important!
  allowed ips: 10.13.13.X/32
  latest handshake: 15 seconds ago          ← Important!
  transfer: 892 B received, 1.23 KiB sent   ← Both directions
```

**Ping Test**:
```bash
# From client
ping 10.13.13.1
# Should respond

# From server (via docker)
docker exec alpium-wireguard ping 10.13.13.X
# Should respond
```

## Security Notes

- Private keys are never transmitted
- Preshared keys add post-quantum resistance
- Each station has unique keys
- Configs stored in `~/alpium/wireguard/peers/` on server
- Server config backed up automatically before changes

## References

- [wireguard-docker-provision-station.sh](wireguard-docker-provision-station.sh) - Server-side provisioning
- [wireguard-client-setup.sh](wireguard-client-setup.sh) - Client installation
- [ogn-autoprovision.sh](ogn-autoprovision.sh) - Automated end-to-end provisioning
- WireGuard Docker Image: https://github.com/linuxserver/docker-wireguard
