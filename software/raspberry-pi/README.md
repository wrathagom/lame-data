# Raspberry Pi Server

Flask-based data recorder and web interface for the horse biomechanics system.

## Setup

1. Copy `.env.example` to `.env` and configure:
   ```bash
   cp .env.example .env
   nano .env
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the server:
   ```bash
   python horse_recorder.py
   ```

4. Access the web interface at `http://<pi-ip>:5000`

## Configuration

Edit `.env` to configure:

| Variable | Default | Description |
|----------|---------|-------------|
| HOME_SSID | - | Your home WiFi network name |
| AP_SSID | HorseNet | Hotspot name for field use |
| AP_PASSWORD | - | Hotspot password |
| UDP_PORT | 8888 | Port for sensor data |
| WEB_PORT | 5000 | Web interface port |
| DATA_DIR | ./data | Where recordings are saved |

## Auto-Start (systemd)

To run automatically on boot:

```bash
sudo cp systemd/horse-recorder.service /etc/systemd/system/
sudo cp systemd/wifi-manager.service /etc/systemd/system/
sudo systemctl enable horse-recorder wifi-manager
sudo systemctl start horse-recorder wifi-manager
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main recording interface |
| `/sessions` | GET | View past sessions |
| `/api/status` | GET | Current recording status |
| `/api/start` | POST | Start recording |
| `/api/stop` | POST | Stop recording |
| `/api/sessions` | GET | List all sessions (JSON) |
| `/api/session_data/<file>` | GET | Get session data for plotting |
| `/api/download/<file>` | GET | Download raw CSV |
