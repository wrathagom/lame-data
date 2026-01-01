#!/bin/bash
# Lame Data - Install Script
# Run this once after cloning the repo

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PI_DIR="$SCRIPT_DIR/software/raspberry-pi"
VENV_DIR="$PI_DIR/venv"

echo "==================================="
echo "  Lame Data - Installation"
echo "==================================="
echo ""

# Check if running as root for systemd operations
if [ "$EUID" -ne 0 ]; then
    echo "Note: Run with sudo for systemd service installation"
    echo "      sudo ./install.sh"
    echo ""
    SKIP_SYSTEMD=true
else
    SKIP_SYSTEMD=false
fi

# Create .env from example if it doesn't exist
echo "[1/5] Configuring environment..."
if [ ! -f "$PI_DIR/.env" ]; then
    cp "$PI_DIR/.env.example" "$PI_DIR/.env"
    echo "  Created .env from template"
    echo "  IMPORTANT: Edit $PI_DIR/.env with your WiFi credentials"
else
    echo "  .env already exists, skipping"
fi

# Create virtual environment
echo ""
echo "[2/5] Creating Python virtual environment..."
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo "  Created venv at $VENV_DIR"
else
    echo "  venv already exists, skipping"
fi

# Install Python dependencies
echo ""
echo "[3/5] Installing Python dependencies..."
"$VENV_DIR/bin/pip" install -q --upgrade pip
"$VENV_DIR/bin/pip" install -q -r "$PI_DIR/requirements.txt"
echo "  Done"

# Make scripts executable
echo ""
echo "[4/5] Setting permissions..."
chmod +x "$PI_DIR/wifi_manager.sh"
chmod +x "$SCRIPT_DIR/upgrade.sh" 2>/dev/null || true
echo "  Done"

# Install systemd services
echo ""
echo "[5/5] Installing systemd services..."
if [ "$SKIP_SYSTEMD" = true ]; then
    echo "  Skipped (run with sudo to install services)"
else
    cp "$PI_DIR/systemd/horse-recorder.service" /etc/systemd/system/
    cp "$PI_DIR/systemd/wifi-manager.service" /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable horse-recorder wifi-manager
    echo "  Services installed and enabled"
    echo ""
    read -p "Start services now? [y/N] " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        systemctl start wifi-manager
        systemctl start horse-recorder
        echo "  Services started"
    fi
fi

echo ""
echo "==================================="
echo "  Installation Complete!"
echo "==================================="
echo ""
echo "Next steps:"
echo "  1. Edit $PI_DIR/.env with your WiFi credentials"
echo "  2. Start services: sudo systemctl start horse-recorder wifi-manager"
echo "  3. Access web UI: http://$(hostname -I | awk '{print $1}'):5000"
echo ""
