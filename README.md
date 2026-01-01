# Lame Data

Low-cost (~$150) equine gait analysis system using M5StickC + Raspberry Pi

## What It Does
- 194Hz IMU sampling from horse legs
- WiFi data streaming (95% packet efficiency)
- Web interface for recording sessions
- Real-time accelerometer plots

## Hardware Required
- M5StickC PLUS ($25 each, need 1-5)
- Raspberry Pi 4 ($35-75)
- MicroSD card (16GB+)
- Battery bank for Pi

## Quick Start

### M5StickC Sensor
1. Copy `hardware/m5stickc/config.h.example` to `config.h`
2. Update WiFi credentials and device ID
3. [Flash to M5StickC](hardware/m5stickc/README.md)

### Raspberry Pi Server
1. Copy `software/raspberry-pi/.env.example` to `.env`
2. Update WiFi credentials
3. Install dependencies: `pip install -r requirements.txt`
4. Run: `python horse_recorder.py`

See [full setup guide](docs/getting-started.md) for detailed instructions.

## Features
- 194Hz sample rate per device
- 5+ simultaneous sensors
- Automatic WiFi switching (home/field)
- Battery monitoring
- Web-based recording interface
- Built-in data visualization

## Use Cases
- Lameness detection
- Gait analysis
- Training optimization
- Research data collection
