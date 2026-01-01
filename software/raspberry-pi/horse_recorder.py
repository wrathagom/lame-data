from flask import Flask, render_template, request, jsonify, send_file
import socket
import datetime
import os
import threading
import json
import csv
from pathlib import Path
from dotenv import load_dotenv

# Load configuration from .env file
SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR / '.env')

# Configuration from environment
UDP_PORT = int(os.getenv('UDP_PORT', 8888))
WEB_PORT = int(os.getenv('WEB_PORT', 5000))
DATA_DIR = os.getenv('DATA_DIR', str(SCRIPT_DIR / 'data'))

app = Flask(__name__,
          template_folder=str(SCRIPT_DIR / 'templates'),
          static_folder=str(SCRIPT_DIR / 'static'))

os.makedirs(DATA_DIR, exist_ok=True)

# Recording state
recording_state = {
    'is_recording': False,
    'session_file': None,
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
                device_id = int(parts[1])
                voltage = float(parts[2])
                percent = float(parts[3])
                recording_state['device_status'][device_id] = {
                    'voltage': voltage,
                    'percent': percent,
                    'last_seen': datetime.datetime.now().isoformat()
                }
            elif recording_state['is_recording'] and recording_state['session_file']:
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
                samples = decoded.split('|')
                for sample in samples:
                    if sample.strip() and not sample.startswith('BAT'):
                        recording_state['session_file'].write(f"{timestamp},{sample}\n")
                        recording_state['samples_received'] += 1
                recording_state['session_file'].flush()
                
        except socket.timeout:
            continue
        except Exception as e:
            print(f"Error in UDP listener: {e}")

listener_thread = threading.Thread(target=udp_listener, daemon=True)
listener_thread.start()

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


@app.route('/api/start', methods=['POST'])
def start_recording():
    if recording_state['is_recording']:
        return jsonify({'error': 'Already recording'}), 400
    
    data = request.json
    location = data.get('location', 'unknown')
    notes = data.get('notes', '')
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{DATA_DIR}session_{timestamp}_{location}.csv"
    
    session_file = open(filename, 'w')
    session_file.write(f"# Location: {location}\n")
    session_file.write(f"# Notes: {notes}\n")
    session_file.write(f"# Start Time: {datetime.datetime.now().isoformat()}\n")
    session_file.write("timestamp,device_id,sequence,accel_x,accel_y,accel_z\n")
    
    recording_state['is_recording'] = True
    recording_state['session_file'] = session_file
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
    
    if recording_state['session_file']:
        recording_state['session_file'].write(f"# End Time: {datetime.datetime.now().isoformat()}\n")
        recording_state['session_file'].write(f"# Total Samples: {recording_state['samples_received']}\n")
        recording_state['session_file'].close()
    
    duration = (datetime.datetime.now() - recording_state['session_start']).total_seconds()
    samples = recording_state['samples_received']
    
    recording_state['is_recording'] = False
    recording_state['session_file'] = None
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
    """Get accelerometer data for plotting"""
    filepath = os.path.join(DATA_DIR, filename)
    
    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404
    
    timestamps = []
    accel_x = []
    accel_y = []
    accel_z = []
    
    with open(filepath, 'r') as f:
        lines = f.readlines()
    
    # Find where data starts (after # comments and header line)
    data_start_idx = 0
    for i, line in enumerate(lines):
        if not line.startswith('#'):
            # This is the header line, data starts next line
            data_start_idx = i + 1
            break
    
    # Parse data lines
    sample_count = 0
    for line in lines[data_start_idx:]:
        if sample_count >= 10000:  # Limit to 10k points
            break
        
        line = line.strip()
        if not line:
            continue
            
        parts = line.split(',')
        if len(parts) >= 6:  # timestamp,device_id,sequence,x,y,z
            try:
                timestamps.append(parts[0])
                accel_x.append(float(parts[3]))  # x is column 3
                accel_y.append(float(parts[4]))  # y is column 4
                accel_z.append(float(parts[5]))  # z is column 5
                sample_count += 1
            except (ValueError, IndexError) as e:
                print(f"Error parsing line: {line} - {e}")
                continue
    
    print(f"Loaded {len(timestamps)} samples from {filename}")
    
    return jsonify({
        'timestamps': timestamps,
        'accel_x': accel_x,
        'accel_y': accel_y,
        'accel_z': accel_z,
        'sample_count': len(timestamps)
    })


@app.route('/api/download/<filename>')
def download_session(filename):
    """Download raw CSV file"""
    filepath = os.path.join(DATA_DIR, filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    return jsonify({'error': 'File not found'}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=WEB_PORT, debug=False)