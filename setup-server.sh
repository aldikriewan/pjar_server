#!/bin/bash
# PJAR Server Setup Script for Ubuntu
# Usage: bash setup-server.sh

set -e

echo "======================================"
echo "PJAR Server - Ubuntu Setup"
echo "======================================"

# Check if running on Ubuntu
if ! command -v lsb_release &> /dev/null; then
    echo "❌ This script is designed for Ubuntu/Debian"
    exit 1
fi

# Update system
echo "📦 Updating system..."
sudo apt update
sudo apt upgrade -y

# Install Python 3.10+
echo "🐍 Installing Python 3.10..."
sudo apt install -y python3.10 python3.10-venv python3-pip

# Create pjar user if it doesn't exist
if ! id "pjar" &>/dev/null; then
    echo "👤 Creating pjar user..."
    sudo useradd -m -s /bin/bash pjar
fi

# Create directories
echo "📁 Creating directories..."
sudo mkdir -p /home/pjar/pjar_server
sudo mkdir -p /var/lib/pjar-web/uploads/received
sudo chown -R pjar:pjar /home/pjar/pjar_server
sudo chown -R pjar:pjar /var/lib/pjar-web

# Copy server files
echo "📄 Copying server files..."
sudo cp -r ./* /home/pjar/pjar_server/ || echo "Note: Some files may already exist"
sudo chown -R pjar:pjar /home/pjar/pjar_server

# Setup virtual environment
echo "🔧 Setting up virtual environment..."
cd /home/pjar/pjar_server
sudo -u pjar python3.10 -m venv venv
sudo -u pjar venv/bin/pip install --upgrade pip
sudo -u pjar venv/bin/pip install -r requirements.txt

# Setup .env
if [ ! -f /home/pjar/pjar_server/.env ]; then
    echo "⚙️  Creating .env file..."
    sudo cp .env.example /home/pjar/pjar_server/.env
    echo "⚠️  IMPORTANT: Edit /home/pjar/pjar_server/.env with your configuration"
fi

# Create systemd service
echo "🚀 Creating systemd service..."
sudo tee /etc/systemd/system/pjar-server.service > /dev/null <<EOF
[Unit]
Description=PJAR Backend Server
After=network.target

[Service]
Type=simple
User=pjar
WorkingDirectory=/home/pjar/pjar_server
Environment="PATH=/home/pjar/pjar_server/venv/bin"
ExecStart=/home/pjar/pjar_server/venv/bin/gunicorn -w 2 -b 0.0.0.0:5000 --timeout 30 app:app
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable pjar-server
sudo systemctl start pjar-server

echo ""
echo "✅ Setup complete!"
echo ""
echo "📝 Next steps:"
echo "1. Edit /home/pjar/pjar_server/.env with your configuration"
echo "2. Run: sudo systemctl restart pjar-server"
echo "3. Check status: sudo systemctl status pjar-server"
echo "4. View logs: sudo journalctl -u pjar-server -f"
echo ""
echo "🔗 Server URL: http://$(hostname -I | awk '{print $1}'):5000"
echo ""
