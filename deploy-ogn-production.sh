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

# ===== Step 3: Install Tailscale =====
echo "3/6 Installing Tailscale..."
if ! command -v tailscale &> /dev/null; then
    curl -fsSL https://tailscale.com/install.sh | sh
    echo "   Tailscale installed"
else
    echo "   Tailscale already installed"
fi

# ===== Step 4: Connect to Tailscale =====
echo "4/6 Connecting to Tailscale network..."
sudo tailscale up --authkey="$TS_AUTHKEY" --hostname="ogn-$SERIAL"
TAILSCALE_IP=$(tailscale ip -4 2>/dev/null || echo "pending")
echo "   Connected with IP: $TAILSCALE_IP"

# ===== Step 5: Update OGN software =====
echo "5/6 Updating OGN software..."
git pull || echo "   Git pull skipped (not a git repo or no updates)"
sudo pkill -f ogn-config-web-alpium.py || true
sleep 2
nohup sudo python3 ogn-config-web-alpium.py > /var/log/ogn-config-web.log 2>&1 &
echo "   OGN software updated and running"

# ===== Step 6: Verify deployment =====
echo "6/6 Verifying deployment..."
sleep 5

# Check Tailscale
if tailscale status 2>/dev/null | grep -q "$SERIAL"; then
    echo "   Tailscale: CONNECTED"
else
    echo "   Tailscale: PENDING (may take a moment)"
fi

# Check OGN service
if pgrep -f ogn-config-web-alpium.py > /dev/null; then
    echo "   OGN Config Service: RUNNING"
else
    echo "   OGN Config Service: NOT RUNNING"
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
