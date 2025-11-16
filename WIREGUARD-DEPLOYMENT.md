# WireGuard Deployment Guide for OGN Fleet

This guide explains how to deploy thousands of OGN ground stations connected via WireGuard VPN over cellular connections.

## Architecture

```
[Your WireGuard Server]                    [OGN Station Fleet]
Public IP: x.x.x.x               ←─────    Station 1 (10.0.0.2) via SIM
VPN Network: 10.0.0.0/16         ←─────    Station 2 (10.0.0.3) via SIM
                                 ←─────    Station N (10.0.x.x) via SIM
         ↑
         │
   [Your Laptop/Admin]
   Access any station via VPN
```

## Prerequisites

### Server Requirements
- Linux server with public static IP (VPS, cloud instance, or home server with port forwarding)
- WireGuard installed and configured
- Port 51820/UDP open in firewall
- Root/sudo access

### Client Requirements (Per OGN Station)
- Raspberry Pi with cellular modem or SIM card hat
- Internet connectivity via SIM card
- SSH access for initial setup

## Quick Start

### 1. Server Setup (One-time)

Ensure your WireGuard server is running:

```bash
# Check WireGuard status
sudo systemctl status wg-quick@wg0

# View current config
sudo cat /etc/wireguard/wg0.conf

# Get your public IP or domain
curl ifconfig.me
```

Your server config should have IP forwarding enabled:

```bash
# Check IP forwarding
sysctl net.ipv4.ip_forward  # Should be 1

# If not, enable it
echo "net.ipv4.ip_forward=1" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### 2. Provision Single Station

On your **WireGuard server**, run:

```bash
cd /path/to/hfss-pi-flarm-rx
chmod +x wireguard-provision-station.sh
sudo ./wireguard-provision-station.sh 1 ogn-zurich
```

This will:
- Generate unique keys for the station
- Assign IP: 10.0.0.2 (station ID 1)
- Create config file: `station-configs/ogn-zurich.conf`
- Add peer to server config
- Reload WireGuard server

### 3. Provision Multiple Stations (Bulk)

For deploying 100 stations at once:

```bash
chmod +x wireguard-bulk-provision.sh
sudo ./wireguard-bulk-provision.sh 1 100 ogn-europe
```

This creates configs for stations 1-100:
- `station-configs/ogn-europe-0001.conf` (10.0.0.2)
- `station-configs/ogn-europe-0002.conf` (10.0.0.3)
- ...
- `station-configs/ogn-europe-0100.conf` (10.0.0.101)

### 4. Deploy to Raspberry Pi

**Method A: Manual Installation**

1. Copy config and setup script to the Pi:
```bash
scp station-configs/ogn-europe-0001.conf pi@192.168.1.100:~/
scp wireguard-client-setup.sh pi@192.168.1.100:~/
```

2. SSH to Pi and install:
```bash
ssh pi@192.168.1.100
chmod +x wireguard-client-setup.sh
sudo ./wireguard-client-setup.sh ogn-europe-0001.conf
```

3. Test connection:
```bash
ping 10.0.0.1  # Ping WireGuard server
```

**Method B: SD Card Image (Recommended for bulk deployment)**

Create a master SD card image with WireGuard pre-installed:

1. Install base system on one Pi
2. Install WireGuard client setup script
3. Create systemd service to auto-detect and load config on first boot
4. Clone SD card image
5. Before deploying each Pi, mount SD card and copy unique `.conf` file

### 5. Access Stations Remotely

Once connected via WireGuard, you can access any station from anywhere:

```bash
# SSH to station
ssh hfss@10.0.0.2  # Station 1
ssh hfss@10.0.0.3  # Station 2

# Access OGN web interface
curl http://10.0.0.2:8080  # Station 1
firefox http://10.0.0.42:8080  # Station 42

# Check OGN logs
ssh hfss@10.0.0.2 'sudo journalctl -u ogn-rf -f'

# View live data
ssh hfss@10.0.0.2 'telnet localhost 50000'
```

## IP Address Allocation

The scripts allocate IPs as follows:

- **Server**: 10.0.0.1
- **Station 1**: 10.0.0.2
- **Station 2**: 10.0.0.3
- **Station 254**: 10.0.1.0
- **Station 255**: 10.0.1.1
- **Maximum**: 10.0.255.254 (65,534 stations)

Formula: Station ID `N` → IP `10.0.{N/254}.{(N%254)+2}`

## Management Commands

### Server Side

```bash
# View all connected peers
sudo wg show

# View specific peer
sudo wg show wg0 peers

# Count active connections
sudo wg show wg0 | grep peer | wc -l

# Reload config without disconnect
sudo wg syncconf wg0 <(wg-quick strip wg0)

# Full restart
sudo systemctl restart wg-quick@wg0
```

### Client Side (on Pi)

```bash
# Check WireGuard status
sudo systemctl status wg-quick@wg0

# View connection details
sudo wg show

# Restart connection
sudo systemctl restart wg-quick@wg0

# View logs
sudo journalctl -u wg-quick@wg0 -f
```

## Troubleshooting

### Station can't connect

1. **Check server firewall**:
```bash
# Server
sudo ufw allow 51820/udp
sudo iptables -L -n | grep 51820
```

2. **Check client routing**:
```bash
# Pi
ip route show
ping 10.0.0.1
```

3. **Verify peer added to server**:
```bash
# Server
sudo wg show wg0 | grep -A 2 "peer: <PUBLIC_KEY>"
```

4. **Check cellular connection**:
```bash
# Pi
ping -c 3 8.8.8.8
curl ifconfig.me
```

### High data usage on cellular

WireGuard is very efficient, but you can optimize:

```bash
# Increase keepalive interval (in client config)
PersistentKeepalive = 60  # Instead of 25

# Monitor data usage
vnstat -i wg0
```

### Station unreachable after connection

Check NAT/firewall rules on server:

```bash
# Server - ensure traffic forwarding is enabled
sudo iptables -A FORWARD -i wg0 -j ACCEPT
sudo iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
```

## Monitoring Dashboard

Create a simple monitoring script:

```bash
#!/bin/bash
# monitor-fleet.sh

echo "OGN Fleet Status - $(date)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

TOTAL=$(sudo wg show wg0 peers | wc -l)
ACTIVE=$(sudo wg show wg0 latest-handshakes | awk '{if ($2 > systime() - 180) print $1}' | wc -l)

echo "Total configured: $TOTAL"
echo "Active (last 3min): $ACTIVE"
echo ""

# List offline stations
echo "Offline stations:"
sudo wg show wg0 latest-handshakes | awk '{if ($2 < systime() - 180) print $1}' | while read peer; do
    grep -B 1 "$peer" /etc/wireguard/wg0.conf | grep "# OGN"
done
```

## Scaling Considerations

### Small Fleet (1-100 stations)
- Single VPS (2GB RAM, 1 CPU core) is sufficient
- Cost: $5-10/month

### Medium Fleet (100-1000 stations)
- VPS with 4GB RAM, 2 CPU cores
- Consider monitoring with Prometheus/Grafana
- Cost: $20-40/month

### Large Fleet (1000+ stations)
- Dedicated server or cloud instance (8GB+ RAM)
- Multiple WireGuard servers with DNS load balancing
- Centralized logging (ELK stack, Loki)
- Automated health checks
- Cost: $50-100/month

## Security Best Practices

1. **Key Management**: Store private keys securely, never commit to git
2. **Firewall**: Only expose port 51820/UDP on server
3. **Access Control**: Restrict SSH access to VPN network only
4. **Updates**: Keep WireGuard updated on all devices
5. **Monitoring**: Alert on unusual traffic patterns

## Integration with OGN Monitoring

You can create a dashboard that shows:
- All stations on live.glidernet.org map
- WireGuard connection status per station
- Data throughput per station
- Alert on disconnected stations

Example integration:
```bash
# Check if station is online on OGN network
curl "https://live.glidernet.org/api/stations" | grep HfssHq2
```

## Cost Estimate (1000 Stations)

| Item | Cost |
|------|------|
| WireGuard VPS (dedicated) | $40/month |
| SIM cards (1000 × $5/month) | $5,000/month |
| Raspberry Pi hardware (one-time) | ~$80,000 |
| **Total recurring** | **$5,040/month** |

Main cost is cellular data. Consider:
- Negotiate bulk SIM card rates
- Use IoT-specific data plans (cheaper for low bandwidth)
- Share SIM costs with local gliding clubs

## Next Steps

1. Test with 1-2 stations first
2. Verify remote access and OGN data flow
3. Create master SD card image for bulk deployment
4. Set up monitoring dashboard
5. Scale to full fleet

## Support

For issues specific to:
- **OGN system**: See [CLAUDE.md](CLAUDE.md)
- **WireGuard**: https://www.wireguard.com/
- **Raspberry Pi**: https://www.raspberrypi.org/forums/
