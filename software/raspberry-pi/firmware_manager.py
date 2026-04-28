"""Firmware version + build + OTA-flash orchestration for the M5StickC fleet.

The Pi is the build host and the flash host. On upgrade it pulls the latest
`horse_sensor.ino` source (incl. a bumped FIRMWARE_VERSION constant); when a
user clicks "Flash all plugged-in" in the UI, we generate a config.h from the
Pi's .env, build the .bin with arduino-cli, and push it to each target stick
via the ESP32 OTA upload protocol.

Design guardrails:
 - Pure functions for version + toolchain detection so unit tests don't need
   the actual compiler installed.
 - The subprocess-touching functions (build_bin, flash_device) raise on
   failure with clear messages; orchestration captures those and surfaces
   them per-device in flash_state.
 - flash_state is module-level (similar to recording_state in horse_recorder)
   so the API layer can expose it via /api/firmware/flash_status polling.
"""
from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import threading
import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent.parent
FIRMWARE_SRC_DIR = REPO_ROOT / 'hardware' / 'm5stickc' / 'horse_sensor'
FIRMWARE_INO = FIRMWARE_SRC_DIR / 'horse_sensor.ino'
GENERATED_CONFIG = FIRMWARE_SRC_DIR / 'config.h'

BUILD_DIR = SCRIPT_DIR / 'firmware'
FIRMWARE_BIN = BUILD_DIR / 'horse_sensor.bin'

# Fully-qualified board name that arduino-cli expects for the M5StickC Plus
# M5Stack core. Different versions of the M5Stack ESP32 core have used
# slightly different board IDs over time (m5stick-c-plus, m5stickc_plus,
# m5stack_stickc_plus). If yours doesn't compile with the default, find the
# right value with:
#   arduino-cli board listall m5stack:esp32 | grep -i stick
# and override via FIRMWARE_FQBN in the Pi's .env file — no code change.
FQBN = os.getenv('FIRMWARE_FQBN', 'm5stack:esp32:m5stack_stickc_plus')

# Regex that pulls the FIRMWARE_VERSION constant out of the .ino source. Lives
# here, not scattered across modules, so a version-scheme change is one edit.
_VERSION_RE = re.compile(
    r'FIRMWARE_VERSION\s*=\s*"([^"]+)"'
)

# espota.py progress lines look like:  Uploading: [=====    ] 43%
_ESPOTA_PROGRESS_RE = re.compile(r'(\d+)%')


# ---------------------------------------------------------------------------
# Flash state (read-only to the API layer; mutated here)
# ---------------------------------------------------------------------------

flash_state = {
    'active': False,
    'targets': {},      # device_id -> {state, progress, error, version_at_start}
    'started_at': None,
    'finished_at': None,
}

_flash_lock = threading.Lock()


def reset_flash_state():
    with _flash_lock:
        flash_state['active'] = False
        flash_state['targets'] = {}
        flash_state['started_at'] = None
        flash_state['finished_at'] = None


def _set_target(device_id, **fields):
    with _flash_lock:
        flash_state['targets'].setdefault(device_id, {})
        flash_state['targets'][device_id].update(fields)


# ---------------------------------------------------------------------------
# Pure functions — safe to call anywhere, no subprocess side effects
# ---------------------------------------------------------------------------

def available_version():
    """Return the FIRMWARE_VERSION string parsed from the .ino source, or
    None if the source file is missing or doesn't declare the constant."""
    if not FIRMWARE_INO.exists():
        return None
    text = FIRMWARE_INO.read_text()
    m = _VERSION_RE.search(text)
    return m.group(1) if m else None


def toolchain_installed():
    """True iff arduino-cli is on PATH and the m5stack:esp32 core is installed."""
    if shutil.which('arduino-cli') is None:
        return False
    try:
        result = subprocess.run(
            ['arduino-cli', 'core', 'list'],
            capture_output=True, text=True, timeout=10,
        )
        return 'm5stack:esp32' in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_pi_lan_ip():
    """Best-effort LAN IP detection. Returns 127.0.0.1 if the Pi is offline —
    in that case the sticks wouldn't be able to reach us anyway."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # No packet actually leaves — connect() on a UDP socket just sets
        # up the kernel's routing decision so getsockname() has an answer.
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    except OSError:
        return '127.0.0.1'
    finally:
        s.close()


def render_config_h(env=None, pi_ip=None):
    """Return a config.h string populated from the Pi's .env values.

    env: dict-like (defaults to os.environ); looked up for HOME_SSID, etc.
    pi_ip: override for the LAN IP; defaults to auto-detected.
    """
    env = env if env is not None else os.environ
    home_ssid = env.get('HOME_SSID', '')
    home_pw = env.get('HOME_PASSWORD', '')
    ap_ssid = env.get('AP_SSID', 'HorseNet')
    ap_pw = env.get('AP_PASSWORD', 'Horse12345')
    udp_port = env.get('UDP_PORT', '8888')
    ota_pw = env.get('OTA_PASSWORD', 'changeme')
    pi_ip = pi_ip if pi_ip is not None else get_pi_lan_ip()

    return f"""// AUTO-GENERATED by firmware_manager.py. Do not edit by hand — rerun the
// Pi's firmware build (via the web UI) to regenerate.
#ifndef CONFIG_H
#define CONFIG_H

struct WiFiNetwork {{
  const char* ssid;
  const char* password;
  const char* piIP;
}};

WiFiNetwork networks[] = {{
  {{"{home_ssid}", "{home_pw}", "{pi_ip}"}},
  {{"{ap_ssid}", "{ap_pw}", "10.42.0.1"}}
}};
const int NUM_NETWORKS = 2;

const char* deviceName = "Sensor";
const int udpPort = {udp_port};
const char* otaPassword = "{ota_pw}";

#endif
"""


def write_generated_config(env=None, pi_ip=None):
    """Write config.h to the firmware source dir so arduino-cli picks it up."""
    GENERATED_CONFIG.write_text(render_config_h(env=env, pi_ip=pi_ip))


# ---------------------------------------------------------------------------
# Subprocess-touching — call from a background thread, not request handlers
# ---------------------------------------------------------------------------

def build_bin():
    """Generate config.h, invoke arduino-cli compile, copy .bin to BUILD_DIR.

    Raises RuntimeError on any failure with a message suitable for surfacing
    to the UI.
    """
    if not toolchain_installed():
        raise RuntimeError(
            'arduino-cli + m5stack:esp32 core not installed. '
            'Run `sudo ./install.sh` on the Pi to install the toolchain.'
        )

    write_generated_config()
    BUILD_DIR.mkdir(exist_ok=True)

    cmd = [
        'arduino-cli', 'compile',
        '--fqbn', FQBN,
        '--output-dir', str(BUILD_DIR),
        str(FIRMWARE_SRC_DIR),
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError('arduino-cli compile timed out after 5 minutes')

    if result.returncode != 0:
        tail = (result.stderr or result.stdout or '')[-800:]
        raise RuntimeError(f'arduino-cli compile failed:\n{tail}')

    # arduino-cli writes several artifacts; we want the plain .bin.
    produced = list(BUILD_DIR.glob('*.bin'))
    if not produced:
        raise RuntimeError('compile succeeded but produced no .bin')

    # Normalize to a stable filename the flash step expects.
    chosen = sorted(produced, key=lambda p: p.stat().st_mtime)[-1]
    if chosen != FIRMWARE_BIN:
        shutil.copy2(chosen, FIRMWARE_BIN)


def _find_espota():
    """Locate espota.py inside the installed arduino-cli core. Different core
    versions nest it at slightly different paths, so search a couple of known
    roots. Returns the full path or None if not found."""
    candidates = []
    home = Path.home()
    roots = [
        home / '.arduino15' / 'packages' / 'm5stack' / 'hardware' / 'esp32',
        home / '.arduino15' / 'packages' / 'esp32' / 'hardware' / 'esp32',
    ]
    for root in roots:
        if root.exists():
            candidates.extend(root.glob('*/tools/espota.py'))
    return sorted(candidates, reverse=True)[0] if candidates else None


def flash_device(device_id, device_ip, password, progress_callback=None):
    """Push FIRMWARE_BIN to a single stick via espota.py. Blocks until the
    subprocess exits. progress_callback (if given) is called with an int 0-100
    as espota.py reports progress lines.

    Raises RuntimeError with a short message on failure — caller is expected
    to catch and record it in flash_state.
    """
    if not FIRMWARE_BIN.exists():
        raise RuntimeError('firmware binary missing — run build first')

    espota = _find_espota()
    if espota is None:
        raise RuntimeError(
            'espota.py not found. The m5stack:esp32 core may not be fully '
            'installed — try `arduino-cli core install m5stack:esp32`.'
        )

    cmd = [
        'python3', str(espota),
        '--ip', device_ip,
        '--auth', password,
        '--file', str(FIRMWARE_BIN),
    ]
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )

    last_pct = -1
    last_line = ''
    for line in proc.stdout or []:
        last_line = line.rstrip()
        m = _ESPOTA_PROGRESS_RE.search(line)
        if m:
            pct = int(m.group(1))
            if pct != last_pct and progress_callback:
                progress_callback(pct)
                last_pct = pct

    rc = proc.wait(timeout=120)
    if rc != 0:
        raise RuntimeError(f'espota.py failed (rc={rc}): {last_line}')


# ---------------------------------------------------------------------------
# Orchestration — called from the API layer in a background thread
# ---------------------------------------------------------------------------

def flash_fleet(targets, password, device_ip_lookup, current_versions=None):
    """Sequentially flash a list of (device_id, device_ip) tuples. Updates
    flash_state per-device so the UI polling endpoint has progress to show.

    `device_ip_lookup` is a callable that returns the most recent IP we've
    seen from a device (injected by horse_recorder's caller so we don't need
    a hard dep on its internal state).

    Raises nothing — individual failures are recorded per-device; callers
    should check flash_state['targets'] after the fleet run.
    """
    current_versions = current_versions or {}

    with _flash_lock:
        flash_state['active'] = True
        flash_state['started_at'] = datetime.datetime.now().isoformat()
        flash_state['finished_at'] = None
        flash_state['targets'] = {
            device_id: {
                'state': 'pending',
                'progress': 0,
                'error': None,
                'version_at_start': current_versions.get(device_id, 'unknown'),
            }
            for device_id in targets
        }

    try:
        build_bin()
    except RuntimeError as e:
        # Build failure means no device can flash — mark every target failed.
        with _flash_lock:
            for device_id in flash_state['targets']:
                flash_state['targets'][device_id]['state'] = 'failed'
                flash_state['targets'][device_id]['error'] = f'build: {e}'
            flash_state['active'] = False
            flash_state['finished_at'] = datetime.datetime.now().isoformat()
        return

    for device_id in targets:
        device_ip = device_ip_lookup(device_id)
        if not device_ip:
            _set_target(device_id, state='failed',
                        error='no known IP for device (not connected recently)')
            continue

        _set_target(device_id, state='running', progress=0)

        def cb(pct, _id=device_id):
            _set_target(_id, progress=pct)

        try:
            flash_device(device_id, device_ip, password, progress_callback=cb)
            _set_target(device_id, state='done', progress=100)
        except Exception as e:
            _set_target(device_id, state='failed', error=str(e))

    with _flash_lock:
        flash_state['active'] = False
        flash_state['finished_at'] = datetime.datetime.now().isoformat()
