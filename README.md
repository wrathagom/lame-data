<div align="center">

<img src="docs/assets/lamedata-logo-dark.png" alt="Lame Data" width="400">

### Equine gait analytics

Low-cost IMU-based system for detecting lameness, tracking performance, and building baseline movement profiles for horses.

[![License: PolyForm Noncommercial](https://img.shields.io/badge/License-PolyForm%20NC-blue.svg)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/wrathagom/lame-data?style=social)](https://github.com/wrathagom/lame-data/stargazers)

**[Getting Started](docs/getting-started.md)** · **[Hardware Guide](hardware/)** · **[Sample Data](examples/sample-data/)** · **[Website](https://lamedata.com)**

</div>

---

## The Problem

Lameness is the [#1 cause of lost performance](https://www.merckvetmanual.com/musculoskeletal-system/lameness-in-horses/overview-of-lameness-in-horses) in horses — the most common reason horses lose use. But detecting subtle or early-stage lameness is notoriously difficult. Clinical gait analysis systems exist, but they cost tens of thousands of dollars and require specialized facilities. Most horse owners and trainers rely on the human eye — which misses a lot.

## The Idea

What if you could strap $150 worth of sensors to a horse, collect high-frequency motion data, and build a movement profile that catches what eyes can't?

**Lame Data** uses cheap IMU sensors (M5StickC) connected to a Raspberry Pi to capture 194Hz accelerometer and gyroscope data from multiple points on a horse's body — cannon bones, poll, and more. Over time, regular measurements build a baseline for each horse. Deviations from that baseline surface problems early, before they become visible to the naked eye.

This isn't just a lameness detector. It's a movement intelligence platform:

- **Veterinary support** — Objective gait data to complement clinical assessments
- **Performance tracking** — Monitor training progress and recovery in sport and track horses
- **Baseline monitoring** — Weekly measurements that catch subtle changes over months
- **Research** — Open data and open tools for equine biomechanics research

## How It Works

```
┌─────────────┐     WiFi      ┌──────────────┐     Analysis     ┌──────────────┐
│  M5StickC   │ ──────────▶  │ Raspberry Pi │  ──────────────▶ │   Reports    │
│  IMU Sensor │   194Hz UDP   │    Server    │                  │  & Insights  │
│  (x1–5)     │               │              │                  │              │
└─────────────┘               └──────────────┘                  └──────────────┘
    On horse                    In your pocket                    On your screen
```

Each M5StickC sensor captures accelerometer and gyroscope data at 194Hz and streams it over WiFi to a Raspberry Pi running a lightweight collection server. The Pi provides a web interface for starting/stopping recording sessions and visualizing data in real time.

## Current Status

> **🟡 Active Development — Early prototype**

The system works with a single sensor and has been tested in real barn conditions. Multi-sensor support (up to 5 simultaneous devices) is the current focus. The analysis pipeline is being developed alongside longitudinal data collection on real horses.

**What works today:**
- Single-sensor data collection at 194Hz
- WiFi streaming with ~95% packet efficiency
- Web-based recording interface
- Real-time accelerometer visualization
- Automatic WiFi switching (home/field networks)
- Battery monitoring on sensors

**What's coming:**
- Multi-sensor simultaneous capture (5 sensors)
- Sensor mounting hardware (3D printable boot/holder designs)
- Baseline-vs-deviation analysis pipeline
- Radar chart visualization for multi-dimensional gait profiles
- Improved reporting interface
- Cloud platform for data storage and longitudinal tracking

## Hardware

| Component | Cost | Notes |
|---|---|---|
| M5StickC PLUS | ~$25 each | Need 1–5 depending on measurement points |
| Raspberry Pi 4 | $35–75 | Any model works, 4GB+ recommended |
| MicroSD card | ~$10 | 16GB minimum |
| USB battery bank | ~$15 | Powers the Pi in the field |

**Total cost: ~$85 (1 sensor) to ~$185 (5 sensors)**

For comparison, clinical equine gait analysis systems start around $15,000.

## Quick Start

### 1. Flash the M5StickC sensor

```bash
# Copy and configure
cp hardware/m5stickc/config.h.example hardware/m5stickc/config.h
# Edit config.h with your WiFi credentials and device ID
```

Flash using Arduino IDE or PlatformIO. See the [hardware guide](hardware/) for detailed instructions.

### 2. Set up the Raspberry Pi server

```bash
git clone git@github.com:wrathagom/lame-data.git
cd lame-data
sudo ./install.sh

# Configure your environment
# Edit software/raspberry-pi/.env with your WiFi credentials
```

### 3. Collect data

Power on your sensor(s), open the web interface on the Pi, and start a recording session. Walk or trot the horse past the sensor range. That's it.

See the [full getting started guide](docs/getting-started.md) for detailed setup instructions.

## Project Structure

```
lame-data/
├── hardware/           # M5StickC firmware and hardware docs
│   └── m5stickc/       # Arduino/PlatformIO sensor code
├── software/           # Raspberry Pi server and analysis tools
│   └── raspberry-pi/   # Collection server, web UI
├── examples/           # Sample data for testing and development
│   └── sample-data/
├── docs/               # Website (GitHub Pages) and documentation
│   ├── index.html      # Landing page at lamedata.com
│   └── assets/         # Logo, favicon, images
├── install.sh          # One-line Pi setup
└── upgrade.sh          # Update to latest version
```

## Licensing

Everything here is source-available under the [PolyForm Noncommercial](https://polyformproject.org/licenses/noncommercial/1.0.0/) license. The hardware is off-the-shelf. The firmware and server code are in this repo. You're free to use, modify, and share for any non-commercial purpose — research, education, personal use, hobby projects. If you can build it yourself — do it.

But if you want help, there are options:

- **📦 Kits** — Pre-configured sensor packs ready to go *(coming soon)*
- **☁️ Cloud** — Hosted analysis platform for longitudinal tracking *(coming soon)*
- **🤝 On-site service** — We come to your barn, collect data, deliver reports *(available in the Louisville, KY area)*

## Contributing

This project is in early development and contributions are welcome. Whether you're an embedded systems developer, a data scientist, an equine vet, or a horse person who wants to help test — there's a place for you.

- **Report bugs** or **request features** via [Issues](https://github.com/wrathagom/lame-data/issues)
- **Submit PRs** for code improvements, analysis algorithms, or documentation
- **Share data** from your own horses to help build reference datasets
- **Spread the word** — star the repo and tell your barn friends

## Background

This project was born from the intersection of a few things: a career in manufacturing engineering and data analytics, a job at a veterinary clinic, and a horse that needed monitoring. The idea is simple — the same IMU sensors that track human movement in phones and fitness wearables can capture incredibly detailed motion data from horses, and modern analysis techniques can find patterns in that data that human observation misses.

A project by [Sun & Stone Solutions](https://sunandstonesolutions.com/). Built by [Caleb Keller](https://calebmkeller.com) as a [Passion Stack](https://calebmkeller.com/blog/welcome-to-the-builder-economy) project — using AI and cheap hardware to make equine biomechanics accessible to everyone, not just research labs.

---

<div align="center">

**[⭐ Star this repo](https://github.com/wrathagom/lame-data)** if you think horses deserve better data.

</div>
