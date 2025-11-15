# OGN Station Setup Guide

**Version:** 1.0
**Last Updated:** 2025-11-15
**Author:** HFSS Development Team

This guide provides complete instructions for setting up OGN receiver stations that register with the HFSS tracking system and send periodic status heartbeats.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Server-Side Configuration](#server-side-configuration)
4. [Raspberry Pi Station Setup](#raspberry-pi-station-setup)
5. [Testing & Verification](#testing--verification)
6. [Administration & Monitoring](#administration--monitoring)
7. [Troubleshooting](#troubleshooting)
8. [Security Considerations](#security-considerations)

---

## Overview

### What is an OGN Station?

OGN (Open Glider Network) stations are Raspberry Pi-based receivers that listen to FLARM and other aircraft tracking signals. In the HFSS system, these stations:

- **Register themselves** as stationary devices (not mobile trackers)
- **Do NOT transmit GPS data** (they have fixed coordinates)
- **Send periodic heartbeats** with status information (CPU temp, uptime, etc.)
- **Can be filtered** separately from mobile devices in the admin panel

### Key Differences from Mobile Devices

| Feature | Mobile Devices (ESP32, GPS Trackers) | OGN Stations |
|---------|--------------------------------------|--------------|
| Data Type | GPS points (lat/lon updates) | Status heartbeats only |
| Location | Changes constantly | Fixed coordinates |
| Registration | Via MQTT or TCP protocols | Via HTTP REST API |
| Data Source | `cellular`, `mqtt` | `station` |
| Device Type | `TK905`, `GL320M`, `ESP32` | `OGN_STATION` |
| Category | `gps_tracker`, `mobile` | `station` |

---

## Architecture

### Registration Flow

```
┌─────────────────┐
│  Raspberry Pi   │
│  OGN Station    │
└────────┬────────┘
         │
         │ 1. HTTP POST /api/v1/devices/register
         │    {device_id, manufacturer, token}
         │
         ▼
┌─────────────────┐
│   API Server    │
│  (FastAPI)      │
└────────┬────────┘
         │
         │ 2. Validate HMAC token
         │    using MANUFACTURER_SECRET_OGN
         │
         ▼
┌─────────────────┐
│  Device Table   │
│  (PostgreSQL)   │
└────────┬────────┘
         │
         │ 3. Return credentials
         │    {api_key, mqtt_username, mqtt_password}
         │
         ▼
┌─────────────────┐
│  Raspberry Pi   │
│  Saves to disk  │
└─────────────────┘
```

### Heartbeat Flow

```
┌─────────────────┐
│  Raspberry Pi   │   Every 5 minutes
│  Cron/Systemd   │──────────────────┐
└─────────────────┘                  │
                                     │
         ┌───────────────────────────┘
         │
         │ HTTP POST /api/v1/gps
         │ Headers: X-API-Key
         │ Body: {device_metadata: {heartbeat, status}}
         │
         ▼
┌─────────────────┐
│   API Server    │
│  Validates Key  │
└────────┬────────┘
         │
         │ Updates last_seen timestamp
         │ Stores metadata in Redis cache
         │
         ▼
┌─────────────────┐
│  Device Table   │
│  last_seen      │
└─────────────────┘
```

---

## Server-Side Configuration

### Step 1: Generate Manufacturer Secret

On the production server, generate a secure secret for OGN devices:

```bash
# SSH to production server
ssh hfss@hfss-dev
cd ~/apps/hfss-digi

# Generate a strong 256-bit secret
openssl rand -hex 32
# Example output: a3f8d9e2c1b4567890abcdef1234567890abcdef1234567890abcdef12345678
```

### Step 2: Update `.env` File

Add the OGN manufacturer secret to your `.env` file:

```bash
# Edit .env file
nano .env

# Add this line (use your generated secret)
MANUFACTURER_SECRET_OGN=a3f8d9e2c1b4567890abcdef1234567890abcdef12345678
```

**IMPORTANT NOTES:**
- Keep this secret secure - it's used to validate station registrations
- Do NOT commit this secret to git
- Different from `MANUFACTURER_SECRET_DIGIFLY` (used for ESP32 devices)
- Each manufacturer should have a unique secret

### Step 3: Verify Code Changes

The following files have already been updated (verify they exist):

#### `/app/core/config.py`
```python
# Manufacturer secrets for device registration
MANUFACTURER_SECRET_DIGIFLY: Optional[str] = None
MANUFACTURER_SECRET_OGN: Optional[str] = None  # ✓ Added
```

#### `/app/core/device_security.py`
```python
def __init__(self):
    self.manufacturer_secrets = {
        "DIGIFLY": settings.MANUFACTURER_SECRET_DIGIFLY or "default_digifly_secret",
        "OGN": settings.MANUFACTURER_SECRET_OGN or "default_ogn_secret"  # ✓ Added
    }

    self.device_patterns = {
        "DIGIFLY": r"^.+$",
        "OGN": r"^OGN_STATION_.+$"  # ✓ Station IDs must start with OGN_STATION_
    }
```

### Step 4: Deploy Changes

```bash
# On production server
cd ~/apps/hfss-digi

# Pull latest changes (if code was committed)
git pull

# Restart API servers to load new .env
docker compose restart api1 api2

# Verify environment variable is loaded
docker compose exec api1 env | grep MANUFACTURER_SECRET_OGN
```

### Step 5: Create OGN Station Device Type (Optional but Recommended)

Create a dedicated device type for better filtering:

```bash
# Using curl (replace <admin_token> with your actual JWT token)
curl -X POST "http://localhost/api/v1/admin/device-types" \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "OGN_STATION",
    "display_name": "OGN Receiver Station",
    "description": "Stationary OGN receiver for FLARM and ADS-B signals",
    "manufacturer": "OGN",
    "category": "station",
    "capabilities": ["receiver", "heartbeat", "status_monitoring"],
    "default_settings": {
      "is_stationary": true,
      "transmits_gps": false,
      "heartbeat_interval": 300
    },
    "icon": "radio-tower",
    "is_active": true,
    "sort_order": 100
  }'
```

**Expected Response:**
```json
{
  "id": "uuid-here",
  "name": "OGN_STATION",
  "display_name": "OGN Receiver Station",
  "category": "station",
  "is_active": true
}
```

---

## Raspberry Pi Station Setup

### Prerequisites

- Raspberry Pi (any model, recommended: Pi 3B+ or newer)
- Raspbian/Raspberry Pi OS installed
- Internet connectivity
- Python 3.7+ installed (comes with Raspbian)
- OGN receiver hardware connected (optional for testing)

### Step 1: Install Required Packages

```bash
# Update system
sudo apt update
sudo apt upgrade -y

# Install Python dependencies
sudo apt install -y python3-pip python3-venv

# Install requests library
pip3 install requests
```

### Step 2: Create Station Script

Create the main station script:

```bash
# Create directory
mkdir -p ~/ogn-station
cd ~/ogn-station

# Create script
nano ogn_station.py
```

Paste the following complete script:

```python
#!/usr/bin/env python3
"""
OGN Station Registration & Heartbeat for HFSS
Runs on Raspberry Pi

This script:
1. Registers the station with HFSS server (first run)
2. Saves credentials securely
3. Sends periodic heartbeats with status information
"""
import requests
import hmac
import hashlib
import time
import json
import os
import sys
from datetime import datetime
import logging

# ============================================================================
# CONFIGURATION - MODIFY THESE VALUES FOR YOUR STATION
# ============================================================================

# Server configuration
SERVER_URL = "https://your-hfss-server.com"  # ⚠️ CHANGE THIS

# Station identification
STATION_ID = "OGN_STATION_RPI001"  # ⚠️ CHANGE THIS (must start with OGN_STATION_)
STATION_NAME = "OGN Station Pi 001"  # Friendly name

# Station location (fixed coordinates)
STATION_LAT = 45.123456  # ⚠️ CHANGE THIS to your station latitude
STATION_LON = 7.654321   # ⚠️ CHANGE THIS to your station longitude
STATION_ALTITUDE = 1200  # meters above sea level (optional)

# Security
MANUFACTURER = "OGN"
MANUFACTURER_SECRET = "PASTE_YOUR_SECRET_HERE"  # ⚠️ GET THIS FROM SERVER ADMIN

# Heartbeat configuration
HEARTBEAT_INTERVAL = 300  # seconds (5 minutes)
CREDENTIALS_FILE = "/home/pi/.ogn_credentials.json"

# Logging
LOG_FILE = "/var/log/ogn_station.log"
LOG_LEVEL = logging.INFO

# ============================================================================
# DO NOT MODIFY BELOW THIS LINE UNLESS YOU KNOW WHAT YOU'RE DOING
# ============================================================================

# Setup logging
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def generate_registration_token(device_id, manufacturer, manufacturer_secret):
    """
    Generate HMAC registration token.

    This proves to the server that this registration request is legitimate.
    The server will verify this token using the same secret.
    """
    message = f"{manufacturer}:{device_id}"
    token = hmac.new(
        manufacturer_secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    return token


def register_station():
    """
    Register OGN station with HFSS server.

    This is called on first run or if credentials are lost.
    Returns credentials that should be saved securely.
    """
    logger.info(f"Registering station {STATION_ID} with server {SERVER_URL}")

    # Validate configuration
    if MANUFACTURER_SECRET == "PASTE_YOUR_SECRET_HERE":
        logger.error("MANUFACTURER_SECRET not configured! Get it from server admin.")
        return None

    if not STATION_ID.startswith("OGN_STATION_"):
        logger.error(f"Invalid STATION_ID: {STATION_ID}. Must start with 'OGN_STATION_'")
        return None

    # Generate registration token
    token = generate_registration_token(STATION_ID, MANUFACTURER, MANUFACTURER_SECRET)

    # Prepare registration payload
    payload = {
        "device_id": STATION_ID,
        "manufacturer": MANUFACTURER,
        "registration_token": token,
        "name": STATION_NAME,
        "device_info": {
            "custom_data": {
                "latitude": STATION_LAT,
                "longitude": STATION_LON,
                "altitude": STATION_ALTITUDE,
                "is_station": True,
                "station_type": "OGN_RECEIVER",
                "raspberry_pi": True
            }
        }
    }

    try:
        response = requests.post(
            f"{SERVER_URL}/api/v1/devices/register",
            json=payload,
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            credentials = {
                "device_id": data["device_id"],
                "api_key": data["api_key"],
                "mqtt_username": data["mqtt_username"],
                "mqtt_password": data["mqtt_password"],
                "registered_at": datetime.utcnow().isoformat()
            }

            # Save credentials securely
            with open(CREDENTIALS_FILE, 'w') as f:
                json.dump(credentials, f, indent=2)
            os.chmod(CREDENTIALS_FILE, 0o600)  # Owner read/write only

            logger.info(f"✓ Station registered successfully!")
            logger.info(f"  Device ID: {credentials['device_id']}")
            logger.info(f"  Credentials saved to: {CREDENTIALS_FILE}")
            return credentials

        else:
            logger.error(f"✗ Registration failed with status {response.status_code}")
            logger.error(f"  Response: {response.text}")
            return None

    except requests.exceptions.ConnectionError:
        logger.error(f"✗ Cannot connect to server: {SERVER_URL}")
        logger.error("  Check network connection and SERVER_URL configuration")
        return None

    except Exception as e:
        logger.error(f"✗ Registration error: {e}", exc_info=True)
        return None


def load_credentials():
    """Load saved credentials from disk."""
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, 'r') as f:
                creds = json.load(f)
            logger.debug(f"Loaded credentials for device {creds.get('device_id')}")
            return creds
        except Exception as e:
            logger.error(f"Failed to load credentials: {e}")
            return None
    return None


def get_station_status():
    """
    Collect current station status information.

    Returns dict with:
    - cpu_temp: CPU temperature (Celsius)
    - uptime: System uptime (seconds)
    - connected_clients: Number of OGN clients (if applicable)
    - timestamp: Current timestamp
    """
    status = {
        "timestamp": datetime.utcnow().isoformat()
    }

    # CPU temperature (Raspberry Pi specific)
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            cpu_temp = float(f.read().strip()) / 1000.0
            status["cpu_temp"] = round(cpu_temp, 1)
    except Exception as e:
        logger.debug(f"Could not read CPU temp: {e}")
        status["cpu_temp"] = None

    # System uptime
    try:
        with open('/proc/uptime', 'r') as f:
            uptime_seconds = int(float(f.read().split()[0]))
            status["uptime"] = uptime_seconds
    except Exception as e:
        logger.debug(f"Could not read uptime: {e}")
        status["uptime"] = 0

    # OGN clients (example - adjust based on your OGN software)
    # TODO: Implement actual OGN client counting
    # This could check ogn-rf logs, rtlsdr-ogn status, or other metrics
    status["connected_clients"] = 0

    # Disk usage
    try:
        import shutil
        disk = shutil.disk_usage('/')
        status["disk_usage_percent"] = round(disk.used / disk.total * 100, 1)
    except:
        status["disk_usage_percent"] = None

    # Memory usage
    try:
        with open('/proc/meminfo', 'r') as f:
            meminfo = f.read()
            total = int([x for x in meminfo.split('\n') if 'MemTotal' in x][0].split()[1])
            available = int([x for x in meminfo.split('\n') if 'MemAvailable' in x][0].split()[1])
            used_percent = round((total - available) / total * 100, 1)
            status["memory_usage_percent"] = used_percent
    except:
        status["memory_usage_percent"] = None

    return status


def send_heartbeat(credentials):
    """
    Send heartbeat to HFSS server.

    This updates the station's last_seen timestamp and provides status info.
    """
    status = get_station_status()

    # Prepare heartbeat payload
    payload = {
        "device_metadata": {
            # Mark as heartbeat (not GPS data)
            "heartbeat": True,
            "station_status": "online",

            # Station info
            "station_lat": STATION_LAT,
            "station_lon": STATION_LON,
            "station_altitude": STATION_ALTITUDE,

            # System status
            "cpu_temp": status["cpu_temp"],
            "uptime": status["uptime"],
            "disk_usage_percent": status["disk_usage_percent"],
            "memory_usage_percent": status["memory_usage_percent"],

            # OGN specific
            "ogn_clients": status["connected_clients"],

            # Timestamp
            "timestamp": status["timestamp"]
        }
    }

    try:
        response = requests.post(
            f"{SERVER_URL}/api/v1/gps",
            headers={"X-API-Key": credentials["api_key"]},
            json=payload,
            timeout=10
        )

        if response.status_code == 200:
            logger.info(
                f"✓ Heartbeat sent - "
                f"CPU: {status['cpu_temp']}°C, "
                f"Uptime: {status['uptime']}s, "
                f"Disk: {status['disk_usage_percent']}%"
            )
            return True
        else:
            logger.warning(f"✗ Heartbeat failed: HTTP {response.status_code}")
            logger.debug(f"  Response: {response.text}")
            return False

    except requests.exceptions.ConnectionError:
        logger.error(f"✗ Cannot connect to server: {SERVER_URL}")
        return False

    except Exception as e:
        logger.error(f"✗ Heartbeat error: {e}")
        return False


def main():
    """Main application loop."""
    logger.info("=" * 60)
    logger.info("OGN Station Monitor Starting")
    logger.info("=" * 60)
    logger.info(f"Station ID: {STATION_ID}")
    logger.info(f"Server: {SERVER_URL}")
    logger.info(f"Location: {STATION_LAT}, {STATION_LON}")
    logger.info(f"Heartbeat interval: {HEARTBEAT_INTERVAL}s")
    logger.info("=" * 60)

    # Load existing credentials or register
    credentials = load_credentials()

    if not credentials:
        logger.info("No credentials found - registering station")
        credentials = register_station()

        if not credentials:
            logger.error("Failed to register station. Exiting.")
            logger.error("Check configuration and server connectivity.")
            sys.exit(1)
    else:
        logger.info(f"Using saved credentials for {credentials['device_id']}")

    # Send initial heartbeat
    logger.info("Sending initial heartbeat...")
    send_heartbeat(credentials)

    # Main heartbeat loop
    logger.info("Entering heartbeat loop...")
    consecutive_failures = 0

    while True:
        try:
            time.sleep(HEARTBEAT_INTERVAL)

            success = send_heartbeat(credentials)

            if success:
                consecutive_failures = 0
            else:
                consecutive_failures += 1

                # Re-register if many consecutive failures
                if consecutive_failures >= 10:
                    logger.warning("Too many consecutive failures - attempting re-registration")
                    new_credentials = register_station()
                    if new_credentials:
                        credentials = new_credentials
                        consecutive_failures = 0

        except KeyboardInterrupt:
            logger.info("Shutting down gracefully...")
            break

        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
            time.sleep(60)  # Wait before retrying


if __name__ == "__main__":
    main()
```

Make it executable:

```bash
chmod +x ogn_station.py
```

### Step 3: Configure the Script

Edit the configuration section:

```bash
nano ogn_station.py
```

Update these values:

```python
# Server configuration
SERVER_URL = "https://hfss-dev.yourdomain.com"  # Your actual server

# Station identification
STATION_ID = "OGN_STATION_ALPINE001"  # Unique ID for this station

# Station location
STATION_LAT = 45.464211  # Your station's latitude
STATION_LON = 6.982689   # Your station's longitude
STATION_ALTITUDE = 1850  # meters

# Security (get this from server admin)
MANUFACTURER_SECRET = "a3f8d9e2c1b4567890abcdef1234567890abcdef12345678"
```

### Step 4: Test Registration

Run the script manually first to test:

```bash
python3 ogn_station.py
```

**Expected output:**
```
============================================================
OGN Station Monitor Starting
============================================================
Station ID: OGN_STATION_ALPINE001
Server: https://hfss-dev.yourdomain.com
Location: 45.464211, 6.982689
Heartbeat interval: 300s
============================================================
2025-11-15 10:30:45 [INFO] No credentials found - registering station
2025-11-15 10:30:45 [INFO] Registering station OGN_STATION_ALPINE001 with server
2025-11-15 10:30:46 [INFO] ✓ Station registered successfully!
2025-11-15 10:30:46 [INFO]   Device ID: OGN_STATION_ALPINE001
2025-11-15 10:30:46 [INFO]   Credentials saved to: /home/pi/.ogn_credentials.json
2025-11-15 10:30:46 [INFO] Using saved credentials for OGN_STATION_ALPINE001
2025-11-15 10:30:46 [INFO] Sending initial heartbeat...
2025-11-15 10:30:47 [INFO] ✓ Heartbeat sent - CPU: 42.3°C, Uptime: 86400s, Disk: 45.2%
2025-11-15 10:30:47 [INFO] Entering heartbeat loop...
```

Press `Ctrl+C` to stop.

### Step 5: Create Systemd Service

For automatic startup and management:

```bash
sudo nano /etc/systemd/system/ogn-station.service
```

Paste:

```ini
[Unit]
Description=OGN Station Monitor for HFSS
Documentation=https://github.com/your-org/hfss-digi/docs/OGN_STATION_SETUP_GUIDE.md
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
Group=pi
WorkingDirectory=/home/pi/ogn-station
ExecStart=/usr/bin/python3 /home/pi/ogn-station/ogn_station.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Logging
SyslogIdentifier=ogn-station

# Resource limits (optional)
MemoryLimit=256M
CPUQuota=25%

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
# Enable auto-start on boot
sudo systemctl enable ogn-station

# Start the service
sudo systemctl start ogn-station

# Check status
sudo systemctl status ogn-station

# View logs
sudo journalctl -u ogn-station -f
```

### Step 6: Setup Log Rotation

Prevent logs from filling disk:

```bash
sudo nano /etc/logrotate.d/ogn-station
```

Paste:

```
/var/log/ogn_station.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0644 pi pi
}
```

---

## Testing & Verification

### Test 1: Verify Registration

On the server, check that the device was registered:

```bash
# SSH to server
ssh hfss@hfss-dev
cd ~/apps/hfss-digi

# Query database
docker compose exec db psql -U postgres -d gps_tracking -c \
  "SELECT device_id, name, manufacturer, device_type, is_active, last_seen
   FROM devices
   WHERE device_id LIKE 'OGN_STATION_%';"
```

**Expected output:**
```
     device_id      |        name         | manufacturer | device_type | is_active |         last_seen
--------------------+--------------------+--------------+-------------+-----------+----------------------------
 OGN_STATION_ALPINE001 | OGN Station Alpine | OGN          | OGN_STATION | t         | 2025-11-15 10:35:47.123+00
```

### Test 2: Check API Response

```bash
# Get station details via API
curl -H "Authorization: Bearer <admin_token>" \
  "http://localhost/api/v1/admin/devices?device_id=OGN_STATION_ALPINE001"
```

**Expected JSON:**
```json
{
  "items": [{
    "device_id": "OGN_STATION_ALPINE001",
    "name": "OGN Station Alpine",
    "manufacturer": "OGN",
    "device_type": "OGN_STATION",
    "is_active": true,
    "last_seen": "2025-11-15T10:35:47.123Z",
    "device_metadata": {
      "source": "http",
      "latitude": 45.464211,
      "longitude": 6.982689,
      "is_station": true
    }
  }]
}
```

### Test 3: Monitor Heartbeats

Watch the station logs on Raspberry Pi:

```bash
sudo journalctl -u ogn-station -f
```

Should see heartbeats every 5 minutes:

```
Nov 15 10:35:47 raspberrypi ogn-station[1234]: [INFO] ✓ Heartbeat sent - CPU: 42.3°C, Uptime: 86400s
Nov 15 10:40:47 raspberrypi ogn-station[1234]: [INFO] ✓ Heartbeat sent - CPU: 42.1°C, Uptime: 86700s
```

### Test 4: Check Server Logs

On the server, verify heartbeats are received:

```bash
# View API logs
docker compose logs -f api1 | grep OGN_STATION
```

---

## Administration & Monitoring

### View All OGN Stations

```bash
# API endpoint
GET /api/v1/admin/devices?manufacturer=OGN&device_type=OGN_STATION

# cURL example
curl -H "Authorization: Bearer <token>" \
  "http://your-server/api/v1/admin/devices?manufacturer=OGN&device_type=OGN_STATION"
```

### Filter by Category

If you created the `station` device type:

```bash
GET /api/v1/admin/devices?category=station
```

### Check Station Health

Stations are considered **offline** if `last_seen` is older than 10 minutes:

```sql
-- Query offline stations
SELECT device_id, name, last_seen,
       EXTRACT(EPOCH FROM (NOW() - last_seen))/60 AS minutes_since_last_seen
FROM devices
WHERE manufacturer = 'OGN'
  AND device_type = 'OGN_STATION'
  AND last_seen < NOW() - INTERVAL '10 minutes'
ORDER BY last_seen DESC;
```

### Dashboard Metrics

Key metrics to monitor:

- **Total OGN Stations:** Count of registered stations
- **Online Stations:** `last_seen` within 10 minutes
- **Average CPU Temperature:** From heartbeat metadata
- **Stations by Location:** Map view of fixed coordinates

---

## Troubleshooting

### Problem: Registration Fails with "Invalid registration credentials"

**Cause:** HMAC token validation failed

**Solutions:**
1. Verify `MANUFACTURER_SECRET` matches on both server and Pi
2. Check `STATION_ID` starts with `OGN_STATION_`
3. Ensure `.env` was reloaded after changes (`docker compose restart api1 api2`)

**Debug:**
```bash
# On Pi - generate token manually
python3 -c "
import hmac, hashlib
device_id = 'OGN_STATION_ALPINE001'
manufacturer = 'OGN'
secret = 'your_secret_here'
message = f'{manufacturer}:{device_id}'
token = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
print(f'Token: {token}')
"

# On server - check expected token
docker compose exec api1 python -c "
from app.core.device_security import device_security
token = device_security.generate_registration_token('OGN_STATION_ALPINE001', 'OGN')
print(f'Expected token: {token}')
"
```

### Problem: Heartbeats Not Received

**Cause:** API key invalid or network issues

**Solutions:**
1. Check `/home/pi/.ogn_credentials.json` exists and is readable
2. Verify `X-API-Key` header is sent
3. Check firewall allows outbound HTTPS

**Debug:**
```bash
# Test API key manually
API_KEY=$(jq -r '.api_key' /home/pi/.ogn_credentials.json)

curl -X POST "http://your-server/api/v1/gps" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"device_metadata": {"heartbeat": true, "test": true}}'
```

### Problem: Station Shows as Inactive

**Cause:** Auto-approval may be disabled for TCP/HTTP devices

**Solution:**
```bash
# Manually activate station via API
curl -X PATCH "http://localhost/api/v1/admin/devices/OGN_STATION_ALPINE001" \
  -H "Authorization: Bearer <admin_token>" \
  -d '{"is_active": true}'
```

### Problem: Service Won't Start

**Debug systemd service:**
```bash
# Check service status
sudo systemctl status ogn-station

# View full logs
sudo journalctl -u ogn-station -n 100 --no-pager

# Check for Python errors
sudo journalctl -u ogn-station | grep -i error

# Test script manually
cd /home/pi/ogn-station
python3 ogn_station.py
```

---

## Security Considerations

### Best Practices

1. **Secure Credentials Storage**
   - File permissions: `chmod 600 /home/pi/.ogn_credentials.json`
   - Only readable by `pi` user
   - Never commit credentials to git

2. **Manufacturer Secret Protection**
   - Store in environment variable or secure vault
   - Different secret per manufacturer
   - Rotate if compromised

3. **Network Security**
   - Use HTTPS for all API calls
   - Validate SSL certificates
   - Consider VPN for station-to-server communication

4. **Access Control**
   - Limit SSH access to Raspberry Pi
   - Use key-based authentication
   - Regular security updates

### Rotating Credentials

If API key is compromised:

```bash
# On server - rotate key
curl -X POST "http://localhost/api/v1/devices/OGN_STATION_ALPINE001/rotate-key" \
  -H "Content-Type: application/json" \
  -d '{"current_api_key": "old_key_here", "reason": "Security rotation"}'

# On Pi - delete old credentials
rm /home/pi/.ogn_credentials.json

# Restart service to re-register
sudo systemctl restart ogn-station
```

---

## Advanced Configuration

### Custom Heartbeat Interval

Edit `ogn_station.py`:

```python
HEARTBEAT_INTERVAL = 600  # 10 minutes instead of 5
```

### Multiple Stations on Same Pi

Run separate instances:

```bash
# Station 1
/home/pi/ogn-station-1/ogn_station.py  # STATION_ID=OGN_STATION_ALPINE001

# Station 2
/home/pi/ogn-station-2/ogn_station.py  # STATION_ID=OGN_STATION_ALPINE002

# Create separate systemd services
sudo systemctl enable ogn-station-1
sudo systemctl enable ogn-station-2
```

### Integration with OGN Software

Example: Read OGN receiver status

```python
def get_ogn_status():
    """Read status from OGN receiver logs"""
    try:
        # Read rtlsdr-ogn status
        with open('/var/log/rtlsdr-ogn.log', 'r') as f:
            lines = f.readlines()[-100:]  # Last 100 lines

        # Count unique aircraft IDs
        aircraft = set()
        for line in lines:
            if 'FLARM' in line:
                # Extract FLARM ID
                # Format depends on your OGN software
                pass

        return len(aircraft)
    except:
        return 0
```

---

## FAQ

**Q: Can one Raspberry Pi run multiple station IDs?**
A: Yes, but each needs unique credentials. Run separate script instances.

**Q: How do I change station coordinates?**
A: Edit `STATION_LAT`/`STATION_LON` in script, delete credentials file, restart service to re-register.

**Q: What happens if internet connection is lost?**
A: Service retries heartbeats. After 10 consecutive failures, attempts re-registration.

**Q: Can I send additional custom data?**
A: Yes, add to `device_metadata` in heartbeat payload.

**Q: How do I unregister a station?**
A: Delete from admin panel or via API: `DELETE /api/v1/admin/devices/{device_id}`

---

## Support

For issues or questions:

1. Check this guide's Troubleshooting section
2. Review logs: `sudo journalctl -u ogn-station -n 100`
3. Contact development team with:
   - Station ID
   - Error messages from logs
   - Server URL
   - Raspberry Pi model/OS version

---

## Appendix A: Quick Reference

### Service Commands

```bash
# Start
sudo systemctl start ogn-station

# Stop
sudo systemctl stop ogn-station

# Restart
sudo systemctl restart ogn-station

# Status
sudo systemctl status ogn-station

# Logs
sudo journalctl -u ogn-station -f

# Enable auto-start
sudo systemctl enable ogn-station

# Disable auto-start
sudo systemctl disable ogn-station
```

### File Locations

- Script: `/home/pi/ogn-station/ogn_station.py`
- Credentials: `/home/pi/.ogn_credentials.json`
- Service: `/etc/systemd/system/ogn-station.service`
- Logs: `/var/log/ogn_station.log` and `journalctl`
- Config: Edit variables in `ogn_station.py`

### API Endpoints

- Registration: `POST /api/v1/devices/register`
- Heartbeat: `POST /api/v1/gps` (with `X-API-Key` header)
- List Stations: `GET /api/v1/admin/devices?manufacturer=OGN`
- Station Detail: `GET /api/v1/admin/devices/{device_id}`

---

**Document Version:** 1.0
**Last Updated:** 2025-11-15
**For HFSS System Version:** 2.x
