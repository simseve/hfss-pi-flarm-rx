# OGN FLARM Receiver Installation Guide

Complete installation and configuration guide for setting up an Open Glider Network (OGN) FLARM receiver on Raspberry Pi 3B+.

## Table of Contents
- [Hardware Requirements](#hardware-requirements)
- [Fresh Installation Steps](#fresh-installation-steps)
- [Configuration](#configuration)
- [Web Interface](#web-interface)
- [Services Management](#services-management)
- [Troubleshooting](#troubleshooting)
- [Technical Details](#technical-details)

---

## Hardware Requirements

- **Raspberry Pi 3 Model B Plus** (or Pi 4/5, Zero 2W)
- **RTL-SDR Dongle** (RTL2832U chipset with R820T tuner)
- **Antenna** tuned for 868 MHz (EU) or 915 MHz (US/Canada)
- **SD Card** (16GB minimum, 32GB recommended)
- **Power Supply** (5V 2.5A minimum)
- **Network Connection** (WiFi or Ethernet)

---

## Fresh Installation Steps

### 1. Flash OS Image

**Download Raspberry Pi OS Bookworm (32-bit)**
- Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
- Select: **Raspberry Pi OS Lite (32-bit)** - Debian 12 Bookworm
- **Important**: Use 32-bit, not 64-bit (better binary compatibility)

**Configure during imaging:**
- Set hostname: `flarm2`
- Enable SSH
- Configure WiFi/Ethernet
- Set username: `hfss` (or your choice)
- Set timezone

### 2. Initial System Setup

```bash
# SSH into the Pi
ssh hfss@flarm2.local
# or use IP address: ssh hfss@<ip-address>

# Update system
sudo apt update
sudo apt full-upgrade -y

# Install git
sudo apt install git -y
```

### 3. Install OGN Receiver Software

```bash
# Clone VirusPilot's OGN installer
cd ~
git clone https://github.com/VirusPilot/ogn-pi34.git
cd ogn-pi34

# Run the installer (will pause for configuration)
sudo ./install-pi34.sh
```

**During installation:**
- Packages will be installed automatically
- When nano opens `Template.conf`, press Ctrl+X (we'll configure via web later)
- Press 'N' when asked to reboot (we'll do more setup first)

### 4. Configure for Your User

The installer defaults to user `pi`, but if using a different username:

```bash
# Update service configuration
sudo sed -i 's|pi /home/pi/rtlsdr-ogn|hfss /home/hfss/ogn-pi34/rtlsdr-ogn-0.3.2|g' /etc/rtlsdr-ogn.conf

# Restart service
sudo service rtlsdr-ogn restart
```

### 5. Install Web Configuration Interface

```bash
# Install Flask
sudo apt install python3-flask -y

# Create the web interface (see web app code below)
nano ~/ogn-config-web.py
# Paste the Flask app code (provided separately)

# Make it executable
chmod +x ~/ogn-config-web.py

# Allow service restart without password
echo 'hfss ALL=(ALL) NOPASSWD: /usr/sbin/service rtlsdr-ogn restart' | sudo tee /etc/sudoers.d/ogn-config
sudo chmod 440 /etc/sudoers.d/ogn-config

# Create systemd service
sudo nano /etc/systemd/system/ogn-config-web.service
```

**Service file content:**
```ini
[Unit]
Description=OGN Configuration Web Interface
After=network.target

[Service]
Type=simple
User=hfss
WorkingDirectory=/home/hfss
ExecStart=/usr/bin/python3 /home/hfss/ogn-config-web.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Enable and start:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable ogn-config-web
sudo systemctl start ogn-config-web
```

### 6. Calibrate Frequency

```bash
# Stop OGN service
sudo service rtlsdr-ogn stop

# Run GSM scan
cd ~/ogn-pi34/rtlsdr-ogn-0.3.2
./gsm_scan --gain 30

# Note the "Receiver Xtal correction" value (e.g., +0.983 ppm)
# Round to 1 decimal place (e.g., 1.0)

# Update via web interface or manually in Template.conf

# Restart service
sudo service rtlsdr-ogn start
```

---

## Configuration

### Initial Configuration Required

**Station Information:**
- **Callsign**: Your amateur radio callsign or unique station ID (max 9 characters)
- **Latitude**: Decimal degrees (e.g., 45.97316)
- **Longitude**: Decimal degrees (e.g., 8.87516)
- **Altitude**: Meters above sea level
- **Frequency Correction**: PPM from GSM scan (e.g., 1.0)
- **Center Frequency**: 868.2 MHz (EU), 915.0 MHz (US/Canada)

### Configuration Files

**Main Config:** `~/ogn-pi34/rtlsdr-ogn-0.3.2/Template.conf`
```
RF:
{
  FreqCorr = 1.0;           # From GSM scan
  GSM: { CenterFreq = 950.0; Gain = 30.0; };
  OGN: { CenterFreq = 868.2; Gain = 40.0; };
};

Position:
{
  Latitude   =  45.97316;   # Your location
  Longitude  =  8.87516;    # Your location
  Altitude   =  280;        # Meters MSL
};

APRS:
{
  Call = "HfssHq2";         # Your callsign
  Server = "aprs.glidernet.org:14580";
};

HTTP:
{
  Port = 8080;              # OGN RF monitor
};
```

**Service Config:** `/etc/rtlsdr-ogn.conf`
```
50000  hfss /home/hfss/ogn-pi34/rtlsdr-ogn-0.3.2  ./ogn-rf     Template.conf
50001  hfss /home/hfss/ogn-pi34/rtlsdr-ogn-0.3.2  ./ogn-decode Template.conf
```

---

## Web Interface

### Access Points

**Configuration Interface (Port 8082):**
```
http://flarm2.local:8082
http://192.168.68.118:8082
```
- Change station name, coordinates, altitude
- Adjust RF parameters
- Embedded iframe of OGN monitor

**OGN RF Monitor (Port 8080):**
```
http://flarm2.local:8080
http://192.168.68.118:8080
```
- Real-time RF statistics
- Signal quality metrics
- Direct from ogn-rf process

**OGN Decode Status (Port 8081):**
```
http://flarm2.local:8081
http://192.168.68.118:8081
```
- Decoder status
- APRS connection info
- Direct from ogn-decode process

### Telnet Access

**RF Data Stream (Port 50000):**
```bash
telnet localhost 50000
```
- Raw demodulated RF data
- Signal measurements
- Controlled by procServ

**Decoded APRS Stream (Port 50001):**
```bash
telnet localhost 50001
```
- Decoded aircraft positions
- FLARM IDs and data
- APRS packets being sent

---

## Services Management

### OGN Receiver Service

```bash
# Status
sudo service rtlsdr-ogn status

# Start
sudo service rtlsdr-ogn start

# Stop
sudo service rtlsdr-ogn stop

# Restart
sudo service rtlsdr-ogn restart

# View logs
tail -f /var/log/rtlsdr-ogn/50000  # RF logs
tail -f /var/log/rtlsdr-ogn/50001  # Decode logs
```

### Web Configuration Service

```bash
# Status
sudo systemctl status ogn-config-web

# Start
sudo systemctl start ogn-config-web

# Stop
sudo systemctl stop ogn-config-web

# Restart
sudo systemctl restart ogn-config-web

# View logs
sudo journalctl -u ogn-config-web -f
```

### Auto-start on Boot

Both services are configured to start automatically:
- `rtlsdr-ogn` via SysV init (`/etc/rc*.d/S01rtlsdr-ogn`)
- `ogn-config-web` via systemd (`multi-user.target`)

**Verify auto-start:**
```bash
# Check OGN service
ls -la /etc/rc3.d/*rtlsdr*

# Check web service
sudo systemctl is-enabled ogn-config-web
```

---

## Troubleshooting

### Service Not Starting

**Check processes:**
```bash
ps aux | grep ogn
netstat -tulpn | grep -E '50000|50001|8080|8081|8082'
```

**Check RTL-SDR hardware:**
```bash
lsusb | grep -i realtek
rtl_test -t
```

**Review logs:**
```bash
sudo journalctl -u ogn-config-web -n 50
tail -50 /var/log/rtlsdr-ogn/50000
tail -50 /var/log/rtlsdr-ogn/50001
```

### No Data / No Aircraft

**Check APRS connection:**
```bash
telnet localhost 50001
# Look for "Connected to aprs.glidernet.org"
# Look for "logresp <callsign> verified"
```

**Verify RF reception:**
```bash
telnet localhost 50000
# Should see continuous RF statistics
```

**Check antenna connection and tuning**

### Web Interface Not Accessible

**Check service:**
```bash
sudo systemctl status ogn-config-web
curl http://localhost:8082
```

**Check firewall:**
```bash
sudo iptables -L
```

**Try IP address instead of .local:**
```bash
hostname -I  # Get IP address
# Access via http://<ip>:8082
```

### Frequency Drift

**Recalibrate with GSM scan:**
```bash
cd ~/ogn-pi34/rtlsdr-ogn-0.3.2
sudo service rtlsdr-ogn stop
./gsm_scan --gain 30
# Update FreqCorr in Template.conf
sudo service rtlsdr-ogn start
```

### Permission Denied Errors

**Fix file permissions:**
```bash
sudo chown -R hfss:hfss ~/ogn-pi34
chmod +x ~/ogn-config-web.py
```

**Check sudoers:**
```bash
sudo visudo -c  # Check syntax
cat /etc/sudoers.d/ogn-config
```

---

## Technical Details

### System Architecture

```
┌─────────────────────────────────────────────┐
│  Raspberry Pi 3B+ (Debian 12 Bookworm)      │
│  User: hfss, Hostname: flarm2               │
└─────────────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │   RTL-SDR Dongle        │
        │   (RTL2832U + R820T)    │
        └────────────┬────────────┘
                     │
        ┌────────────┴────────────┐
        │   ogn-rf (Port 8080)    │
        │   Demodulates RF         │
        │   Telnet: 50000          │
        └────────────┬────────────┘
                     │ FIFO pipe
        ┌────────────┴────────────┐
        │   ogn-decode (8081)     │
        │   Decodes FLARM          │
        │   Telnet: 50001          │
        └────────────┬────────────┘
                     │
        ┌────────────┴────────────┐
        │   APRS Network          │
        │   aprs.glidernet.org    │
        │   Port: 14580           │
        └─────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │   live.glidernet.org    │
        │   Public Tracking Map   │
        └─────────────────────────┘

┌─────────────────────────────────────────────┐
│  Flask Web Interface (Port 8082)            │
│  - Configuration UI                         │
│  - Embedded RF monitor                      │
│  - Auto-restart on config change            │
└─────────────────────────────────────────────┘
```

### Port Reference

| Port  | Service           | Protocol | Purpose                    |
|-------|-------------------|----------|----------------------------|
| 8080  | ogn-rf            | HTTP     | RF monitor web interface   |
| 8081  | ogn-decode        | HTTP     | Decoder status interface   |
| 8082  | ogn-config-web    | HTTP     | Configuration UI           |
| 50000 | procServ (ogn-rf) | Telnet   | RF data stream             |
| 50001 | procServ (decode) | Telnet   | APRS data stream           |
| 14580 | APRS Server       | TCP      | Outbound to glidernet.org  |

### File Locations

```
/home/hfss/
├── ogn-pi34/
│   └── rtlsdr-ogn-0.3.2/
│       ├── Template.conf          # Main configuration
│       ├── WW15MGH.DAC            # Geoid data
│       ├── ogn-rf                 # RF receiver binary
│       ├── ogn-decode             # Decoder binary
│       ├── gsm_scan               # Calibration tool
│       └── rtlsdr-ogn             # Init script
└── ogn-config-web.py              # Flask web app

/etc/
├── init.d/
│   └── rtlsdr-ogn                 # Service init script
├── rtlsdr-ogn.conf                # procServ configuration
├── sudoers.d/
│   └── ogn-config                 # Sudo permissions
└── systemd/system/
    └── ogn-config-web.service     # Web UI service

/var/log/rtlsdr-ogn/
├── 50000                          # ogn-rf logs
└── 50001                          # ogn-decode logs
```

### Network Configuration

**Hostname Resolution:**
- mDNS: `flarm2.local` (via avahi-daemon)
- Direct IP: Check with `hostname -I`
- SSH: `ssh hfss@flarm2.local` or `ssh hfss@<ip>`

**WiFi Configuration:**
- Interface: wlan0
- Network: Configured during imaging
- Check: `ip addr show wlan0`

---

## What We Did After Fresh Image

1. ✅ Updated system packages
2. ✅ Installed git and development tools
3. ✅ Cloned VirusPilot ogn-pi34 repository
4. ✅ Installed OGN receiver binaries (ARM 32-bit)
5. ✅ Configured for user `hfss` (not default `pi`)
6. ✅ Calibrated frequency with GSM scan (+1.0 ppm)
7. ✅ Configured station (HfssHq2, coordinates, altitude)
8. ✅ Created Flask web configuration interface
9. ✅ Set up auto-start services (OGN + web UI)
10. ✅ Verified all ports and telnet access
11. ✅ Tested APRS connection to glidernet.org

**System is now:**
- ✅ Receiving FLARM signals
- ✅ Decoding aircraft positions
- ✅ Uploading to OGN network
- ✅ Accessible via web interfaces
- ✅ Auto-starting on boot
- ✅ Remotely configurable

**Your station will appear on http://live.glidernet.org within 10-15 minutes!**

---

## Additional Resources

- OGN Wiki: http://wiki.glidernet.org
- Live Map: http://live.glidernet.org
- APRS Passcode: https://apps.magicbug.co.uk/passcode/
- VirusPilot GitHub: https://github.com/VirusPilot/ogn-pi34
- OGN GitHub: https://github.com/glidernet/ogn-rf

---

**Document Version:** 1.0
**Last Updated:** 2025-11-12
**Station:** HfssHq2
**Location:** 45.97316°N, 8.87516°E, 280m
