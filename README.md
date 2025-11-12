# OGN FLARM Receiver for Raspberry Pi

Complete setup for an Open Glider Network (OGN) FLARM receiver with web-based configuration interface.

## Quick Start

### Hardware
- Raspberry Pi 3B+ (or Pi 4/5, Zero 2W)
- RTL-SDR dongle (RTL2832U with R820T tuner)
- 868 MHz antenna (EU) or 915 MHz (US/Canada)

### Installation
1. Flash **Raspberry Pi OS Bookworm 32-bit Lite** to SD card
2. SSH into Pi: `ssh hfss@flarm2.local`
3. Run:
```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install git -y
git clone https://github.com/VirusPilot/ogn-pi34.git
cd ogn-pi34
sudo ./install-pi34.sh
```
4. Configure via web interface at `http://flarm2.local:8082`

**Full installation guide:** [INSTALLATION.md](INSTALLATION.md)

## Features

### 🌐 Web Configuration Interface (Port 8082)
- Change station callsign, coordinates, and altitude
- Adjust RF parameters (frequency correction, gain)
- Live OGN RF monitor embedded
- Auto-restart service on configuration save
- Auto-starts on boot

### 📡 OGN Receiver
- Receives FLARM signals from gliders, aircraft, balloons
- Decodes aircraft positions and IDs
- Uploads to global OGN network
- View your station on [live.glidernet.org](http://live.glidernet.org)

### 🔧 Telnet Access
```bash
telnet localhost 50000  # RF data stream
telnet localhost 50001  # Decoded APRS stream
```

## Access Points

| Service | Port | URL |
|---------|------|-----|
| Configuration UI | 8082 | `http://flarm2.local:8082` |
| OGN RF Monitor | 8080 | `http://flarm2.local:8080` |
| OGN Decode Status | 8081 | `http://flarm2.local:8081` |
| RF Telnet | 50000 | `telnet localhost 50000` |
| APRS Telnet | 50001 | `telnet localhost 50001` |

## Files

```
.
├── README.md                  # This file
├── INSTALLATION.md            # Complete installation guide
├── CLAUDE.md                  # Claude Code development guide
├── Template.conf              # Example configuration
└── ogn_installation_script.sh # Legacy installer (not recommended)
```

## Services Management

```bash
# OGN Receiver
sudo service rtlsdr-ogn start|stop|restart|status

# Web Configuration Interface
sudo systemctl start|stop|restart|status ogn-config-web

# View logs
tail -f /var/log/rtlsdr-ogn/50000  # RF logs
tail -f /var/log/rtlsdr-ogn/50001  # Decode logs
sudo journalctl -u ogn-config-web -f  # Web UI logs
```

## Configuration

Edit via web interface (recommended) or manually:
```bash
nano ~/ogn-pi34/rtlsdr-ogn-0.3.2/Template.conf
sudo service rtlsdr-ogn restart
```

**Required settings:**
- Station callsign (max 9 characters)
- Latitude/Longitude (decimal degrees)
- Altitude (meters MSL)
- Frequency correction (from GSM scan)
- Center frequency (868.2 EU / 915.0 US-CA)

## Calibration

Run GSM scan to determine frequency correction:
```bash
cd ~/ogn-pi34/rtlsdr-ogn-0.3.2
sudo service rtlsdr-ogn stop
./gsm_scan --gain 30
# Note the PPM correction value
# Update via web UI or Template.conf
sudo service rtlsdr-ogn start
```

## Troubleshooting

### Web UI not accessible?
```bash
# Check service status
sudo systemctl status ogn-config-web

# Check if port is listening
netstat -tuln | grep 8082

# Try IP address instead of .local
hostname -I
```

### No aircraft data?
```bash
# Check processes
ps aux | grep ogn

# Check APRS connection
telnet localhost 50001
# Look for "Connected to aprs.glidernet.org"

# Check RF reception
telnet localhost 50000
# Should show continuous RF statistics
```

### Service won't start?
```bash
# Check RTL-SDR hardware
lsusb | grep -i realtek
rtl_test -t

# Review logs
tail -50 /var/log/rtlsdr-ogn/50000
tail -50 /var/log/rtlsdr-ogn/50001
```

## System Architecture

```
RTL-SDR Dongle → ogn-rf (8080) → FIFO → ogn-decode (8081) → APRS Network
                     ↓                         ↓
                Telnet 50000             Telnet 50001

                Flask Web UI (8082) - Configuration Interface
```

## Platform Compatibility

### ✅ Recommended: Raspberry Pi OS Bookworm 32-bit
- **Pi 3B+, Pi 4, Pi 5, Zero 2W**
- Pre-compiled ARM 32-bit binaries available
- Tested and stable

### ⚠️ Debian 13 Trixie (64-bit) - Not Recommended
- Binary incompatibility (time64 ABI mismatch)
- Pre-compiled binaries will segfault
- Requires compilation from source

### Why 32-bit Works Better
The OGN project distributes pre-compiled binaries for:
- ARM 32-bit (armhf) - Debian Bullseye/Bookworm compatible
- ARM 64-bit (aarch64) - Debian Bullseye compatible only

On **Debian 13 Trixie**, the time64 ABI migration breaks binary compatibility with older compiled software. Using **32-bit Bookworm** avoids this issue entirely.

## Documentation

- **[INSTALLATION.md](INSTALLATION.md)** - Complete step-by-step guide
- **[CLAUDE.md](CLAUDE.md)** - Development and troubleshooting reference
- [OGN Wiki](http://wiki.glidernet.org) - Official documentation
- [VirusPilot/ogn-pi34](https://github.com/VirusPilot/ogn-pi34) - Installer source

## What This Repository Contains

### Configuration Files
- `Template.conf` - Example OGN receiver configuration
- Pre-configured for station HfssHq2 at 45.97316°N, 8.87516°E, 280m

### Installation Scripts
- `ogn_installation_script.sh` - Legacy manual installer
- Flask web app code (installed on Pi)

### Documentation
- Complete installation guide with architecture diagrams
- Troubleshooting procedures
- Port reference tables
- Service management commands

## Current Configuration Example

**Station:** HfssHq2
**Location:** 45.97316°N, 8.87516°E @ 280m
**Frequency:** 868.2 MHz (EU)
**Correction:** +1.0 ppm (GSM calibrated)
**Gain:** 40.0 dB
**APRS Server:** aprs.glidernet.org:14580

## Support

- GitHub Issues: Report problems here
- OGN Forum: https://groups.google.com/g/openglidernetwork
- Live Map: http://live.glidernet.org (see your station after 10-15 minutes)

## License

OGN software: Various open-source licenses (see respective projects)
This documentation: MIT License

## Acknowledgments

- [Open Glider Network Project](http://glidernet.org)
- [VirusPilot](https://github.com/VirusPilot) for ogn-pi34 installer
- RTL-SDR community
- Raspberry Pi Foundation

---

**Last Updated:** 2025-11-12
**Version:** 1.0
**Tested On:** Raspberry Pi 3B+ with Raspbian Bookworm 32-bit
