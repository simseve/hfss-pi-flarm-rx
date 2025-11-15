#!/bin/bash
#
# OGN Web Configuration Deployment Script
# Deploys React frontend + FastAPI backend to Raspberry Pi
#

set -e

# Configuration
TARGET_USER="hfss"
TARGET_HOST="flarm2.local"
TARGET_DIR="/home/hfss/ogn-web"
BACKEND_PORT=8082
FRONTEND_PORT=3000

echo "========================================="
echo "OGN Web Configuration Deployment"
echo "========================================="
echo "Target: ${TARGET_USER}@${TARGET_HOST}"
echo "Directory: ${TARGET_DIR}"
echo "========================================="
echo

# Step 1: Build Frontend
echo "[1/6] Building React frontend..."
cd frontend
npm install
npm run build
cd ..
echo "✓ Frontend built successfully"
echo

# Step 2: Create deployment package
echo "[2/6] Creating deployment package..."
DEPLOY_PKG="ogn-web-deploy.tar.gz"
tar -czf ${DEPLOY_PKG} \
    backend/ \
    frontend/dist/ \
    frontend/package.json \
    ../.env
echo "✓ Package created: ${DEPLOY_PKG}"
echo

# Step 3: Upload to target
echo "[3/6] Uploading to ${TARGET_HOST}..."
scp ${DEPLOY_PKG} ${TARGET_USER}@${TARGET_HOST}:/tmp/
echo "✓ Upload complete"
echo

# Step 4: Extract and setup on target
echo "[4/6] Extracting on target..."
ssh ${TARGET_USER}@${TARGET_HOST} bash << 'ENDSSH'
set -e

# Create directory
mkdir -p /home/hfss/ogn-web
cd /home/hfss/ogn-web

# Extract
tar -xzf /tmp/ogn-web-deploy.tar.gz
rm /tmp/ogn-web-deploy.tar.gz

# Setup Python environment
echo "Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt

echo "✓ Extraction and setup complete"
ENDSSH
echo "✓ Setup complete"
echo

# Step 5: Create systemd service
echo "[5/6] Creating systemd service..."
ssh ${TARGET_USER}@${TARGET_HOST} sudo bash << 'ENDSSH'
set -e

cat > /etc/systemd/system/ogn-web.service << 'EOF'
[Unit]
Description=OGN Web Configuration Interface
Documentation=https://github.com/your-org/hfss-pi-flarm-rx
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=hfss
Group=hfss
WorkingDirectory=/home/hfss/ogn-web/backend
Environment="PATH=/home/hfss/ogn-web/venv/bin"
ExecStart=/home/hfss/ogn-web/venv/bin/python3 main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Logging
SyslogIdentifier=ogn-web

# Resource limits
MemoryLimit=512M
CPUQuota=50%

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
systemctl daemon-reload
systemctl enable ogn-web
systemctl restart ogn-web

echo "✓ Systemd service created and started"
ENDSSH
echo "✓ Service installed"
echo

# Step 6: Setup nginx reverse proxy (optional)
echo "[6/6] Configuring nginx (optional)..."
ssh ${TARGET_USER}@${TARGET_HOST} sudo bash << 'ENDSSH' || echo "Skipping nginx setup (not critical)"
set -e

# Check if nginx is installed
if command -v nginx &> /dev/null; then
    cat > /etc/nginx/sites-available/ogn-web << 'EOF'
server {
    listen 80;
    server_name localhost;

    # Frontend static files
    location / {
        root /home/hfss/ogn-web/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # Backend API proxy
    location /api {
        proxy_pass http://localhost:8082;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
EOF

    # Enable site
    ln -sf /etc/nginx/sites-available/ogn-web /etc/nginx/sites-enabled/ogn-web
    nginx -t && systemctl reload nginx
    echo "✓ Nginx configured"
else
    echo "ℹ Nginx not installed - skipping reverse proxy setup"
fi
ENDSSH
echo

# Cleanup
rm -f ${DEPLOY_PKG}

echo "========================================="
echo "✓ Deployment Complete!"
echo "========================================="
echo
echo "Service Status:"
ssh ${TARGET_USER}@${TARGET_HOST} sudo systemctl status ogn-web --no-pager || true
echo
echo "Access the interface at:"
echo "  http://${TARGET_HOST}  (if nginx is configured)"
echo "  http://${TARGET_HOST}:${BACKEND_PORT}  (direct API access)"
echo
echo "Useful commands:"
echo "  ssh ${TARGET_USER}@${TARGET_HOST} sudo systemctl status ogn-web"
echo "  ssh ${TARGET_USER}@${TARGET_HOST} sudo journalctl -u ogn-web -f"
echo "  ssh ${TARGET_USER}@${TARGET_HOST} sudo systemctl restart ogn-web"
echo "========================================="
