# OGN Web Configuration Interface

**Version:** 2.0.0
**Stack:** React + Vite + Tailwind CSS + FastAPI + Uvicorn

Professional web interface for configuring OGN receivers with HFSS integration, WiFi management, and system monitoring.

---

## Features

### 1. **OGN Configuration**
- Edit station callsign, location (lat/lon/altitude)
- Configure RF settings (frequency correction, center frequency, gain)
- Save and restart OGN service with one click
- Embedded live OGN receiver status (port 8080)

### 2. **WiFi Management**
- Toggle wlan0 and eth1 interfaces on/off
- View IP addresses and interface status
- Add/edit/delete WiFi networks for wlan0
- Set network priorities
- Real-time status updates

### 3. **HFSS Registration**
- Register station with HFSS tracking server
- Automatic heartbeat every 5 minutes
- Send system status (CPU temp, uptime, disk usage, memory)
- Start/stop heartbeat manually
- Unregister station

### 4. **System Status**
- View hostname, CPU temperature, uptime, memory usage
- HFSS registration and heartbeat status
- Real-time monitoring dashboard

---

## Architecture

```
┌─────────────────────────────────────────────┐
│  React Frontend (Vite + Tailwind)          │
│  - Modern UI components                     │
│  - Real-time status updates                 │
│  - Responsive design                        │
└─────────────┬───────────────────────────────┘
              │ HTTP/WebSocket
              ▼
┌─────────────────────────────────────────────┐
│  FastAPI Backend (Uvicorn)                  │
│  - RESTful API endpoints                    │
│  - HFSS registration & heartbeat            │
│  - WiFi management                          │
│  - System info collection                   │
└─────────────┬───────────────────────────────┘
              │
              ├──▶ OGN Config (Template.conf)
              ├──▶ WiFi Config (wpa_supplicant.conf)
              ├──▶ HFSS Server (via HTTP API)
              └──▶ System Info (/proc, /sys)
```

---

## Quick Start

### Development

#### 1. Backend (FastAPI)

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

Backend runs on: `http://localhost:8082`

#### 2. Frontend (React)

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on: `http://localhost:3000` with API proxy to backend.

---

## Production Deployment

### Option 1: Automated Deployment (Recommended)

```bash
cd ogn-web
./deploy.sh
```

This script:
1. Builds React frontend
2. Creates deployment package
3. Uploads to `hfss@flarm2.local`
4. Sets up Python virtual environment
5. Creates systemd service
6. Configures nginx (if available)

### Option 2: Manual Deployment

#### Build Frontend

```bash
cd frontend
npm install
npm run build
```

Built files will be in `frontend/dist/`

#### Transfer to Raspberry Pi

```bash
scp -r backend frontend/dist hfss@flarm2.local:/home/hfss/ogn-web/
scp ../env hfss@flarm2.local:/home/hfss/ogn-web/.env
```

#### Setup on Raspberry Pi

```bash
ssh hfss@flarm2.local

cd /home/hfss/ogn-web

# Setup Python environment
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt

# Run backend
python3 backend/main.py
```

#### Create Systemd Service

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

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable ogn-web
sudo systemctl start ogn-web
sudo systemctl status ogn-web
```

---

## Configuration

### Backend Configuration

Edit `backend/main.py` to change:

- `CONFIG_FILE`: Path to OGN Template.conf
- `WPA_SUPPLICANT`: Path to wpa_supplicant.conf
- `CREDENTIALS_FILE`: Path to store HFSS credentials
- `HEARTBEAT_INTERVAL`: Heartbeat interval in seconds (default: 300)

### Environment Variables

Create `.env` file in project root (copy from parent directory):

```bash
MANUFACTURER_SECRET_OGN=your_secret_here
```

This secret is used for HFSS station registration.

---

## API Documentation

### OGN Configuration

#### Get Config
```http
GET /api/config
```

#### Save Config
```http
POST /api/config
Content-Type: application/json

{
  "call": "NOCALL",
  "latitude": 45.123456,
  "longitude": 7.654321,
  "altitude": 1200,
  "freqcorr": 0.0,
  "centerfreq": 868.2,
  "gain": 40.0
}
```

### WiFi Management

#### Get WiFi Status
```http
GET /api/wifi/status
```

#### Toggle Interface
```http
POST /api/wifi/toggle
Content-Type: application/json

{
  "interface": "wlan0",
  "action": "on"
}
```

#### Add Network
```http
POST /api/wifi/add
Content-Type: application/json

{
  "ssid": "MyNetwork",
  "psk": "password123",
  "priority": 1
}
```

#### Edit Network Password
```http
POST /api/wifi/edit
Content-Type: application/json

{
  "network_id": 0,
  "psk": "newpassword123"
}
```

#### Delete Network
```http
POST /api/wifi/delete
Content-Type: application/json

{
  "network_id": 0
}
```

### HFSS Registration

#### Get Registration Status
```http
GET /api/hfss/status
```

#### Register Station
```http
POST /api/hfss/register
Content-Type: application/json

{
  "server_url": "https://your-hfss-server.com",
  "station_id": "OGN_STATION_ALPINE01",
  "station_name": "Alpine OGN Station",
  "manufacturer_secret": "your_secret_here"
}
```

#### Unregister Station
```http
POST /api/hfss/unregister
```

#### Start/Stop Heartbeat
```http
POST /api/hfss/heartbeat/start
POST /api/hfss/heartbeat/stop
```

### System Info

#### Get System Information
```http
GET /api/system
```

Response:
```json
{
  "hostname": "flarm2",
  "uptime": "up 2 days, 3:15",
  "cpu_temp": 42.3,
  "memory_usage": "512M / 1.9G"
}
```

---

## Security Considerations

1. **HTTPS**: Use nginx with SSL/TLS in production
2. **Firewall**: Restrict port 8082 to local network only
3. **Credentials**: Stored in `/home/hfss/.ogn_credentials.json` with 600 permissions
4. **Secrets**: Never commit `.env` file to git
5. **sudo**: Backend requires sudo permissions for:
   - WiFi interface control (`ip link`)
   - WiFi configuration (`wpa_cli`)
   - OGN service restart (`service rtlsdr-ogn restart`)

### Sudo Configuration

Add to `/etc/sudoers.d/ogn-web`:

```bash
hfss ALL=(ALL) NOPASSWD: /usr/sbin/ip link set wlan0 *
hfss ALL=(ALL) NOPASSWD: /usr/sbin/ip link set eth1 *
hfss ALL=(ALL) NOPASSWD: /sbin/wpa_cli *
hfss ALL=(ALL) NOPASSWD: /usr/sbin/service rtlsdr-ogn *
```

---

## Troubleshooting

### Backend Won't Start

```bash
# Check logs
sudo journalctl -u ogn-web -f

# Test manually
cd /home/hfss/ogn-web/backend
source ../venv/bin/activate
python3 main.py
```

### Frontend Build Fails

```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
npm run build
```

### Heartbeat Not Working

1. Check registration status:
   ```bash
   curl http://localhost:8082/api/hfss/status
   ```

2. Check credentials file:
   ```bash
   cat /home/hfss/.ogn_credentials.json
   ```

3. Test manual heartbeat:
   ```bash
   curl -X POST http://localhost:8082/api/hfss/heartbeat/start
   ```

4. Check backend logs:
   ```bash
   sudo journalctl -u ogn-web | grep heartbeat
   ```

### WiFi Commands Fail

Check sudo permissions:
```bash
sudo -l
```

Should show `NOPASSWD` entries for ip, wpa_cli, and service commands.

---

## Development

### Tech Stack

**Frontend:**
- React 18
- Vite (build tool)
- Tailwind CSS (styling)
- Axios (HTTP client)
- lucide-react (icons)

**Backend:**
- Python 3.9+
- FastAPI (web framework)
- Uvicorn (ASGI server)
- Pydantic (data validation)
- Requests (HTTP client)

### Project Structure

```
ogn-web/
├── backend/
│   ├── main.py              # FastAPI application
│   └── requirements.txt     # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── HFSSRegistration.jsx
│   │   │   ├── OGNConfig.jsx
│   │   │   ├── WiFiManagement.jsx
│   │   │   └── SystemStatus.jsx
│   │   ├── App.jsx          # Main app component
│   │   ├── main.jsx         # React entry point
│   │   └── index.css        # Tailwind CSS
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   └── postcss.config.js
├── deploy.sh                # Deployment script
└── README.md
```

---

## License

Part of the HFSS OGN Receiver project.

---

## Support

For issues or questions:

1. Check this README
2. Review logs: `sudo journalctl -u ogn-web -f`
3. Check HFSS server connectivity
4. Verify sudo permissions
5. Test API endpoints manually with curl

---

## Changelog

### v2.0.0 (2025-11-15)
- Complete rewrite with React + FastAPI
- Added HFSS registration and heartbeat
- Modern UI with Tailwind CSS
- Improved WiFi management
- Real-time system monitoring
- Automated deployment script
