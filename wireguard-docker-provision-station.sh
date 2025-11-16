#!/bin/bash
# wireguard-docker-provision-station.sh
# Provision OGN stations for Docker-based WireGuard (LinuxServer.io image)
# Run on the Docker host (vilnius)
# Usage: ./wireguard-docker-provision-station.sh <station_id> [station_name]

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <station_id> [station_name]"
    echo "Example: $0 42 ogn-zurich"
    exit 1
fi

STATION_ID=$1
STATION_NAME=${2:-"ogn-station-$STATION_ID"}
WG_DIR="$HOME/apps/wireguard_vpn"
CONFIG_DIR="$WG_DIR/config"
SERVER_CONFIG="$CONFIG_DIR/wg_confs/wg0.conf"
OUTPUT_DIR="$WG_DIR/peers"
CONTAINER_NAME="wireguard"

# Check if running on correct host
if [ ! -d "$WG_DIR" ]; then
    echo "Error: WireGuard directory $WG_DIR not found"
    echo "This script must run on the Docker host (vilnius)"
    exit 1
fi

# Check if container is running
if ! docker ps | grep -q "$CONTAINER_NAME"; then
    echo "Error: WireGuard container not running"
    echo "Start it with: cd $WG_DIR && docker-compose up -d"
    exit 1
fi

# Read server config
if [ ! -f "$SERVER_CONFIG" ]; then
    echo "Error: Server config $SERVER_CONFIG not found"
    exit 1
fi

# Extract server public key
SERVER_PRIVATE_KEY=$(grep "PrivateKey" "$SERVER_CONFIG" | head -1 | awk '{print $3}')
SERVER_PUBLIC_KEY=$(echo "$SERVER_PRIVATE_KEY" | docker exec -i "$CONTAINER_NAME" wg pubkey)

# Get server endpoint
read -p "Enter WireGuard server public endpoint [vilnius.yourdomain.com:51820]: " SERVER_ENDPOINT
if [ -z "$SERVER_ENDPOINT" ]; then
    echo "Using default: auto-detect"
    # Try to get public IP
    SERVER_ENDPOINT=$(curl -s ifconfig.me):51820
    echo "Detected endpoint: $SERVER_ENDPOINT"
fi

# Calculate IP address (10.13.13.x network, starting from .12 for OGN stations)
# First 11 IPs (.1-.11) are reserved for existing peers
STATION_IP_OFFSET=$((STATION_ID + 11))
if [ $STATION_IP_OFFSET -gt 254 ]; then
    echo "Error: Station ID too high. Max 243 stations on 10.13.13.0/24 network"
    echo "Consider expanding to 10.13.0.0/16 network for more stations"
    exit 1
fi
STATION_IP="10.13.13.$STATION_IP_OFFSET"

echo "Provisioning station $STATION_ID ($STATION_NAME)..."
echo "  IP: $STATION_IP"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Generate unique keys for this station
STATION_PRIVATE=$(docker exec "$CONTAINER_NAME" wg genkey)
STATION_PUBLIC=$(echo "$STATION_PRIVATE" | docker exec -i "$CONTAINER_NAME" wg pubkey)
PRESHARED_KEY=$(docker exec "$CONTAINER_NAME" wg genpsk)

# Generate client config for Pi
cat > "$OUTPUT_DIR/${STATION_NAME}.conf" << EOF
# WireGuard Client Config for OGN Station
# Station ID: $STATION_ID
# Station Name: $STATION_NAME
# Generated: $(date)

[Interface]
Address = $STATION_IP/24
PrivateKey = $STATION_PRIVATE
DNS = 1.1.1.1, 1.0.0.1

[Peer]
PublicKey = $SERVER_PUBLIC_KEY
PresharedKey = $PRESHARED_KEY
Endpoint = $SERVER_ENDPOINT
AllowedIPs = 10.13.13.0/24
PersistentKeepalive = 25
EOF

echo "✓ Client config created: $OUTPUT_DIR/${STATION_NAME}.conf"

# Add peer to server config (append to file)
cat >> "$SERVER_CONFIG" << EOF

[Peer]
# $STATION_NAME (Station ID: $STATION_ID) - Added $(date +%Y-%m-%d)
PublicKey = $STATION_PUBLIC
PresharedKey = $PRESHARED_KEY
AllowedIPs = $STATION_IP/32
EOF

echo "✓ Peer added to server config"

# Reload WireGuard in container without restarting
echo "Reloading WireGuard configuration..."
docker exec "$CONTAINER_NAME" wg syncconf wg0 <(docker exec "$CONTAINER_NAME" wg-quick strip wg0)

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

Transfer config to Pi:
  scp $OUTPUT_DIR/${STATION_NAME}.conf pi@<pi-ip>:~/
  ssh pi@<pi-ip> 'sudo cp ${STATION_NAME}.conf /etc/wireguard/wg0.conf'
EOF

# Display QR code for mobile scanning (optional)
if docker exec "$CONTAINER_NAME" which qrencode > /dev/null 2>&1; then
    echo ""
    echo "QR Code for mobile device:"
    docker exec "$CONTAINER_NAME" qrencode -t ansiutf8 < "$OUTPUT_DIR/${STATION_NAME}.conf"
fi

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
