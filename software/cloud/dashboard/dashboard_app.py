"""
Cloud Dashboard for Lame Data
Queries Moose ConsumptionAPIs and renders analytics pages.
"""
import os
import json
from flask import Flask, render_template, request, jsonify
from pathlib import Path

try:
    import requests as http_requests
except ImportError:
    raise RuntimeError("requests library required: pip install requests")

SCRIPT_DIR = Path(__file__).parent
MOOSE_API_URL = os.getenv('MOOSE_API_URL', 'http://localhost:4000').rstrip('/')

app = Flask(__name__,
            template_folder=str(SCRIPT_DIR / 'templates'),
            static_folder=str(SCRIPT_DIR / 'static'))


def moose_get(endpoint, params=None):
    """Fetch from Moose consumption API."""
    url = f"{MOOSE_API_URL}/consumption/{endpoint}"
    resp = http_requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


# --- Page routes ---

@app.route('/')
def sessions_page():
    return render_template('sessions.html')


@app.route('/session/<session_id>')
def session_detail_page(session_id):
    return render_template('session_detail.html', session_id=session_id)


@app.route('/trends')
def trends_page():
    return render_template('trends.html')


# --- API proxy routes ---

@app.route('/api/sessions')
def api_sessions():
    params = {}
    if request.args.get('horse_name'):
        params['horse_name'] = request.args['horse_name']
    return jsonify(moose_get('sessions', params))


@app.route('/api/session-detail')
def api_session_detail():
    params = {'session_id': request.args['session_id']}
    if request.args.get('downsample'):
        params['downsample'] = request.args['downsample']
    return jsonify(moose_get('session-detail', params))


@app.route('/api/gait-analysis')
def api_gait_analysis():
    params = {
        'session_id': request.args['session_id'],
        'device_id': request.args['device_id'],
    }
    for k in ('movement', 'variance', 'frequency', 'min_segment'):
        if request.args.get(k):
            params[k] = request.args[k]
    return jsonify(moose_get('gait-analysis', params))


@app.route('/api/trends')
def api_trends():
    return jsonify(moose_get('trends', {'horse_name': request.args['horse_name']}))


@app.route('/api/asymmetry')
def api_asymmetry():
    return jsonify(moose_get('asymmetry', {'session_id': request.args['session_id']}))


if __name__ == '__main__':
    port = int(os.getenv('DASHBOARD_PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
