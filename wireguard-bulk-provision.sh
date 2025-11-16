#!/bin/bash
# wireguard-bulk-provision.sh
# Run on WireGuard server to provision multiple OGN stations at once
# Usage: ./wireguard-bulk-provision.sh <start_id> <end_id> [name_prefix]

set -e

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Usage: $0 <start_id> <end_id> [name_prefix]"
    echo "Example: $0 1 100 ogn-europe"
    echo "         $0 101 200 ogn-usa"
    exit 1
fi

START_ID=$1
END_ID=$2
NAME_PREFIX=${3:-"ogn-station"}

if [ ! -f "./wireguard-provision-station.sh" ]; then
    echo "Error: wireguard-provision-station.sh not found in current directory"
    exit 1
fi

if [ "$EUID" -ne 0 ]; then
    echo "Error: Please run as root (sudo)"
    exit 1
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "OGN Fleet Bulk Provisioning"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Range: $START_ID - $END_ID"
echo "Prefix: $NAME_PREFIX"
echo "Total stations: $((END_ID - START_ID + 1))"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

# Get server endpoint once
read -p "Enter your WireGuard server public endpoint [IP:port]: " SERVER_ENDPOINT
if [ -z "$SERVER_ENDPOINT" ]; then
    echo "Error: Server endpoint required"
    exit 1
fi

# Export for child script to use
export SERVER_ENDPOINT

WG_CONFIG_DIR="/etc/wireguard"
OUTPUT_DIR="./station-configs"
SERVER_CONFIG="$WG_CONFIG_DIR/wg0.conf"
SERVER_PUBLIC_KEY=$(grep PrivateKey $SERVER_CONFIG | awk '{print $3}' | wg pubkey)

mkdir -p "$OUTPUT_DIR"

echo ""
echo "Provisioning stations..."
echo ""

SUCCESS_COUNT=0
FAIL_COUNT=0

for i in $(seq $START_ID $END_ID); do
    STATION_NAME="${NAME_PREFIX}-$(printf "%04d" $i)"

    # Calculate IP
    OCTET3=$((i / 254))
    OCTET4=$(((i % 254) + 2))
    STATION_IP="10.0.$OCTET3.$OCTET4"

    echo -n "[$i/$END_ID] $STATION_NAME ($STATION_IP)... "

    # Generate keys
    STATION_PRIVATE=$(wg genkey)
    STATION_PUBLIC=$(echo "$STATION_PRIVATE" | wg pubkey)

    # Generate client config
    cat > "$OUTPUT_DIR/${STATION_NAME}.conf" << EOF
# WireGuard Client Config for OGN Station
# Station ID: $i
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

    # Add peer to server config
    cat >> "$SERVER_CONFIG" << EOF

# OGN Station $i - $STATION_NAME - Added $(date)
[Peer]
PublicKey = $STATION_PUBLIC
AllowedIPs = $STATION_IP/32
EOF

    # Create info file
    cat > "$OUTPUT_DIR/${STATION_NAME}.info" << EOF
Station ID: $i
Station Name: $STATION_NAME
IP Address: $STATION_IP
Public Key: $STATION_PUBLIC
Config File: ${STATION_NAME}.conf
Created: $(date)

Access: ssh hfss@$STATION_IP
Web UI: http://$STATION_IP:8080
EOF

    echo "✓"
    SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
done

echo ""
echo "Reloading WireGuard server configuration..."
wg syncconf wg0 <(wg-quick strip wg0)

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Bulk Provisioning Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Successful: $SUCCESS_COUNT"
echo "Failed: $FAIL_COUNT"
echo ""
echo "Config files: $OUTPUT_DIR/*.conf"
echo "Info files: $OUTPUT_DIR/*.info"
echo ""
echo "Next steps:"
echo "1. Copy individual .conf files to each Pi"
echo "2. Run wireguard-client-setup.sh on each Pi"
echo ""
echo "Or create SD card image with config pre-installed"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
