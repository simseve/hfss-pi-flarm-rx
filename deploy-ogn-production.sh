#!/bin/bash
# Production deployment script for OGN Raspberry Pi with Cloudflare + Tailscale
# Fetches credentials securely from Alpium API

set -e

echo "=== OGN Production Deployment ==="
echo ""

# Get device serial
SERIAL=$(cat /proc/cpuinfo | grep Serial | awk '{print $3}' | tail -c 9)
echo "Device Serial: $SERIAL"
echo ""

cd ~/hfss-pi-flarm-rx

# ===== Step 1: Fetch credentials from Alpium =====
echo "1/6 Fetching credentials from Alpium..."

# Check if .env already exists
if [ -f .env ]; then
    echo "   .env already exists. Overwrite? (y/N): "
    read -r OVERWRITE
    if [ "$OVERWRITE" != "y" ] && [ "$OVERWRITE" != "Y" ]; then
        echo "   Keeping existing .env"
        source .env
    else
        rm .env
    fi
fi

# Fetch from API if .env doesn't exist
if [ ! -f .env ]; then
    echo ""
    echo "   Enter the provisioning passphrase (ask Alpium admin):"
    read -s -p "   Passphrase: " PASSPHRASE
    echo ""

    # Fetch credentials
    HTTP_CODE=$(curl -s -w "%{http_code}" -o .env.tmp \
        -H "X-Provision-Key: $PASSPHRASE" \
        https://ogn.alpium.io/api/v1/provision/ogn)

    if [ "$HTTP_CODE" = "200" ]; then
        mv .env.tmp .env
        chmod 600 .env
        echo "   Credentials fetched successfully"
    elif [ "$HTTP_CODE" = "401" ]; then
        rm -f .env.tmp
        echo "   Error: Invalid passphrase"
        exit 1
    else
        rm -f .env.tmp
        echo "   Error: Failed to fetch credentials (HTTP $HTTP_CODE)"
        exit 1
    fi
fi

# Load the credentials
source .env
echo "   Environment configured"

# ===== Step 2: Deploy SSH key =====
echo "2/6 Deploying SSH key..."
if [ -n "$SSH_PUBLIC_KEY_OGN" ]; then
    mkdir -p ~/.ssh
    chmod 700 ~/.ssh
    if ! grep -q "$(echo $SSH_PUBLIC_KEY_OGN | awk '{print $2}')" ~/.ssh/authorized_keys 2>/dev/null; then
        echo "$SSH_PUBLIC_KEY_OGN" >> ~/.ssh/authorized_keys
        chmod 600 ~/.ssh/authorized_keys
        echo "   SSH key deployed"
    else
        echo "   SSH key already deployed"
    fi
else
    echo "   Skipped (no SSH key provided)"
fi

# ===== Step 3: Install OGN Receiver =====
echo "3/7 Installing OGN receiver software..."
if [ ! -d "$HOME/ogn-pi34" ]; then
    cd ~
    git clone https://github.com/VirusPilot/ogn-pi34.git
    cd ogn-pi34
    ./install-pi34.sh
    echo "   OGN receiver installed"
else
    echo "   OGN receiver already installed"
fi
cd ~/hfss-pi-flarm-rx

# ===== Step 4: Install Tailscale =====
echo "4/7 Installing Tailscale..."
if ! command -v tailscale &> /dev/null; then
    curl -fsSL https://tailscale.com/install.sh | sh
    echo "   Tailscale installed"
else
    echo "   Tailscale already installed"
fi

# ===== Step 5: Connect to Tailscale =====
echo "5/7 Connecting to Tailscale network..."
sudo tailscale up --authkey="$TS_AUTHKEY" --hostname="ogn-$SERIAL"
TAILSCALE_IP=$(tailscale ip -4 2>/dev/null || echo "pending")
echo "   Connected with IP: $TAILSCALE_IP"

# ===== Step 6: Start OGN Config Web Service =====
echo "6/7 Starting OGN config web service..."
git pull || echo "   Git pull skipped (not a git repo or no updates)"
sudo pkill -f ogn-config-web-alpium.py || true
sleep 2
nohup sudo python3 ogn-config-web-alpium.py > /var/log/ogn-config-web.log 2>&1 &
echo "   OGN config web service started"

# ===== Step 7: Verify deployment =====
echo "7/7 Verifying deployment..."
sleep 5

# Check Tailscale
if tailscale status 2>/dev/null | grep -q "$SERIAL"; then
    echo "   Tailscale: CONNECTED"
else
    echo "   Tailscale: PENDING (may take a moment)"
fi

# Check OGN services
if pgrep -f ogn-config-web-alpium.py > /dev/null; then
    echo "   OGN Config Web: RUNNING"
else
    echo "   OGN Config Web: NOT RUNNING"
fi

OGN_RF_RUNNING=false
OGN_DECODE_RUNNING=false

if systemctl is-active --quiet ogn-rf 2>/dev/null; then
    echo "   OGN RF Receiver: RUNNING"
    OGN_RF_RUNNING=true
else
    echo "   OGN RF Receiver: NOT RUNNING"
fi

if systemctl is-active --quiet ogn-decode 2>/dev/null; then
    echo "   OGN Decoder: RUNNING"
    OGN_DECODE_RUNNING=true
else
    echo "   OGN Decoder: NOT RUNNING"
fi

# Get final Tailscale IP
TAILSCALE_IP=$(tailscale ip -4 2>/dev/null || echo "pending")

echo ""
echo "=== Deployment Complete! ==="
echo ""
echo "Device Serial: $SERIAL"
echo "Tailscale IP: $TAILSCALE_IP"
if [ "$TAILSCALE_IP" != "pending" ]; then
    echo "Web Interface: http://$TAILSCALE_IP:8082"
    echo "OGN Status: http://$TAILSCALE_IP:8080"
fi
echo ""
echo "View device in Tailscale dashboard:"
echo "https://login.tailscale.com/admin/machines"
echo ""
echo "Heartbeats will be sent to: $SERVER_URL/gps/"

# Check if OGN services need configuration
if [ "$OGN_RF_RUNNING" = false ] || [ "$OGN_DECODE_RUNNING" = false ]; then
    echo ""
    echo "=== ACTION REQUIRED ==="
    echo "OGN receiver services are not running."
    echo ""
    echo "Please configure your station via the web interface:"
    echo "  1. Open http://$TAILSCALE_IP:8082"
    echo "  2. Set your station callsign, location, and RF settings"
    echo "  3. Click 'Save & Restart' to start the OGN services"
    echo ""
    echo "After configuration, verify services with:"
    echo "  sudo systemctl status ogn-rf ogn-decode"
fi
