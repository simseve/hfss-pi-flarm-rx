#!/bin/bash
# ogn-autoprovision.sh
# Auto-provision OGN station with Alpium VPN server
# Run on the OGN Raspberry Pi after registration
# Usage: sudo ./ogn-autoprovision.sh

set -e

ALPIUM_SERVER="alpium@alpium"
ALPIUM_WG_DIR="~/alpium/wireguard"
OGN_CREDS_FILE="/home/hfss/.ogn_credentials.json"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "⚡ Alpium OGN Station Auto-Provisioning"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ "$EUID" -ne 0 ]; then
    echo "Error: Please run as root (sudo)"
    exit 1
fi

# Check if already registered
if [ ! -f "$OGN_CREDS_FILE" ]; then
    echo "Error: OGN station not registered with Alpium"
    echo "Please register first at http://$(hostname -I | awk '{print $1}'):8082"
    exit 1
fi

# Extract device ID and derive station ID
DEVICE_ID=$(jq -r '.device_id' "$OGN_CREDS_FILE" 2>/dev/null || echo "")
if [ -z "$DEVICE_ID" ]; then
    echo "Error: Cannot read device_id from $OGN_CREDS_FILE"
    exit 1
fi

echo "✓ Station registered: $DEVICE_ID"

# Derive numeric station ID from device ID hash
STATION_ID_HASH=$(echo "$DEVICE_ID" | sed 's/OGN_STATION_//' | head -c 8)
# Convert hex to decimal and map to 1-243 range (avoiding peer1-peer10)
STATION_ID=$(printf "%d" 0x$STATION_ID_HASH 2>/dev/null || echo "1")
STATION_ID=$((STATION_ID % 233 + 12))  # Range: 12-244 (avoids .1-.11)

STATION_NAME="ogn-$(hostname)"
echo "Station Name: $STATION_NAME"
echo "Station ID: $STATION_ID"
echo "VPN IP will be: 10.13.13.$STATION_ID"
echo ""

# Install dependencies
echo "[1/5] Installing dependencies..."
if ! command -v wg &> /dev/null; then
    apt update -qq
    apt install -y wireguard resolvconf jq curl openssh-client
else
    echo "✓ WireGuard already installed"
fi

# Request provisioning from Alpium server via SSH
echo "[2/5] Requesting VPN provisioning from Alpium server..."
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# Check SSH connectivity
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes $ALPIUM_SERVER "echo Connected" >/dev/null 2>&1; then
    echo "Error: Cannot connect to $ALPIUM_SERVER"
    echo "Please set up SSH key authentication first:"
    echo "  ssh-copy-id $ALPIUM_SERVER"
    exit 1
fi

# Run provisioning script on Alpium server
ssh $ALPIUM_SERVER bash << 'EOF'
set -e

STATION_ID='$STATION_ID'
STATION_NAME="$STATION_NAME"
WG_DIR="$HOME/alpium/wireguard"
CONFIG_DIR="$WG_DIR/config"
SERVER_CONFIG="$CONFIG_DIR/wg_confs/wg0.conf"
OUTPUT_DIR="$WG_DIR/peers"
CONTAINER_NAME="alpium-wireguard"

# Check if already provisioned
if grep -q "# $STATION_NAME" "$SERVER_CONFIG" 2>/dev/null; then
    echo "✓ Station $STATION_NAME already provisioned" >&2
    cat "$OUTPUT_DIR/${STATION_NAME}.conf"
    exit 0
fi

echo "Provisioning new station $STATION_NAME (ID: $STATION_ID)..." >&2

# Get server public key
SERVER_PRIVATE_KEY=$(grep "PrivateKey" "$SERVER_CONFIG" | head -1 | awk '{print $3}')
SERVER_PUBLIC_KEY=$(echo "$SERVER_PRIVATE_KEY" | docker exec -i "$CONTAINER_NAME" wg pubkey)
SERVER_ENDPOINT=$(curl -s ifconfig.me):51820

# Station IP
STATION_IP="10.13.13.$STATION_ID"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Generate keys
STATION_PRIVATE=$(docker exec "$CONTAINER_NAME" wg genkey)
STATION_PUBLIC=$(echo "$STATION_PRIVATE" | docker exec -i "$CONTAINER_NAME" wg pubkey)
PRESHARED_KEY=$(docker exec "$CONTAINER_NAME" wg genpsk)

# Generate client config
cat > "$OUTPUT_DIR/${STATION_NAME}.conf" << EOFCONF
# WireGuard Client Config for Alpium OGN Station
# Station ID: $STATION_ID
# Station Name: $STATION_NAME
# Generated: $(date)

[Interface]
Address = $STATION_IP/24
PrivateKey = $STATION_PRIVATE
DNS = 10.13.13.1

[Peer]
PublicKey = $SERVER_PUBLIC_KEY
PresharedKey = $PRESHARED_KEY
Endpoint = $SERVER_ENDPOINT
AllowedIPs = 10.13.13.0/24
PersistentKeepalive = 25
EOFCONF

# Add peer to server config
cat >> "$SERVER_CONFIG" << EOFCONF

[Peer]
# $STATION_NAME (Station ID: $STATION_ID) - Added $(date +%Y-%m-%d)
PublicKey = $STATION_PUBLIC
PresharedKey = $PRESHARED_KEY
AllowedIPs = $STATION_IP/32
EOFCONF

# Reload WireGuard
docker exec "$CONTAINER_NAME" wg syncconf wg0 <(docker exec "$CONTAINER_NAME" wg-quick strip wg0) >/dev/null 2>&1

echo "✓ Provisioned successfully" >&2
cat "$OUTPUT_DIR/${STATION_NAME}.conf"
EOF

# Capture config (with variable expansion)
ssh $ALPIUM_SERVER "cat ~/alpium/wireguard/peers/${STATION_NAME}.conf" > "$TEMP_DIR/wg0.conf"

if [ ! -s "$TEMP_DIR/wg0.conf" ]; then
    echo "Error: Failed to provision VPN configuration"
    exit 1
fi

echo "✓ VPN configuration received"

# Install configuration
echo "[3/5] Installing VPN configuration..."
cp "$TEMP_DIR/wg0.conf" /etc/wireguard/wg0.conf
chmod 600 /etc/wireguard/wg0.conf

STATION_IP=$(grep "Address" /etc/wireguard/wg0.conf | awk '{print $3}' | cut -d'/' -f1)

# Enable and start WireGuard
echo "[4/5] Enabling WireGuard service..."
systemctl enable wg-quick@wg0 >/dev/null 2>&1
systemctl restart wg-quick@wg0

# Test connection
echo "[5/5] Testing VPN connection..."
sleep 3

if systemctl is-active --quiet wg-quick@wg0; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "✓ OGN Station Auto-Provisioned Successfully!"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Station Name: $STATION_NAME"
    echo "Station ID: $STATION_ID"
    echo "VPN IP: $STATION_IP"
    echo ""
    echo "Test VPN connection:"
    echo "  ping 10.13.13.1  # Ping Alpium VPN server"
    echo ""
    echo "Status commands:"
    echo "  sudo wg show                    # Show WireGuard status"
    echo "  sudo systemctl status wg-quick@wg0"
    echo "  sudo journalctl -u wg-quick@wg0 -f"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
else
    echo ""
    echo "✗ WireGuard failed to start"
    echo "Check logs: sudo journalctl -u wg-quick@wg0 -n 50"
    exit 1
fi
