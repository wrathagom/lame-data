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

# Configure .env
echo "[1/5] Configuring environment..."
if [ -f "$PI_DIR/.env" ]; then
    echo "  .env already exists."
    read -p "  Reconfigure? [y/N] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "  Keeping existing configuration"
        SKIP_ENV_CONFIG=true
    else
        SKIP_ENV_CONFIG=false
    fi
else
    SKIP_ENV_CONFIG=false
fi

if [ "$SKIP_ENV_CONFIG" = false ]; then
    echo ""
    echo "  WiFi Configuration"
    echo "  ==================="

    # Home network (required)
    read -p "  Home WiFi SSID: " HOME_SSID
    read -s -p "  Home WiFi Password: " HOME_PASSWORD
    echo ""

    # AP settings (with defaults)
    echo ""
    echo "  Access Point Configuration (press Enter for defaults)"
    read -p "  AP SSID [HorseNet]: " AP_SSID
    AP_SSID=${AP_SSID:-HorseNet}
    read -p "  AP Password [Horse12345]: " AP_PASSWORD
    AP_PASSWORD=${AP_PASSWORD:-Horse12345}

    # Write .env file
    cat > "$PI_DIR/.env" << EOF
# WiFi Configuration
HOME_SSID="$HOME_SSID"
HOME_PASSWORD="$HOME_PASSWORD"
AP_SSID="$AP_SSID"
AP_PASSWORD="$AP_PASSWORD"

# Server Configuration
UDP_PORT=8888
WEB_PORT=5000

# Data storage (optional, defaults to ./data)
# DATA_DIR=/home/pi/horse_data
EOF

    echo ""
    echo "  Configuration saved to .env"
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
    # Stop existing services if running
    systemctl stop horse-recorder 2>/dev/null || true
    systemctl stop wifi-manager 2>/dev/null || true

    cp "$PI_DIR/systemd/horse-recorder.service" /etc/systemd/system/
    cp "$PI_DIR/systemd/wifi-manager.service" /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable horse-recorder wifi-manager
    echo "  Services installed and enabled"

    echo ""
    read -p "Start services now? [Y/n] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        echo "  Starting wifi-manager..."
        if systemctl start wifi-manager; then
            echo "  wifi-manager: OK"
        else
            echo "  wifi-manager: FAILED"
            echo "  Check logs: journalctl -u wifi-manager -n 20"
        fi

        echo "  Starting horse-recorder..."
        if systemctl start horse-recorder; then
            sleep 2  # Give it a moment to start
            if systemctl is-active --quiet horse-recorder; then
                echo "  horse-recorder: OK"
            else
                echo "  horse-recorder: FAILED (crashed after start)"
                echo "  Check logs: journalctl -u horse-recorder -n 20"
            fi
        else
            echo "  horse-recorder: FAILED"
            echo "  Check logs: journalctl -u horse-recorder -n 20"
        fi
    fi
fi

echo ""
echo "==================================="
echo "  Installation Complete!"
echo "==================================="
echo ""
echo "Access web UI: http://$(hostname -I | awk '{print $1}'):5000"
echo ""
