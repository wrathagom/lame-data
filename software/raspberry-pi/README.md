# Raspberry Pi Server

Flask-based data recorder and web interface for the horse biomechanics system.

## Setup

1. Copy `.env.example` to `.env` and configure:
   ```bash
   cp .env.example .env
   nano .env
   ```

2. Create the venv and install dependencies:
   ```bash
   python3 -m venv venv
   venv/bin/pip install -r requirements.txt
   ```

   For contributors who want to run the tests, install the dev deps instead:
   ```bash
   venv/bin/pip install -r requirements-dev.txt
   ```

3. Run the server:
   ```bash
   venv/bin/python horse_recorder.py
   ```

4. Access the web interface at `http://<pi-ip>:5000`.

## Configuration

Edit `.env` to configure:

| Variable | Default | Description |
|----------|---------|-------------|
| HOME_SSID | - | Home WiFi network (used by `wifi_manager.sh`) |
| AP_SSID | HorseNet | Hotspot name for field use |
| AP_PASSWORD | - | Hotspot password |
| UDP_PORT | 8888 | Port the Pi listens on for sensor data |
| WEB_PORT | 5000 | Web interface port |
| DATA_DIR | `./data` | Where session CSVs are saved |
| CLOUD_URL | `` (disabled) | Base URL of the cloud ingest endpoint |
| CLOUD_API_KEY | `` (disabled) | API key passed on cloud uploads |

Runtime state lives in two JSON files next to `horse_recorder.py`:

- `device_config.json` — sensor ID to horse-position mapping (edited via the Settings page).
- `protocols.json` — user-defined recording protocols with favorites (edited via the Protocols page; seeded with a "Standard Lameness Exam" on first run).

## Auto-Start (systemd)

To run automatically on boot:

```bash
sudo cp systemd/horse-recorder.service /etc/systemd/system/
sudo cp systemd/wifi-manager.service /etc/systemd/system/
sudo systemctl enable horse-recorder wifi-manager
sudo systemctl start horse-recorder wifi-manager
```

## Web Interface

| Path | Purpose |
|------|---------|
| `/` | Recorder — horse diagram, favorite-protocol quick-launch, manual start/stop |
| `/sessions` | Browse, download, and upload past recordings |
| `/protocols` | CRUD for recording protocols; toggle up to 2 favorites |
| `/settings` (alias `/config`) | Device-to-position assignment, theme picker, system actions |
| `/view/<filename>` | Inspect an individual session (charts) |

## API Endpoints

### Recording lifecycle
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | Current recording flag, device status, samples received |
| `/api/start` | POST | Begin a recording. Body: `{location, notes, horse}` for a manual run, or `{location, horse, protocol_name, step_instruction, iteration}` when run from a protocol. `horse` is optional. |
| `/api/stop` | POST | End the current recording |
| `/api/sync` | POST | Re-broadcast the time-sync packet to sensors mid-recording |
| `/api/recent_horses` | GET | Distinct horse names from recent sessions (newest first, case-insensitive dedup, capped at 10). Powers the Recorder's horse autocomplete |

### Protocols
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/protocols` | GET | List all protocols |
| `/api/protocols` | POST | Create. Body: `{name, steps: [{instruction}]}` |
| `/api/protocols/<id>` | PUT | Replace name and/or steps |
| `/api/protocols/<id>` | DELETE | Remove |
| `/api/protocols/<id>/favorite` | POST | Body: `{is_favorite: bool}`. Returns 409 with `current_favorites` if setting a third favorite |

### Devices
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/device_config` | GET | Current sensor-to-position mapping |
| `/api/device_config` | POST | Replace the mapping |

### Sessions (saved CSVs)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/sessions` | GET | List saved sessions with parsed metadata |
| `/api/session_data/<filename>` | GET | Multi-device accelerometer arrays for plotting |
| `/api/segment/<filename>` | GET | Gait-segmentation output |
| `/api/download/<filename>` | GET | Download a single CSV |
| `/api/download_batch` | POST | Body: `{filenames: [...]}`; returns a zip |

### Cloud upload
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/cloud_status` | GET | Whether `CLOUD_URL` / `CLOUD_API_KEY` are configured |
| `/api/upload/<filename>` | POST | Start uploading a single session to the cloud |
| `/api/upload_status/<filename>` | GET | Poll upload progress |

### System
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/upgrade` | POST | Run `upgrade.sh` (git pull → tests → restart) |
| `/api/shutdown` | POST | Body: `{action: "reboot" | "shutdown"}` |

## CSV Format

Each recording writes a `session_YYYYMMDD_HHMMSS.csv` containing a comment header, a single CSV column line, data rows, and a comment footer:

```
# Location: <user-provided>
# Notes: <user-provided OR step instruction when run from a protocol>
# Start Time: <ISO 8601>
# Device Config: <JSON of id → {position, color}>
# Horse: <name>                        (only when horse field provided)
# Protocol: <protocol name>            (only when run from a protocol)
# Step Iteration: <N>                  (only when run from a protocol)
timestamp,device_id,millis_time,accel_x,accel_y,accel_z,gyro_x,gyro_y,gyro_z
... sample rows ...
# End Time: <ISO 8601>
# Total Samples: <N>
# Sync Offsets: <JSON of id → {device_millis, pi_time}>
```

Downstream parsers should treat unknown `# ...` lines as ignorable metadata — new headers may be added over time.

## Testing

Tests live in `tests/` and use Flask's `test_client()` with per-test monkeypatching of `DATA_DIR`, `PROTOCOLS_FILE`, and `DEVICE_CONFIG_FILE`, so runs never touch your real data directory. UDP listener and cloud upload paths are intentionally not covered.

Run them with:

```bash
venv/bin/pytest tests
```

The suite also runs automatically in two places:

- **CI**: `.github/workflows/test.yml` runs on every push and PR.
- **Upgrade gate**: `upgrade.sh` runs `pytest -x` between `git pull` and `systemctl restart horse-recorder`. A failing test leaves the previous service running rather than rolling a broken commit. See the root `upgrade.sh` for the full flow.

When adding a feature, add tests that pin the contract the frontend or the CSV consumers depend on — the same way `test_protocols_api.py` locks the 409 `current_favorites` payload and `test_recording_api.py` locks the exact `# Protocol:` / `# Step Iteration:` header strings.
