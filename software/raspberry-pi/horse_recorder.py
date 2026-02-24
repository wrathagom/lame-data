from flask import Flask, render_template, request, jsonify, send_file
import socket
import datetime
import os
import threading
import json
import csv
import math
from pathlib import Path
from collections import deque
from dotenv import load_dotenv
from gait_segmentation import segment_gait

try:
    import requests as http_requests
except ImportError:
    http_requests = None

# Load configuration from .env file
SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR / '.env')

# Configuration from environment
UDP_PORT = int(os.getenv('UDP_PORT', 8888))
WEB_PORT = int(os.getenv('WEB_PORT', 5000))
DATA_DIR = os.getenv('DATA_DIR', str(SCRIPT_DIR / 'data'))
DEVICE_CONFIG_FILE = SCRIPT_DIR / 'device_config.json'
CLOUD_URL = os.getenv('CLOUD_URL', '').rstrip('/')
CLOUD_API_KEY = os.getenv('CLOUD_API_KEY', '')

app = Flask(__name__,
          template_folder=str(SCRIPT_DIR / 'templates'),
          static_folder=str(SCRIPT_DIR / 'static'))

os.makedirs(DATA_DIR, exist_ok=True)


class BufferedRecorder:
    """Buffered file writer for high-throughput sensor data"""

    def __init__(self, filepath, flush_interval_ms=500, buffer_size=1000):
        self.filepath = filepath
        self.flush_interval = flush_interval_ms / 1000.0  # Convert to seconds
        self.buffer = deque(maxlen=buffer_size)
        self.lock = threading.Lock()
        self.file = None
        self.running = False
        self.flush_thread = None
        self.total_samples = 0

    def start(self, header_lines):
        """Open file, write headers, start flush thread"""
        self.file = open(self.filepath, 'w', buffering=65536)  # 64KB OS buffer
        for line in header_lines:
            self.file.write(line + '\n')
        self.running = True
        self.flush_thread = threading.Thread(target=self._flush_worker, daemon=True)
        self.flush_thread.start()

    def append(self, line):
        """Thread-safe append to buffer (O(1))"""
        with self.lock:
            self.buffer.append(line)
            self.total_samples += 1

    def _flush_worker(self):
        """Background thread that flushes buffer every N milliseconds"""
        while self.running:
            threading.Event().wait(self.flush_interval)
            self._flush()

    def _flush(self):
        """Write all buffered lines to disk"""
        with self.lock:
            if self.buffer and self.file:
                while self.buffer:
                    self.file.write(self.buffer.popleft())
                self.file.flush()

    def stop(self, footer_lines=None):
        """Flush remaining data, write footers, close file"""
        self.running = False
        if self.flush_thread:
            self.flush_thread.join(timeout=2.0)

        # Final flush
        self._flush()

        # Write footers
        if footer_lines and self.file:
            for line in footer_lines:
                self.file.write(line + '\n')

        if self.file:
            self.file.close()
            self.file = None


# Recording state
recording_state = {
    'is_recording': False,
    'recorder': None,  # BufferedRecorder instance
    'session_start': None,
    'location': '',
    'notes': '',
    'samples_received': 0,
    'device_status': {}
}

def udp_listener():
    """Background thread to receive UDP data"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", UDP_PORT))
    sock.settimeout(1.0)
    
    while True:
        try:
            data, addr = sock.recvfrom(2048)
            decoded = data.decode('utf-8').strip()
            
            if decoded.startswith("BAT,"):
                parts = decoded.split(',')
                device_id = parts[1]  # Keep as string (4-char hex from MAC address)
                voltage = float(parts[2])
                percent = float(parts[3])
                recording_state['device_status'][device_id] = {
                    'voltage': voltage,
                    'percent': percent,
                    'last_seen': datetime.datetime.now().isoformat()
                }
            elif recording_state['is_recording'] and recording_state['recorder']:
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
                samples = decoded.split('|')
                for sample in samples:
                    if sample.strip() and not sample.startswith('BAT'):
                        recording_state['recorder'].append(f"{timestamp},{sample}\n")
                        recording_state['samples_received'] += 1
                
        except socket.timeout:
            continue
        except Exception as e:
            print(f"Error in UDP listener: {e}")

listener_thread = threading.Thread(target=udp_listener, daemon=True)
listener_thread.start()


def load_device_config():
    """Load device configuration from JSON file"""
    if DEVICE_CONFIG_FILE.exists():
        with open(DEVICE_CONFIG_FILE, 'r') as f:
            return json.load(f)
    # Return default config if file doesn't exist
    return {
        "devices": {},
        "positions": [
            {"id": "left_front", "label": "Left Front Leg"},
            {"id": "right_front", "label": "Right Front Leg"},
            {"id": "left_rear", "label": "Left Rear Leg"},
            {"id": "right_rear", "label": "Right Rear Leg"},
            {"id": "poll", "label": "Poll"},
            {"id": "withers", "label": "Withers"},
            {"id": "girth", "label": "Girth"}
        ]
    }


def save_device_config(config):
    """Save device configuration to JSON file"""
    with open(DEVICE_CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/sessions')
def sessions_page():
    return render_template('sessions.html')

@app.route('/view/<filename>')
def view_session(filename):
    return render_template('view_session.html', filename=filename)

@app.route('/api/status')
def status():
    """Get current recording status"""
    # Check device connection status (if no update in 60 seconds, mark disconnected)
    now = datetime.datetime.now()
    for device_id in list(recording_state['device_status'].keys()):
        last_seen_str = recording_state['device_status'][device_id]['last_seen']
        last_seen = datetime.datetime.fromisoformat(last_seen_str)
        seconds_since = (now - last_seen).total_seconds()
        
        recording_state['device_status'][device_id]['connected'] = (seconds_since < 60)
        recording_state['device_status'][device_id]['seconds_ago'] = int(seconds_since)
    
    response = {
        'is_recording': recording_state['is_recording'],
        'samples_received': recording_state['samples_received'],
        'device_status': recording_state['device_status'],
        'location': recording_state['location'],
        'notes': recording_state['notes']
    }
    
    if recording_state['session_start']:
        duration = (datetime.datetime.now() - recording_state['session_start']).total_seconds()
        response['duration'] = duration
    
    return jsonify(response)


@app.route('/api/device_config')
def get_device_config():
    """Get current device configuration"""
    return jsonify(load_device_config())


@app.route('/api/device_config', methods=['POST'])
def update_device_config():
    """Update device configuration"""
    config = request.json
    save_device_config(config)
    return jsonify({'success': True})


@app.route('/api/start', methods=['POST'])
def start_recording():
    if recording_state['is_recording']:
        return jsonify({'error': 'Already recording'}), 400

    data = request.json
    location = data.get('location', 'unknown')
    notes = data.get('notes', '')

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(DATA_DIR, f"session_{timestamp}.csv")

    # Create buffered recorder
    recorder = BufferedRecorder(filename, flush_interval_ms=500, buffer_size=1000)

    # Get current device config and embed in header
    device_config = load_device_config()

    # Prepare headers
    headers = [
        f"# Location: {location}",
        f"# Notes: {notes}",
        f"# Start Time: {datetime.datetime.now().isoformat()}",
        f"# Device Config: {json.dumps(device_config['devices'])}",
        "timestamp,device_id,sequence,accel_x,accel_y,accel_z"
    ]

    recorder.start(headers)

    recording_state['is_recording'] = True
    recording_state['recorder'] = recorder
    recording_state['session_start'] = datetime.datetime.now()
    recording_state['location'] = location
    recording_state['notes'] = notes
    recording_state['samples_received'] = 0

    return jsonify({
        'success': True,
        'filename': filename,
        'start_time': recording_state['session_start'].isoformat()
    })

@app.route('/api/stop', methods=['POST'])
def stop_recording():
    if not recording_state['is_recording']:
        return jsonify({'error': 'Not recording'}), 400

    recorder = recording_state['recorder']
    duration = (datetime.datetime.now() - recording_state['session_start']).total_seconds()
    samples = recording_state['samples_received']

    if recorder:
        footers = [
            f"# End Time: {datetime.datetime.now().isoformat()}",
            f"# Total Samples: {samples}"
        ]
        recorder.stop(footers)

    recording_state['is_recording'] = False
    recording_state['recorder'] = None
    recording_state['session_start'] = None

    return jsonify({
        'success': True,
        'duration': duration,
        'samples_recorded': samples
    })

@app.route('/api/sessions')
def list_sessions():
    sessions = []
    for filename in sorted(os.listdir(DATA_DIR), reverse=True):
        if filename.startswith('session_') and filename.endswith('.csv'):
            filepath = os.path.join(DATA_DIR, filename)
            
            # Parse metadata from file
            metadata = {}
            with open(filepath, 'r') as f:
                for line in f:
                    if line.startswith('# Location:'):
                        metadata['location'] = line.split(':', 1)[1].strip()
                    elif line.startswith('# Notes:'):
                        metadata['notes'] = line.split(':', 1)[1].strip()
                    elif line.startswith('# Start Time:'):
                        metadata['start_time'] = line.split(':', 1)[1].strip()
                    elif line.startswith('# Total Samples:'):
                        metadata['samples'] = line.split(':', 1)[1].strip()
                    elif not line.startswith('#'):
                        break
            
            stat = os.stat(filepath)
            sessions.append({
                'filename': filename,
                'size': stat.st_size,
                'modified': datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'metadata': metadata
            })
    return jsonify(sessions)

@app.route('/api/session_data/<filename>')
def get_session_data(filename):
    """Get accelerometer data for plotting (multi-device support)"""
    filepath = os.path.join(DATA_DIR, filename)

    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404

    with open(filepath, 'r') as f:
        lines = f.readlines()

    # Extract device config from header
    device_config = {}
    for line in lines:
        if line.startswith('# Device Config:'):
            try:
                config_json = line.split(':', 1)[1].strip()
                device_config = json.loads(config_json)
            except (json.JSONDecodeError, IndexError):
                pass
            break

    # Find where data starts
    data_start_idx = 0
    for i, line in enumerate(lines):
        if not line.startswith('#'):
            data_start_idx = i + 1
            break

    # Group data by device_id
    devices = {}
    sample_count = 0

    for line in lines[data_start_idx:]:
        if sample_count >= 10000:  # Limit to 10k points total
            break

        line = line.strip()
        if not line:
            continue

        parts = line.split(',')
        if len(parts) >= 6:  # timestamp,device_id,sequence,x,y,z
            try:
                timestamp = parts[0]
                device_id = parts[1]
                x = float(parts[3])
                y = float(parts[4])
                z = float(parts[5])
                mag = math.sqrt(x*x + y*y + z*z)

                if device_id not in devices:
                    devices[device_id] = {
                        'timestamps': [],
                        'accel_x': [],
                        'accel_y': [],
                        'accel_z': [],
                        'magnitude': [],
                        'config': device_config.get(device_id, {})
                    }

                devices[device_id]['timestamps'].append(timestamp)
                devices[device_id]['accel_x'].append(x)
                devices[device_id]['accel_y'].append(y)
                devices[device_id]['accel_z'].append(z)
                devices[device_id]['magnitude'].append(mag)
                sample_count += 1

            except (ValueError, IndexError) as e:
                print(f"Error parsing line: {line} - {e}")
                continue

    print(f"Loaded {sample_count} samples from {filename} across {len(devices)} devices")

    return jsonify({
        'devices': devices,
        'device_config': device_config,
        'sample_count': sample_count
    })


@app.route('/api/download/<filename>')
def download_session(filename):
    """Download raw CSV file"""
    filepath = os.path.join(DATA_DIR, filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    return jsonify({'error': 'File not found'}), 404


@app.route('/api/segment/<filename>')
def segment_session(filename):
    """Segment gait with configurable parameters"""
    filepath = os.path.join(DATA_DIR, filename)

    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404

    # Get parameters from query string
    movement_threshold = float(request.args.get('movement', 0.02))
    variance_threshold = float(request.args.get('variance', 2.0))
    frequency_threshold = float(request.args.get('frequency', 0.3))
    min_segment = float(request.args.get('min_segment', 2.0))

    # Load magnitude data
    magnitude = []

    with open(filepath, 'r') as f:
        lines = f.readlines()

    # Find where data starts
    data_start_idx = 0
    for i, line in enumerate(lines):
        if not line.startswith('#'):
            data_start_idx = i + 1
            break

    # Parse and calculate magnitude
    for line in lines[data_start_idx:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split(',')
        if len(parts) >= 6:
            try:
                x = float(parts[3])
                y = float(parts[4])
                z = float(parts[5])
                magnitude.append(math.sqrt(x*x + y*y + z*z))
            except (ValueError, IndexError):
                continue

    # Run segmentation
    segments = segment_gait(
        magnitude,
        sample_rate=194,
        movement_threshold=movement_threshold,
        variance_threshold=variance_threshold,
        frequency_threshold=frequency_threshold,
        min_segment_seconds=min_segment
    )

    return jsonify(segments)


# --- Cloud upload ---

upload_states = {}


def parse_csv_for_upload(filepath):
    """Parse a session CSV and return structured data for cloud upload."""
    filename = os.path.basename(filepath)
    # session_20250110_143000.csv -> 20250110_143000
    session_id = filename.replace('session_', '').replace('.csv', '')

    metadata = {
        'session_id': session_id,
        'location': '',
        'notes': '',
        'start_time': None,
        'end_time': None,
        'total_samples': 0,
        'device_config': '{}',
    }
    device_config = {}
    readings = []

    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('# Location:'):
                metadata['location'] = line.split(':', 1)[1].strip()
            elif line.startswith('# Notes:'):
                metadata['notes'] = line.split(':', 1)[1].strip()
            elif line.startswith('# Start Time:'):
                metadata['start_time'] = line.split(':', 1)[1].strip()
            elif line.startswith('# End Time:'):
                metadata['end_time'] = line.split(':', 1)[1].strip()
            elif line.startswith('# Total Samples:'):
                metadata['total_samples'] = int(line.split(':', 1)[1].strip())
            elif line.startswith('# Device Config:'):
                try:
                    config_json = line.split(':', 1)[1].strip()
                    device_config = json.loads(config_json)
                    metadata['device_config'] = config_json
                except (json.JSONDecodeError, IndexError):
                    pass
            elif line.startswith('#') or line.startswith('timestamp,'):
                continue
            elif line:
                parts = line.split(',')
                if len(parts) >= 6:
                    try:
                        device_id = parts[1]  # Keep as string (4-char hex from MAC address)
                        x = float(parts[3])
                        y = float(parts[4])
                        z = float(parts[5])
                        mag = math.sqrt(x * x + y * y + z * z)
                        seq = int(parts[2])
                        position = ''
                        if device_id in device_config:
                            position = device_config[device_id].get('position', '')

                        readings.append({
                            'session_id': session_id,
                            'device_id': device_id,
                            'position': position,
                            'sequence': seq,
                            'timestamp': parts[0].replace(' ', 'T', 1) + 'Z',
                            'accel_x': x,
                            'accel_y': y,
                            'accel_z': z,
                            'magnitude': mag,
                        })
                    except (ValueError, IndexError):
                        continue

    return session_id, metadata, device_config, readings


def _do_upload(filename, horse_name):
    """Background worker to upload a session to the cloud."""
    filepath = os.path.join(DATA_DIR, filename)
    upload_states[filename] = {'status': 'parsing', 'progress': 0, 'error': None}

    try:
        session_id, metadata, device_config, readings = parse_csv_for_upload(filepath)

        metadata['horse_name'] = horse_name or None
        metadata['uploaded_at'] = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ')

        # Normalize timestamps to RFC 3339 (required by Moose): 2026-02-22T20:30:33.848649Z
        for key in ('start_time', 'end_time'):
            if metadata.get(key):
                val = metadata[key]
                if 'T' not in val:
                    val = val.replace(' ', 'T', 1)
                if not val.endswith('Z'):
                    val = val + 'Z'
                metadata[key] = val

        upload_states[filename] = {'status': 'uploading_meta', 'progress': 5, 'error': None}

        headers = {}
        if CLOUD_API_KEY:
            headers['Authorization'] = f'Bearer {CLOUD_API_KEY}'
        headers['Content-Type'] = 'application/json'

        # Step 1: Upload session metadata
        resp = http_requests.post(
            f"{CLOUD_URL}/ingest/session-meta",
            json=metadata,
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()

        # Step 2: Upload sensor readings in chunks
        total = len(readings)
        chunk_size = 5000
        for i in range(0, total, chunk_size):
            chunk = readings[i:i + chunk_size]
            progress = 10 + int(85 * min(i + chunk_size, total) / max(total, 1))
            upload_states[filename] = {'status': 'uploading_readings', 'progress': progress, 'error': None}

            resp = http_requests.post(
                f"{CLOUD_URL}/ingest/sensor-reading",
                json=chunk,
                headers=headers,
                timeout=60,
            )
            resp.raise_for_status()

        upload_states[filename] = {'status': 'complete', 'progress': 100, 'error': None}

    except Exception as e:
        upload_states[filename] = {'status': 'error', 'progress': 0, 'error': str(e)}


@app.route('/api/cloud_status')
def cloud_status():
    """Check if cloud upload is configured."""
    configured = bool(CLOUD_URL and http_requests)
    return jsonify({'configured': configured, 'url': CLOUD_URL if configured else None})


@app.route('/api/upload/<filename>', methods=['POST'])
def upload_session(filename):
    """Start uploading a session to the cloud."""
    if not CLOUD_URL:
        return jsonify({'error': 'Cloud URL not configured'}), 400
    if not http_requests:
        return jsonify({'error': 'requests library not installed'}), 400

    filepath = os.path.join(DATA_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404

    if filename in upload_states and upload_states[filename]['status'] in ('parsing', 'uploading_meta', 'uploading_readings'):
        return jsonify({'error': 'Upload already in progress'}), 409

    data = request.json or {}
    horse_name = data.get('horse_name', '')

    thread = threading.Thread(target=_do_upload, args=(filename, horse_name), daemon=True)
    thread.start()

    return jsonify({'success': True, 'status': 'started'})


@app.route('/api/upload_status/<filename>')
def upload_status(filename):
    """Get upload progress for a session."""
    state = upload_states.get(filename, {'status': 'none', 'progress': 0, 'error': None})
    return jsonify(state)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=WEB_PORT, debug=False)