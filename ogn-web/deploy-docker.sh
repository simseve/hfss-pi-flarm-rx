#!/bin/bash
#
# Simple Docker deployment script for flarm2.local
# Run this script on the Raspberry Pi after Docker is installed
#

set -e

echo "========================================="
echo "OGN Web Docker Deployment"
echo "========================================="

cd /home/hfss/ogn-web

# Create credentials directory
echo "[1/5] Setting up directories..."
mkdir -p credentials
chmod 700 credentials
echo "✓ Directories created"

# Stop and remove old services
echo "[2/5] Cleaning up old services..."
sudo systemctl stop ogn-config-web 2>/dev/null || true
sudo systemctl disable ogn-config-web 2>/dev/null || true
sudo systemctl stop ogn-web 2>/dev/null || true
sudo systemctl disable ogn-web 2>/dev/null || true
sudo rm -f /etc/systemd/system/ogn-config-web.service 2>/dev/null || true
sudo rm -f /etc/systemd/system/ogn-web.service 2>/dev/null || true
sudo systemctl daemon-reload
rm -f /home/hfss/ogn-config-web.py
echo "✓ Old services removed"

# Build Docker image
echo "[3/5] Building Docker image (this may take 5-10 minutes)..."
docker compose build
echo "✓ Image built"

# Start container
echo "[4/5] Starting container..."
docker compose up -d
echo "✓ Container started"

# Show status
echo "[5/5] Checking status..."
sleep 2
docker compose ps
echo ""
docker compose logs --tail=20

echo ""
echo "========================================="
echo "✓ Deployment Complete!"
echo "========================================="
echo ""
echo "Access the interface at:"
echo "  http://flarm2.local:8082"
echo ""
echo "Useful commands:"
echo "  docker compose logs -f           # View logs"
echo "  docker compose restart           # Restart"
echo "  docker compose down              # Stop"
echo "  docker compose ps                # Check status"
echo "  curl http://localhost:8082/health  # Health check"
echo "========================================="
