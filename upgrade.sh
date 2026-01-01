#!/bin/bash
# Lame Data - Upgrade Script
# Pulls latest code and restarts services

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PI_DIR="$SCRIPT_DIR/software/raspberry-pi"

echo "==================================="
echo "  Lame Data - Upgrade"
echo "==================================="
echo ""

# Check for uncommitted changes
if ! git -C "$SCRIPT_DIR" diff --quiet 2>/dev/null; then
    echo "Warning: You have local changes that may be overwritten."
    read -p "Continue anyway? [y/N] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Upgrade cancelled."
        exit 1
    fi
fi

# Pull latest code
echo "[1/3] Pulling latest code..."
git -C "$SCRIPT_DIR" pull
echo "  Done"

# Update dependencies
echo ""
echo "[2/3] Updating dependencies..."
pip3 install -q -r "$PI_DIR/requirements.txt"
echo "  Done"

# Restart services
echo ""
echo "[3/3] Restarting services..."
if [ "$EUID" -eq 0 ]; then
    systemctl restart horse-recorder
    echo "  horse-recorder restarted"
else
    echo "  Run with sudo to restart services, or manually run:"
    echo "    sudo systemctl restart horse-recorder"
fi

echo ""
echo "==================================="
echo "  Upgrade Complete!"
echo "==================================="
echo ""
