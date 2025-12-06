# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an OGN (Open Glider Network) receiver setup repository for Raspberry Pi, designed to receive FLARM aircraft tracking signals using RTL-SDR hardware. The system consists of two main components working together via a FIFO pipe:
- **ogn-rf**: Receives and demodulates RF signals from RTL-SDR dongle
- **ogn-decode**: Decodes OGN/FLARM packets and forwards to APRS network

## Architecture

The system operates as a pipeline:
1. RTL-SDR dongle captures RF signals at 868 MHz (EU) or 915 MHz (US/Canada)
2. `ogn-rf` demodulates signals and outputs to `ogn-rf.fifo`
3. `ogn-decode` reads from FIFO, decodes aircraft data, and transmits to APRS server
4. Data appears on live.glidernet.org map after 10-15 minutes

Both processes run as systemd services and communicate via named pipe.

## Key Configuration

**Template.conf** contains all receiver settings:
- `RF.FreqCorr`: Frequency correction in PPM (calibrate with gsm_scan)
- `RF.OGN.CenterFreq`: 868.2 (EU), 868.4 (alternate), 915.0 (US/Canada)
- `RF.OGN.Gain`: RF gain setting (typically 40.0)
- `Position`: Station coordinates (latitude/longitude/altitude in meters)
- `APRS.Call`: Station callsign (max 9 chars)
- `APRS.Server`: aprs.glidernet.org:14580
- `APRS.Pass`: APRS passcode from https://apps.magicbug.co.uk/passcode/
- `HTTP.Port`: Web interface port (default 8080)

## Installation

### IMPORTANT: Debian Version Compatibility

**Debian 13 (Trixie) Compatibility Issue**: Pre-compiled OGN binaries compiled for Debian Bullseye **will segfault** on Debian 13 Trixie due to time64 ABI mismatch. Trixie uses 64-bit `time_t` which causes stack corruption with older binaries.

### Recommended Installation Method (Pi 3/4/5)

**Use VirusPilot's ogn-pi34 installer** (handles all compatibility issues automatically):
```bash
sudo apt update
sudo apt full-upgrade -y
sudo apt install git -y
git clone https://github.com/VirusPilot/ogn-pi34.git
cd ogn-pi34
./install-pi34.sh
```

This installer:
- Detects Debian version and downloads compatible binaries
- Handles libjpeg compatibility (libjpeg8 → libjpeg62-turbo)
- Configures systemd services correctly
- Sets up FIFO pipes with proper permissions
- Works on Pi Zero 2W, Pi 3, Pi 4, and Pi 5 (32-bit or 64-bit)

## Production Deployment

For production IoT fleet deployment with Cloudflare Zero Trust and Tailscale VPN, see [PRODUCTION-DEPLOYMENT.md](PRODUCTION-DEPLOYMENT.md).

## Common Commands

**Calibrate frequency correction:**
```bash
cd ~/ogn
./calibrate-gsm.sh
```

**Manual start (for testing):**
```bash
cd ~/ogn
./start-ogn-rf.sh      # Start RF receiver
sleep 5                 # Wait for RF to initialize
./start-ogn-decode.sh  # Start decoder
./status-ogn.sh        # Check status
```

**Systemd management (production):**
```bash
sudo systemctl enable ogn-rf ogn-decode   # Enable auto-start
sudo systemctl start ogn-rf ogn-decode    # Start services
sudo systemctl stop ogn-rf ogn-decode     # Stop services
sudo systemctl restart ogn-rf ogn-decode  # Restart services
sudo systemctl status ogn-rf              # Check RF status
sudo systemctl status ogn-decode          # Check decoder status
```

**Stop services:**
```bash
cd ~/ogn
./stop-ogn.sh
```

**View logs:**
```bash
tail -f ~/ogn/ogn-rf.log       # Manual start logs
tail -f ~/ogn/ogn-decode.log   # Manual start logs
sudo journalctl -u ogn-rf -f   # Systemd logs
sudo journalctl -u ogn-decode -f
```

**Monitor live data:**
```bash
telnet localhost 50000  # RF demodulator output
telnet localhost 50001  # Decoded APRS packets
```

**Web interface:**
```
http://<raspberry-pi-ip>:8080
```

**Test RTL-SDR dongle:**
```bash
rtl_test -t
```

## Hardware Requirements

- Raspberry Pi (3/4/5) running 64-bit OS
- RTL-SDR dongle (RTL2832U chipset)
- Antenna tuned for 868 MHz (EU) or 915 MHz (US/Canada)

## Binary Architecture

The system uses precompiled binaries:
- **ARM64**: Downloaded from github.com/VirusPilot/ogn-pi34 (Bullseye build)
- **ARM32**: Downloaded from download.glidernet.org/arm
- Binaries installed to `/usr/local/bin/`: ogn-rf, ogn-decode, gsm_scan

## Important Files

- `/etc/systemd/system/ogn-rf.service`: RF receiver systemd unit
- `/etc/systemd/system/ogn-decode.service`: Decoder systemd unit
- `/etc/modprobe.d/blacklist-rtl-sdr.conf`: Blacklisted DVB-T modules
- `~/ogn/Template.conf`: Main configuration file
- `~/ogn/ogn-rf.fifo`: Named pipe for inter-process communication

## Troubleshooting

### Common Issues

#### 1. ogn-rf Segmentation Fault (Signal 11)
**Symptoms**: Service constantly restarts, `journalctl -u ogn-rf` shows `Main process exited, code=killed, status=11/SEGV`

**Cause**: Binary compiled for older Debian version running on Debian 13 Trixie (time64 ABI incompatibility)

**Solution**:
- Use VirusPilot's ogn-pi34 installer (see Installation section)
- OR compile from source: https://github.com/glidernet/ogn-rf
- OR downgrade to Debian 12 Bookworm

#### 2. Telnet Ports 50000/50001 Connection Refused
**Symptoms**: `telnet localhost 50000` fails with "Connection refused"

**Cause**: ogn-rf crashes before opening telnet ports

**Solution**: Fix ogn-rf segfault issue first (see above)

**Verification**:
```bash
netstat -tuln | grep -E '50000|50001'  # Check if ports are listening
ps aux | grep ogn                        # Check if processes are running
```

#### 3. ogn-decode Can't Connect to localhost:50010
**Symptoms**: `ogn-decode.log` shows "OGN_Demod... can't connect to localhost:50010"

**Cause**: ogn-rf not running or crashed before establishing connection

**Solution**: Ensure ogn-rf is stable and running, then restart ogn-decode

#### 4. libjpeg.so.8 Missing
**Symptoms**: `error while loading shared libraries: libjpeg.so.8: cannot open shared object file`

**Cause**: Debian removed libjpeg8 in favor of libjpeg62-turbo

**Solution**:
```bash
# Create symbolic link (temporary workaround)
sudo ln -s /usr/lib/aarch64-linux-gnu/libjpeg.so.62 /usr/lib/aarch64-linux-gnu/libjpeg.so.8
```
OR use VirusPilot installer which handles this automatically.

#### 5. FIFO Pipeline Issues
**Symptoms**: Data not flowing between ogn-rf and ogn-decode

**Verification**:
```bash
ls -la ~/ogn/ogn-rf.fifo  # Should show 'prw-r--r--' (named pipe)
lsof ~/ogn/ogn-rf.fifo    # Shows which processes have FIFO open
```

**Solution**: Recreate FIFO if missing or corrupted:
```bash
cd ~/ogn
rm ogn-rf.fifo
mkfifo ogn-rf.fifo
chmod 644 ogn-rf.fifo
```

### Diagnostic Commands

**Check system architecture and Debian version:**
```bash
uname -a                    # Kernel and architecture
cat /etc/os-release         # Debian version (Trixie = 13)
dpkg --print-architecture   # arm64 or armhf
```

**Check binary compatibility:**
```bash
file /usr/local/bin/ogn-rf /usr/local/bin/ogn-decode
ldd /usr/local/bin/ogn-rf   # Check library dependencies
```

**Monitor services in real-time:**
```bash
sudo journalctl -u ogn-rf -f       # Follow RF logs
sudo journalctl -u ogn-decode -f   # Follow decode logs
watch -n1 'ps aux | grep ogn'      # Watch processes
```

**Check RTL-SDR hardware:**
```bash
rtl_test -t                 # Test dongle (Ctrl+C to exit)
lsusb | grep -i realtek     # Check USB device detected
dmesg | grep -i rtl         # Check kernel messages
```

### Platform-Specific Issues

**Debian 13 (Trixie) on ARM64**:
- System: `Linux 6.12+ aarch64, Debian 13 (trixie)`
- Issue: Pre-compiled Bullseye binaries segfault due to time64 ABI mismatch
- Solution: Use ogn-pi34 installer or compile from source
- Status: Confirmed issue on hfss@hb9hcm (flarm2) system

**Raspberry Pi 5**:
- Fully supported by ogn-pi34 installer
- Use 64-bit RasPiOS for best performance
- Ensure RTL-SDR USB 2.0 compatibility

### Getting Help

If issues persist:
1. Check OGN Wiki: http://wiki.glidernet.org
2. GitHub Issues: https://github.com/glidernet/ogn-rf/issues
3. OGN Forum: https://groups.google.com/g/openglidernetwork
