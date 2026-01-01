#!/bin/bash

# Load configuration from .env file
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/.env" ]; then
    source "$SCRIPT_DIR/.env"
else
    echo "ERROR: .env file not found. Copy .env.example to .env and configure."
    exit 1
fi

FORCE_AP_FILE="/tmp/force_ap_mode"

# Wait for WiFi interface to be available
wait_for_wifi() {
    echo "Waiting for WiFi interface..."
    for i in {1..30}; do
        if ip link show wlan0 up &>/dev/null; then
            echo "WiFi interface ready"
            return 0
        fi
        echo "Waiting... ($i/30)"
        sleep 1
    done
    echo "ERROR: WiFi interface never became available!"
    return 1
}

check_home_wifi() {
    nmcli device wifi list | grep -q "$HOME_SSID"
    return $?
}

start_ap_mode() {
    echo "Starting Access Point mode..."
    
    # Stop hotspot if running
    nmcli connection down Hotspot 2>/dev/null
    
    # Turn off WiFi and back on to reset
    nmcli radio wifi off
    sleep 2
    nmcli radio wifi on
    sleep 3
    
    # Create hotspot
    nmcli device wifi hotspot ssid "$AP_SSID" password "$AP_PASSWORD"
    
    # Verify it started
    if nmcli connection show --active | grep -q "Hotspot"; then
        echo "✓ Access Point '$AP_SSID' is running"
        return 0
    else
        echo "✗ Failed to start Access Point"
        return 1
    fi
}

start_client_mode() {
    echo "Connecting to home WiFi '$HOME_SSID'..."
    
    # Stop hotspot if running
    nmcli connection down Hotspot 2>/dev/null
    
    # Connect to home network
    if ! nmcli connection up "$HOME_SSID" 2>/dev/null; then
        echo "Connection profile not found, trying SSID..."
        nmcli device wifi connect "$HOME_SSID"
    fi
    
    sleep 5
    
    if nmcli device status | grep -q "connected"; then
        echo "✓ Connected to $HOME_SSID"
        ip addr show wlan0 | grep "inet "
        return 0
    else
        echo "✗ Failed to connect, starting AP mode"
        start_ap_mode
        return 1
    fi
}

# MAIN SCRIPT STARTS HERE

# Wait for WiFi hardware to be ready
if ! wait_for_wifi; then
    echo "Cannot proceed without WiFi interface"
    exit 1
fi

# Check if we're forcing AP mode for testing
if [ -f "$FORCE_AP_FILE" ]; then
    echo "FORCE AP MODE - Test flag detected"
    start_ap_mode
    exit 0
fi

# Normal auto-detection logic
if check_home_wifi; then
    start_client_mode
else
    start_ap_mode
fi