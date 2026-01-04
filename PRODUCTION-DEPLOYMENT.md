# Production Deployment Guide - OGN Receiver

Quick setup guide for deploying OGN Raspberry Pi receivers with Tailscale VPN.

## Quick Start (For Friends)

### Prerequisites
- Raspberry Pi 3/4/5 with 64-bit OS
- RTL-SDR dongle
- Internet connection (WiFi or Ethernet)
- Provisioning passphrase (email repo owner to request)

### Setup Steps

**1. Flash Raspberry Pi OS (64-bit) to SD card**

**2. Boot the Pi and connect to internet**

**3. Clone and deploy**
```bash
git clone https://github.com/simone/hfss-pi-flarm-rx.git
cd hfss-pi-flarm-rx
./deploy-ogn-production.sh
```

**4. Enter the passphrase when prompted**
```
Enter the provisioning passphrase (ask Alpium admin):
Passphrase: ********
```

The script automatically:
1. Fetches all credentials from Alpium API
2. Deploys SSH keys for remote access
3. Installs OGN receiver software (via [ogn-pi34](https://github.com/VirusPilot/ogn-pi34))
4. Installs and connects Tailscale VPN
5. Starts the OGN config web service
6. Verifies all services are running

**5. Configure the receiver via web UI**

Open `http://<tailscale-ip>:8082` to configure:
- Station callsign
- Location (latitude/longitude/altitude)
- RF settings (frequency, gain)

**6. Done!** Your device will appear in the Tailscale dashboard and on [live.glidernet.org](https://live.glidernet.org) after 10-15 minutes.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                  OGN Raspberry Pi Fleet                     │
└────────┬────────────────────────────────────────────┬───────┘
         │                                            │
         │ HTTPS + Service Token                      │ Tailscale VPN
         │ (Heartbeats & Registration)                │ (Device Access)
         ▼                                            ▼
┌─────────────────────┐                    ┌─────────────────────┐
│  Cloudflare Access  │                    │  Tailscale Network  │
│  ogn.alpium.io      │                    │  VPN Mesh           │
└──────────┬──────────┘                    └──────────┬──────────┘
           │                                          │
           ▼                                          ▼
    ┌─────────────────────────────────────────────────────┐
    │            Alpium Management Server                 │
    │  - React Dashboard (view all devices)              │
    │  - Access devices via Tailscale IPs                │
    └─────────────────────────────────────────────────────┘
```

---

## For Administrators

### Provisioning System

The deploy script fetches credentials from:
```
GET https://ogn.alpium.io/api/v1/provision/ogn
Header: X-Provision-Key: <passphrase>
```

This returns the `.env` file containing:
- `MANUFACTURER_SECRET_OGN` - Device registration secret
- `SERVER_URL` - Alpium API endpoint
- `CF_ACCESS_CLIENT_ID` - Cloudflare service token
- `CF_ACCESS_CLIENT_SECRET` - Cloudflare secret
- `TS_AUTHKEY` - Tailscale auth key (reusable, preauthorized)
- `SSH_PUBLIC_KEY_OGN` - SSH key for remote access

### Tailscale Auth Key

Generate at https://login.tailscale.com/admin/settings/keys:
- **Reusable**: ON (same key for all devices)
- **Preauthorized**: ON (auto-approve devices)
- **Expiration**: 90 days

Note: Key expires in 90 days, but connected devices stay connected forever.

### Cloudflare Access

The `/provision/ogn` endpoint must bypass Cloudflare Access:
1. Create separate application for `/api/v1/provision/ogn`
2. Set policy to Bypass for Everyone
3. The passphrase provides authentication

### Changing the Passphrase

To rotate the passphrase:
1. Update your FastAPI server with new passphrase
2. Share new passphrase with authorized users
3. Existing devices are unaffected (already have `.env`)

---

## Troubleshooting

### Device Not Connecting to Tailscale
```bash
sudo systemctl status tailscaled
tailscale status
sudo journalctl -u tailscaled -n 50
```

### Provisioning Fails with 401
- Check passphrase is correct
- Verify endpoint is accessible: `curl https://ogn.alpium.io/api/v1/provision/ogn`

### Heartbeat Fails with 403
- Cloudflare service token may be expired
- Re-run deploy script to fetch fresh credentials

### Cannot Access Device Web Interface
```bash
# On the Pi
tailscale ip -4          # Get Tailscale IP
curl http://localhost:8082   # Test locally
```

---

## Manual Operations

### Re-deploy credentials
```bash
cd ~/hfss-pi-flarm-rx
rm .env
./deploy-ogn-production.sh
```

### Check service status
```bash
sudo systemctl status ogn-rf
sudo systemctl status ogn-decode
tailscale status
```

### View logs
```bash
sudo journalctl -u ogn-rf -f
sudo journalctl -u ogn-decode -f
```

---

## Costs

| Service | Free Tier | Paid |
|---------|-----------|------|
| Tailscale | 100 devices | $48/year unlimited |
| Cloudflare Access | Unlimited service tokens | $0 |

**Total for 1000+ devices: $48/year**

---

**Last Updated**: 2026-01-04
