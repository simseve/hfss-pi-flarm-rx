#!/bin/bash
# wireguard-provision-station.sh
# Run on your WireGuard server to generate config for a new OGN station
# Usage: ./wireguard-provision-station.sh <station_id> [station_name]

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <station_id> [station_name]"
    echo "Example: $0 42 ogn-zurich"
    exit 1
fi

STATION_ID=$1
STATION_NAME=${2:-"ogn-station-$STATION_ID"}
WG_CONFIG_DIR="/etc/wireguard"
OUTPUT_DIR="./station-configs"
SERVER_CONFIG="$WG_CONFIG_DIR/wg0.conf"

# Check if server config exists
if [ ! -f "$SERVER_CONFIG" ]; then
    echo "Error: Server config $SERVER_CONFIG not found"
    exit 1
fi

# Read server public key
SERVER_PUBLIC_KEY=$(grep PrivateKey $SERVER_CONFIG | awk '{print $3}' | wg pubkey)
if [ -z "$SERVER_PUBLIC_KEY" ]; then
    echo "Error: Could not extract server public key"
    exit 1
fi

# Get server endpoint (you may need to adjust this)
read -p "Enter your WireGuard server public endpoint [IP:port]: " SERVER_ENDPOINT
if [ -z "$SERVER_ENDPOINT" ]; then
    echo "Error: Server endpoint required"
    exit 1
fi

# Calculate IP address (supports up to 65534 stations: 10.0.0.2 - 10.0.255.254)
OCTET3=$((STATION_ID / 254))
OCTET4=$(((STATION_ID % 254) + 2))
STATION_IP="10.0.$OCTET3.$OCTET4"

echo "Provisioning station $STATION_ID ($STATION_NAME)..."
echo "  IP: $STATION_IP"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Generate unique keys for this station
STATION_PRIVATE=$(wg genkey)
STATION_PUBLIC=$(echo "$STATION_PRIVATE" | wg pubkey)

# Generate client config for Pi
cat > "$OUTPUT_DIR/${STATION_NAME}.conf" << EOF
# WireGuard Client Config for OGN Station
# Station ID: $STATION_ID
# Station Name: $STATION_NAME
# Generated: $(date)

[Interface]
Address = $STATION_IP/16
PrivateKey = $STATION_PRIVATE
DNS = 1.1.1.1, 1.0.0.1

[Peer]
PublicKey = $SERVER_PUBLIC_KEY
Endpoint = $SERVER_ENDPOINT
AllowedIPs = 10.0.0.0/16
PersistentKeepalive = 25
EOF

echo "✓ Client config created: $OUTPUT_DIR/${STATION_NAME}.conf"

# Add peer to server config
echo "" >> "$SERVER_CONFIG"
cat >> "$SERVER_CONFIG" << EOF
# OGN Station $STATION_ID - $STATION_NAME - Added $(date)
[Peer]
PublicKey = $STATION_PUBLIC
AllowedIPs = $STATION_IP/32
EOF

echo "✓ Peer added to server config"

# Reload WireGuard without interrupting existing connections
wg syncconf wg0 <(wg-quick strip wg0)
echo "✓ WireGuard config reloaded"

# Create station info file
cat > "$OUTPUT_DIR/${STATION_NAME}.info" << EOF
Station ID: $STATION_ID
Station Name: $STATION_NAME
IP Address: $STATION_IP
Public Key: $STATION_PUBLIC
Config File: ${STATION_NAME}.conf
Created: $(date)

Access via SSH: ssh hfss@$STATION_IP
Access OGN UI: http://$STATION_IP:8080
EOF

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Station provisioned successfully!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Config file: $OUTPUT_DIR/${STATION_NAME}.conf"
echo "Info file: $OUTPUT_DIR/${STATION_NAME}.info"
echo ""
echo "Next steps:"
echo "1. Copy $OUTPUT_DIR/${STATION_NAME}.conf to the Pi"
echo "2. Run the client installation script on the Pi"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
