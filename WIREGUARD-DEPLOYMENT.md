# WireGuard VPN Deployment for OGN Stations

Deploy thousands of OGN ground stations with cellular connectivity via WireGuard VPN.

## Architecture

```
[WireGuard Server - Docker]          [OGN Station Fleet]
vilnius (89.47.162.7)      ←─────    Station 1 (10.13.13.12) via WiFi/SIM
VPN: 10.13.13.1                      Station 2 (10.13.13.13) via SIM
Port: 51820/UDP                      Station N (10.13.13.x) via SIM

         ↑
         │ VPN Tunnel
         │
   [Your Device]
   Connect to any station remotely
```

## Server: vilnius (89.47.162.7)

**WireGuard runs in Docker container**
- Network: `10.13.13.0/24`
- Server IP: `10.13.13.1`
- Endpoint: `89.47.162.7:51820`
- Location: `~/apps/wireguard_vpn/`

### Provision New Station

```bash
# SSH to vilnius
ssh ubuntu@vilnius
cd ~/apps/wireguard_vpn

# Provision station (e.g., station ID 2)
./wireguard-docker-provision-station.sh 2 ogn-milan

# Creates: peers/ogn-milan.conf with IP 10.13.13.13
# Restarts container automatically
```

**IP Assignment:** Station ID `N` → IP `10.13.13.{N+11}`
- Station 1 → 10.13.13.12
- Station 2 → 10.13.13.13
- Max 243 stations on current /24 network

### View Connected Stations

```bash
# SSH to vilnius
ssh ubuntu@vilnius

# List all peers
docker exec wireguard wg show

# Active connections (handshake < 3min)
docker exec wireguard wg show wg0 latest-handshakes | awk '{if ($2 > systime() - 180) print}'

# Container status
cd ~/apps/wireguard_vpn && docker-compose ps
```

## Client: Raspberry Pi Setup

### Install WireGuard (One-time per Pi)

1. **Copy config from vilnius:**
```bash
scp ubuntu@vilnius:~/apps/wireguard_vpn/peers/ogn-milan.conf pi@<pi-ip>:~/
```

2. **Install on Pi:**
```bash
ssh pi@<pi-ip>
chmod +x wireguard-client-setup.sh
sudo ./wireguard-client-setup.sh ogn-milan.conf
```

**VPN Auto-Start:** ✅ Enabled by default
- Service: `wg-quick@wg0`
- Starts on boot automatically
- Keeps persistent connection (keepalive every 25s)

### Verify Connection

```bash
# On Pi - check status
sudo systemctl status wg-quick@wg0
sudo wg show

# Test connectivity
ping 10.13.13.1  # Ping vilnius VPN server
```

## Access Stations Remotely

### Connect to Your VPN First

**Option 1: Install WireGuard on your laptop**
- Download peer config from `vilnius:~/apps/wireguard_vpn/peers/`
- Import to WireGuard client (Windows/Mac/Linux)

**Option 2: SSH tunnel via vilnius**
```bash
# SSH to station via vilnius
ssh -J ubuntu@vilnius hfss@10.13.13.12
```

### Access Station Services

Once on VPN network:

```bash
# SSH to any station
ssh hfss@10.13.13.12  # Station 1
ssh hfss@10.13.13.13  # Station 2

# Access OGN web UI
open http://10.13.13.12:8080  # Station 1

# Check OGN logs
ssh hfss@10.13.13.12 'sudo journalctl -u ogn-rf -f'

# View live APRS data
ssh hfss@10.13.13.12 'telnet localhost 50001'
```

## API Endpoint: Station Registry

**Coming soon:** REST API to list all stations with metadata

```bash
# Planned endpoint on vilnius
curl http://89.47.162.7:8000/api/stations

# Returns:
# [
#   {
#     "id": 1,
#     "name": "ogn-flarm-test",
#     "vpn_ip": "10.13.13.12",
#     "callsign": "HfssHq2",
#     "location": {"lat": 45.97316, "lon": 8.87516},
#     "online": true,
#     "last_seen": "2025-11-16T22:15:30Z"
#   }
# ]
```

This will allow your app to:
- Discover all stations dynamically
- Get VPN IP for each station
- Check online/offline status
- Display on map with clickable access

## Management Commands

### Server (vilnius)

```bash
# View all peers
docker exec wireguard wg show

# Restart WireGuard
cd ~/apps/wireguard_vpn && docker-compose restart

# View logs
docker logs wireguard -f

# Count stations
docker exec wireguard wg show wg0 peers | wc -l
```

### Client (Pi)

```bash
# VPN status
sudo systemctl status wg-quick@wg0

# Connection details
sudo wg show

# Restart VPN
sudo systemctl restart wg-quick@wg0

# Enable auto-start (already enabled by setup script)
sudo systemctl enable wg-quick@wg0

# Disable auto-start
sudo systemctl disable wg-quick@wg0
```

## Troubleshooting

### Pi can't connect to VPN

1. **Check internet connection:**
```bash
ping 8.8.8.8
curl ifconfig.me  # Should show public IP
```

2. **Check endpoint reachability:**
```bash
nc -vzu 89.47.162.7 51820  # Should succeed
```

3. **View WireGuard logs:**
```bash
sudo journalctl -u wg-quick@wg0 -f
```

4. **Verify config:**
```bash
sudo cat /etc/wireguard/wg0.conf
# Endpoint should be: 89.47.162.7:51820
```

### Server doesn't see peer

1. **Check if peer added to config:**
```bash
ssh ubuntu@vilnius
cat ~/apps/wireguard_vpn/config/wg_confs/wg0.conf | grep -A 3 "10.13.13.12"
```

2. **Restart container:**
```bash
cd ~/apps/wireguard_vpn && docker-compose restart
```

### VPN connected but can't ping server

**Firewall issue** - check container network:
```bash
docker exec wireguard iptables -L -n
```

## Files

- **wireguard-docker-provision-station.sh** - Provision new station on vilnius
- **wireguard-client-setup.sh** - Install WireGuard on Pi
- **WIREGUARD-DEPLOYMENT.md** - This documentation

## Security Notes

1. **Never commit private keys** to git
2. **Peer configs contain secrets** - stored in `vilnius:~/apps/wireguard_vpn/peers/`
3. **VPN gives full network access** - only share configs with trusted devices
4. **Firewall on vilnius** - only port 51820/UDP exposed publicly

## Next Steps

1. ✅ Test connection with station 1 (ogn-flarm-test @ 10.13.13.12)
2. Create station registry API endpoint
3. Build web dashboard for fleet management
4. Scale to multiple stations with SIM cards
5. Monitor data usage and optimize keepalive intervals

## Support

- **WireGuard docs:** https://www.wireguard.com/
- **OGN setup:** See [CLAUDE.md](CLAUDE.md)
