#!/bin/bash
# Pegasus Galaxy Bot - Quick VPS Setup Script (Ubuntu / Debian / CentOS)
set -e

echo "=========================================="
echo "🪐 Pegasus Galaxy Bot - VPS Installer"
echo "=========================================="

# 1. Update and install Python3 & pip
echo "Installing dependencies..."
if [ -x "$(command -v apt-get)" ]; then
    sudo apt-get update -y
    sudo apt-get install -y python3 python3-pip
elif [ -x "$(command -v yum)" ]; then
    sudo yum install -y python3 python3-pip
fi

# 2. Install python packages
pip3 install --upgrade pip httpx rich

# 3. Create bot directory
APP_DIR="/opt/peg-mcp"
sudo mkdir -p "$APP_DIR"
echo "Copying files to $APP_DIR..."
sudo cp -r peg_client.py peg_bot.py peg_gui.py bot_strategy.py bot_config.json config_profiles custom_strategies .env "$APP_DIR/" || true

# 4. Install systemd services
if [ -f "pegasus-bot.service" ]; then
    echo "Configuring autonomous bot systemd service..."
    sudo cp pegasus-bot.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable pegasus-bot.service
    sudo systemctl restart pegasus-bot.service
    echo "✅ Bot service enabled and running! Status:"
    sudo systemctl status pegasus-bot.service --no-pager
fi

if [ -f "pegasus-gui.service" ]; then
    echo "Configuring Web GUI Hub systemd service (Port 7890)..."
    sudo cp pegasus-gui.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable pegasus-gui.service
    sudo systemctl restart pegasus-gui.service
    echo "✅ Web GUI service enabled and running! Accessible at http://YOUR_VPS_IP:7890"
fi

echo "=========================================="
echo "🎉 Installation complete!"
echo "• Web GUI Dashboard: http://YOUR_VPS_IP:7890"
echo "• View live bot logs: journalctl -u pegasus-bot -f"
echo "• Reset bot anytime:  sudo systemctl restart pegasus-bot"
echo "=========================================="
