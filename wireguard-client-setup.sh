#!/bin/bash
# wireguard-client-setup.sh
# Run on each OGN Raspberry Pi to install and configure WireGuard
# Usage:
#   1. Copy this script and the station .conf file to the Pi
#   2. ./wireguard-client-setup.sh <path-to-station-config.conf>

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <station-config.conf>"
    echo "Example: $0 ogn-station-42.conf"
    exit 1
fi

CONFIG_FILE=$1

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: Config file $CONFIG_FILE not found"
    exit 1
fi

if [ "$EUID" -ne 0 ]; then
    echo "Error: Please run as root (sudo)"
    exit 1
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "OGN Station WireGuard Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Install WireGuard
echo "[1/5] Installing WireGuard..."
apt update -qq
apt install -y wireguard resolvconf

# Copy config
echo "[2/5] Installing configuration..."
cp "$CONFIG_FILE" /etc/wireguard/wg0.conf
chmod 600 /etc/wireguard/wg0.conf

# Extract station IP from config for display
STATION_IP=$(grep "Address" /etc/wireguard/wg0.conf | awk '{print $3}' | cut -d'/' -f1)

# Enable and start WireGuard
echo "[3/5] Enabling WireGuard service..."
systemctl enable wg-quick@wg0

echo "[4/5] Starting WireGuard..."
systemctl start wg-quick@wg0

# Wait for connection
echo "[5/5] Testing connection..."
sleep 3

if systemctl is-active --quiet wg-quick@wg0; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "✓ WireGuard installed and running!"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Station VPN IP: $STATION_IP"
    echo ""
    echo "Test connection:"
    echo "  ping 10.0.0.1  # Ping WireGuard server"
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
