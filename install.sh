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
echo "[1/8] Configuring environment..."
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

    # Cloud analytics (optional)
    echo ""
    echo "  Cloud Analytics (optional - press Enter to skip)"
    echo "  ================================================"
    echo "  If you have a Moose cloud backend running, enter its URL."
    echo "  For local dev, this is typically http://<your-laptop-ip>:4000"
    echo "  API key is only needed for production deployments."
    read -p "  Cloud URL []: " CLOUD_URL
    CLOUD_URL=${CLOUD_URL:-}
    CLOUD_API_KEY=""
    if [ -n "$CLOUD_URL" ]; then
        read -p "  Cloud API Key (blank for local dev) []: " CLOUD_API_KEY
        CLOUD_API_KEY=${CLOUD_API_KEY:-}
    fi

    # OTA_PASSWORD for wireless firmware updates. Honors a pre-set value so
    # you can pass `sudo OTA_PASSWORD=horsey ./install.sh` and skip the
    # auto-generated 32-char hex blob (overkill for a LAN-only barn setup).
    OTA_PASSWORD="${OTA_PASSWORD:-$(openssl rand -hex 16 2>/dev/null || head -c 16 /dev/urandom | xxd -p)}"

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

# Cloud Analytics (optional)
CLOUD_URL=$CLOUD_URL
CLOUD_API_KEY=$CLOUD_API_KEY

# Over-the-air firmware update password (shared with each M5StickC's
# config.h). Bake this value into the stick's config.h before flashing.
OTA_PASSWORD=$OTA_PASSWORD
EOF

    echo ""
    echo "  Configuration saved to .env"
    echo "  OTA_PASSWORD generated: $OTA_PASSWORD"
    echo "  → Copy this into each stick's config.h before the final USB flash."
fi

# Preserve OTA_PASSWORD across reconfigures — if someone re-ran and chose to
# keep the old .env, make sure it has an OTA_PASSWORD line. Honors a pre-set
# env var so `sudo OTA_PASSWORD=mypw ./install.sh` works even on the backfill
# path (e.g. when you're adding it to an already-installed Pi).
if [ -f "$PI_DIR/.env" ] && ! grep -q "^OTA_PASSWORD=" "$PI_DIR/.env"; then
    OTA_PASSWORD="${OTA_PASSWORD:-$(openssl rand -hex 16 2>/dev/null || head -c 16 /dev/urandom | xxd -p)}"
    echo "OTA_PASSWORD=$OTA_PASSWORD" >> "$PI_DIR/.env"
    echo "  Added OTA_PASSWORD=$OTA_PASSWORD to existing .env"
fi

# Create virtual environment
echo ""
echo "[2/8] Creating Python virtual environment..."
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo "  Created venv at $VENV_DIR"
else
    echo "  venv already exists, skipping"
fi

# Install Python dependencies
echo ""
echo "[3/8] Installing Python dependencies..."
"$VENV_DIR/bin/pip" install -q --upgrade pip
"$VENV_DIR/bin/pip" install -q -r "$PI_DIR/requirements.txt"
echo "  Done"

# Make scripts executable
echo ""
echo "[4/8] Setting permissions..."
chmod +x "$PI_DIR/wifi_manager.sh"
chmod +x "$SCRIPT_DIR/upgrade.sh" 2>/dev/null || true
echo "  Done"

# Disable WiFi MAC randomization (needed for DHCP reservations)
echo ""
echo "[5/8] Configuring stable WiFi MAC address..."
if [ "$SKIP_SYSTEMD" = true ]; then
    echo "  Skipped (run with sudo)"
else
    NM_CONF="/etc/NetworkManager/conf.d/no-random-mac.conf"
    if [ ! -f "$NM_CONF" ]; then
        cat > "$NM_CONF" << 'EOF'
[device]
wifi.scan-rand-mac-address=no

[connection]
wifi.cloned-mac-address=preserve
EOF
        echo "  Created $NM_CONF"
        echo "  MAC address will now be stable for DHCP reservations"
    else
        echo "  Already configured, skipping"
    fi
fi

# Configure passwordless shutdown for web UI
echo ""
echo "[6/8] Configuring shutdown permissions..."
if [ "$SKIP_SYSTEMD" = true ]; then
    echo "  Skipped (run with sudo)"
else
    REPO_OWNER_EARLY=$(stat -c '%U' "$SCRIPT_DIR")
    SUDOERS_FILE="/etc/sudoers.d/lame-data-shutdown"
    echo "$REPO_OWNER_EARLY ALL=(ALL) NOPASSWD: /sbin/shutdown, /bin/systemctl restart horse-recorder" > "$SUDOERS_FILE"
    chmod 0440 "$SUDOERS_FILE"
    echo "  Granted $REPO_OWNER_EARLY passwordless shutdown access"
fi

# Install arduino-cli + M5Stack ESP32 core so the Pi can build and push
# firmware updates to the sticks wirelessly (no USB cable needed after the
# initial one-time flash).
echo ""
echo "[7/8] Installing arduino-cli + M5Stack ESP32 core..."
if [ "$SKIP_SYSTEMD" = true ]; then
    echo "  Skipped (run with sudo to install arduino-cli to /usr/local/bin)"
else
    REPO_OWNER_FW=$(stat -c '%U' "$SCRIPT_DIR")
    if ! command -v arduino-cli >/dev/null 2>&1; then
        ARCH=$(uname -m)
        case "$ARCH" in
            aarch64|arm64) ARDUINO_PKG="Linux_ARM64" ;;
            armv7l|armv6l) ARDUINO_PKG="Linux_ARMv7" ;;
            x86_64)        ARDUINO_PKG="Linux_64bit" ;;
            *)             ARDUINO_PKG="Linux_ARM64" ;;
        esac
        ARDUINO_CLI_URL="https://downloads.arduino.cc/arduino-cli/arduino-cli_latest_${ARDUINO_PKG}.tar.gz"
        TMP_DIR=$(mktemp -d)
        if curl -fsSL "$ARDUINO_CLI_URL" -o "$TMP_DIR/arduino-cli.tar.gz"; then
            tar -xzf "$TMP_DIR/arduino-cli.tar.gz" -C "$TMP_DIR"
            mv "$TMP_DIR/arduino-cli" /usr/local/bin/arduino-cli
            chmod +x /usr/local/bin/arduino-cli
            echo "  arduino-cli installed to /usr/local/bin"
        else
            echo "  WARNING: failed to download arduino-cli (offline?). Fleet firmware"
            echo "           flash will be disabled in the web UI until this runs cleanly."
        fi
        rm -rf "$TMP_DIR"
    else
        echo "  arduino-cli already installed"
    fi

    if command -v arduino-cli >/dev/null 2>&1; then
        # Core install runs as the repo owner so ~/.arduino15 lives in their
        # home dir (not root's) and the horse-recorder service can read it.
        sudo -u "$REPO_OWNER_FW" arduino-cli config init --overwrite --quiet 2>/dev/null || true
        sudo -u "$REPO_OWNER_FW" arduino-cli config add board_manager.additional_urls \
            https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/arduino/package_m5stack_index.json
        sudo -u "$REPO_OWNER_FW" arduino-cli core update-index
        if ! sudo -u "$REPO_OWNER_FW" arduino-cli core list | grep -q "m5stack:esp32"; then
            echo "  Installing m5stack:esp32 core (this takes a few minutes)..."
            sudo -u "$REPO_OWNER_FW" arduino-cli core install m5stack:esp32
            echo "  M5Stack ESP32 core installed"
        else
            echo "  M5Stack ESP32 core already installed"
        fi

        # Firmware library dependencies. The board core alone doesn't include
        # the M5StickCPlus headers — without these the .ino won't compile.
        # arduino-cli lib install is idempotent so safe to rerun.
        echo "  Installing Arduino library dependencies..."
        sudo -u "$REPO_OWNER_FW" arduino-cli lib install "M5StickCPlus"
    fi
fi

# Install systemd services
echo ""
echo "[8/8] Installing systemd services..."
if [ "$SKIP_SYSTEMD" = true ]; then
    echo "  Skipped (run with sudo to install services)"
else
    # Stop existing services if running
    systemctl stop horse-recorder 2>/dev/null || true
    systemctl stop wifi-manager 2>/dev/null || true

    # Get the user who owns the repo (not root, even if running with sudo)
    REPO_OWNER=$(stat -c '%U' "$SCRIPT_DIR")

    # Install service files with correct paths
    sed -e "s|/home/pi/lame-data|$SCRIPT_DIR|g" \
        -e "s|User=pi|User=$REPO_OWNER|g" \
        "$PI_DIR/systemd/horse-recorder.service" > /etc/systemd/system/horse-recorder.service

    sed -e "s|/home/pi/lame-data|$SCRIPT_DIR|g" \
        "$PI_DIR/systemd/wifi-manager.service" > /etc/systemd/system/wifi-manager.service

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
