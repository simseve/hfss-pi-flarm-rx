#!/bin/bash

# Complete OGN Receiver Setup Script for Raspberry Pi 64-bit with RTL-SDR 2832
# Downloads ARM64 precompiled binaries and sets up everything to work out of the box

set -e

echo "================================================"
echo "OGN Receiver Complete Setup for Raspberry Pi"
echo "================================================"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run with sudo: sudo ./ogn_install_complete.sh"
    exit 1
fi

# Get current user
CURRENT_USER=${SUDO_USER:-$USER}
USER_HOME=$(eval echo ~$CURRENT_USER)

echo "Installing as user: $CURRENT_USER"
echo "Home directory: $USER_HOME"
echo ""

# Detect architecture
ARCH=$(uname -m)
echo "Detected architecture: $ARCH"

if [ "$ARCH" != "aarch64" ] && [ "$ARCH" != "armv7l" ]; then
    echo "Warning: This script is designed for ARM architecture (aarch64 or armv7l)"
    echo "Your architecture is: $ARCH"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Update system
echo "[1/6] Updating system packages..."
apt-get update
apt-get upgrade -y

# Install dependencies
echo "[2/6] Installing dependencies..."
apt-get install -y \
    git \
    cmake \
    build-essential \
    libusb-1.0-0-dev \
    pkg-config \
    libfftw3-dev \
    libconfig++-dev \
    libjpeg-dev \
    telnet \
    procserv \
    wget

# Install RTL-SDR drivers
echo "[3/6] Installing RTL-SDR drivers..."
cd /tmp
rm -rf rtl-sdr
git clone https://github.com/osmocom/rtl-sdr.git
cd rtl-sdr
mkdir build
cd build
cmake ../ -DINSTALL_UDEV_RULES=ON -DDETACH_KERNEL_DRIVER=ON
make
make install
ldconfig

# Blacklist DVB-T drivers
echo "[4/6] Blacklisting DVB-T drivers..."
cat > /etc/modprobe.d/blacklist-rtl-sdr.conf << EOF
blacklist dvb_usb_rtl28xxu
blacklist rtl2832
blacklist rtl2830
blacklist r820t
blacklist e4000
EOF

# Unload modules if loaded
rmmod dvb_usb_rtl28xxu 2>/dev/null || true
rmmod rtl2832 2>/dev/null || true
rmmod rtl2830 2>/dev/null || true

# Download and install OGN binaries based on architecture
echo "[5/6] Downloading OGN precompiled binaries for $ARCH..."
cd /tmp
rm -rf rtlsdr-ogn-bin-*.tgz rtlsdr-ogn-0.3.2

if [ "$ARCH" = "aarch64" ]; then
    echo "Downloading ARM64 binaries..."
    wget https://github.com/VirusPilot/ogn-pi34/raw/master/rtlsdr-ogn-bin-arm64-0.3.2_Bullseye.tgz
    tar xvzf rtlsdr-ogn-bin-arm64-0.3.2_Bullseye.tgz
else
    echo "Downloading ARM32 binaries..."
    wget http://download.glidernet.org/arm/rtlsdr-ogn-bin-ARM-latest.tgz
    tar xvzf rtlsdr-ogn-bin-ARM-latest.tgz
fi

cd rtlsdr-ogn-0.3.2

# Verify binaries exist
if [ ! -f ogn-rf ] || [ ! -f ogn-decode ]; then
    echo "Error: OGN binaries not found after extraction!"
    exit 1
fi

# Copy binaries
echo "Installing OGN binaries..."
cp ogn-rf ogn-decode gsm_scan /usr/local/bin/
chmod +x /usr/local/bin/ogn-rf /usr/local/bin/ogn-decode /usr/local/bin/gsm_scan

# Verify installation
echo "Verifying binary architecture..."
file /usr/local/bin/ogn-rf
echo ""

# Create OGN working directory
echo "[6/6] Creating OGN working directory and configuration..."
OGN_DIR="$USER_HOME/ogn"
mkdir -p "$OGN_DIR"
cd "$OGN_DIR"

# Create FIFO for communication between ogn-rf and ogn-decode
mkfifo ogn-rf.fifo

# Create configuration file
cat > Template.conf << 'EOF'
RF:
{
  FreqCorr = 0;           # Frequency correction in PPM (use gsm_scan to calibrate)
  GSM: { CenterFreq = 950.0; Gain = 30.0; };
  OGN: { CenterFreq = 868.2; Gain = 40.0; };  # 868.2 for EU, 868.4 alternate, 915.0 for USA/Canada
};

Position:
{
  Latitude   =  0.0;      # YOUR STATION LATITUDE - CHANGE THIS!
  Longitude  =  0.0;      # YOUR STATION LONGITUDE - CHANGE THIS!
  Altitude   =  0;        # YOUR STATION ALTITUDE in meters - CHANGE THIS!
};

APRS:
{
  Call = "NOCALL";        # YOUR CALLSIGN - CHANGE THIS!
  Server = "aprs.glidernet.org";
  Port = 14580;
  Pass = "-1";            # YOUR APRS PASSCODE - CHANGE THIS! (get from https://apps.magicbug.co.uk/passcode/)
};

HTTP:
{
  Port = 8080;            # Web interface port for ogn-rf status
};
EOF

# Create GSM calibration helper script
cat > calibrate-gsm.sh << 'EOF'
#!/bin/bash
echo "=== OGN Frequency Calibration Using GSM ==="
echo ""
echo "This will scan for GSM signals to determine frequency correction (PPM)"
echo ""
echo "Common GSM frequencies by region:"
echo "  Europe: 935-960 MHz (try 947.6, 950.0, 952.4, 955.0)"
echo "  USA: 869-894 MHz"
echo ""
read -p "Enter GSM frequency to scan (MHz) [950.0]: " GSM_FREQ
GSM_FREQ=${GSM_FREQ:-950.0}

echo ""
echo "Running GSM scan on ${GSM_FREQ} MHz..."
echo "This will take about 10 seconds..."
echo ""

gsm_scan -f $GSM_FREQ -g 30

echo ""
echo "Look for the 'Freq. error' value in Hz"
echo "Calculate PPM: PPM = (Frequency_Error_Hz / Center_Freq_Hz) * 1000000"
echo ""
echo "Example: If error is -12000 Hz at 950 MHz:"
echo "  PPM = (-12000 / 950000000) * 1000000 = -12.6 PPM"
echo ""
echo "Update Template.conf with: FreqCorr = -12.6;"
EOF

# Create startup scripts
cat > start-ogn-rf.sh << 'EOF'
#!/bin/bash
cd ~/ogn
/usr/local/bin/ogn-rf Template.conf > ogn-rf.log 2>&1 &
echo "OGN-RF started. PID: $!"
echo "Monitor with: telnet localhost 50000"
echo "Web interface: http://$(hostname -I | awk '{print $1}'):8080"
EOF

cat > start-ogn-decode.sh << 'EOF'
#!/bin/bash
cd ~/ogn
/usr/local/bin/ogn-decode Template.conf > ogn-decode.log 2>&1 &
echo "OGN-Decode started. PID: $!"
echo "Monitor with: telnet localhost 50001"
EOF

cat > stop-ogn.sh << 'EOF'
#!/bin/bash
pkill ogn-rf
pkill ogn-decode
echo "OGN services stopped"
EOF

cat > status-ogn.sh << 'EOF'
#!/bin/bash
echo "=== OGN Process Status ==="
ps aux | grep -E 'ogn-rf|ogn-decode' | grep -v grep
echo ""
echo "=== Recent OGN-RF Log ==="
tail -20 ~/ogn/ogn-rf.log 2>/dev/null || echo "No log file yet"
echo ""
echo "=== Recent OGN-Decode Log ==="
tail -20 ~/ogn/ogn-decode.log 2>/dev/null || echo "No log file yet"
echo ""
echo "Monitor RF data: telnet localhost 50000"
echo "Monitor decoded data: telnet localhost 50001"
echo "Web interface: http://$(hostname -I | awk '{print $1}'):8080"
EOF

chmod +x calibrate-gsm.sh start-ogn-rf.sh start-ogn-decode.sh stop-ogn.sh status-ogn.sh

# Create systemd service for ogn-rf
cat > /etc/systemd/system/ogn-rf.service << EOF
[Unit]
Description=OGN RF Receiver
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$OGN_DIR
ExecStart=/usr/local/bin/ogn-rf $OGN_DIR/Template.conf
Restart=always
RestartSec=10
StandardOutput=append:$OGN_DIR/ogn-rf.log
StandardError=append:$OGN_DIR/ogn-rf.log

[Install]
WantedBy=multi-user.target
EOF

# Create systemd service for ogn-decode
cat > /etc/systemd/system/ogn-decode.service << EOF
[Unit]
Description=OGN Decoder
After=network.target ogn-rf.service
Requires=ogn-rf.service

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$OGN_DIR
ExecStart=/usr/local/bin/ogn-decode $OGN_DIR/Template.conf
Restart=always
RestartSec=10
StandardOutput=append:$OGN_DIR/ogn-decode.log
StandardError=append:$OGN_DIR/ogn-decode.log

[Install]
WantedBy=multi-user.target
EOF

# Set proper ownership
chown -R $CURRENT_USER:$CURRENT_USER "$OGN_DIR"

# Reload systemd
systemctl daemon-reload

echo ""
echo "================================================"
echo "Installation Complete!"
echo "================================================"
echo ""
echo "Working directory: $OGN_DIR"
echo ""
echo "⚠️  IMPORTANT: Configure before starting!"
echo ""
echo "Step 1: Calibrate frequency (optional but recommended)"
echo "  cd $OGN_DIR"
echo "  ./calibrate-gsm.sh"
echo ""
echo "Step 2: Edit configuration"
echo "  nano $OGN_DIR/Template.conf"
echo ""
echo "  Required changes:"
echo "  - Latitude, Longitude, Altitude (your station location)"
echo "  - Call (your amateur radio callsign)"
echo "  - Pass (your APRS passcode from https://apps.magicbug.co.uk/passcode/)"
echo "  - FreqCorr (PPM correction from GSM calibration, or start with 0)"
echo "  - OGN CenterFreq (868.2 EU, 868.4 alternate, 915.0 USA/Canada)"
echo ""
echo "Step 3: Start services"
echo "  Manual (for testing):"
echo "    cd $OGN_DIR"
echo "    ./start-ogn-rf.sh"
echo "    sleep 5"
echo "    ./start-ogn-decode.sh"
echo "    ./status-ogn.sh"
echo ""
echo "  OR systemd (auto-start on boot):"
echo "    sudo systemctl enable ogn-rf ogn-decode"
echo "    sudo systemctl start ogn-rf ogn-decode"
echo ""
echo "Step 4: Monitor your receiver"
echo "  telnet localhost 50000  # RF data"
echo "  telnet localhost 50001  # Decoded APRS data"
echo "  http://$(hostname -I | awk '{print $1}'):8080  # Web interface"
echo ""
echo "Step 5: Manage services"
echo "  cd $OGN_DIR && ./stop-ogn.sh"
echo "  cd $OGN_DIR && ./status-ogn.sh"
echo "  sudo systemctl status ogn-rf ogn-decode"
echo "  sudo systemctl restart ogn-rf ogn-decode"
echo ""
echo "Step 6: View logs"
echo "  tail -f $OGN_DIR/ogn-rf.log"
echo "  tail -f $OGN_DIR/ogn-decode.log"
echo "  sudo journalctl -u ogn-rf -f"
echo "  sudo journalctl -u ogn-decode -f"
echo ""
echo "Your station will appear on http://live.glidernet.org/ after 10-15 minutes"
echo ""
echo "Test RTL-SDR dongle: rtl_test -t"
echo ""
