#!/usr/bin/env python3
from flask import Flask, render_template_string, request, redirect, jsonify
import subprocess
import re
import os
import urllib.request

app = Flask(__name__)
CONFIG_FILE = '/home/hfss/ogn-rf/rtlsdr-ogn-0.3.2/HfssHq.conf'

# HTML Template
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>HfssHq OGN Manager</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { 
            font-family: Arial, sans-serif; 
            max-width: 800px; 
            margin: 50px auto; 
            padding: 20px;
            background: #f5f5f5;
        }
        .card {
            background: white;
            padding: 20px;
            margin: 20px 0;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 { color: #333; }
        h2 { color: #666; border-bottom: 2px solid #4CAF50; padding-bottom: 10px; }
        input, button {
            padding: 10px;
            margin: 5px 0;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 14px;
        }
        input { width: calc(100% - 22px); }
        button {
            background: #4CAF50;
            color: white;
            border: none;
            cursor: pointer;
            width: 100%;
            font-weight: bold;
        }
        button:hover { background: #45a049; }
        button:disabled { background: #ccc; cursor: not-allowed; }
        .status { 
            padding: 10px; 
            border-radius: 4px; 
            margin: 10px 0;
            font-size: 16px;
        }
        .status.running { background: #d4edda; color: #155724; }
        .status.stopped { background: #f8d7da; color: #721c24; }
        .current-config {
            background: #e7f3ff;
            padding: 15px;
            border-radius: 4px;
            font-family: monospace;
            line-height: 1.8;
        }
        .btn-group {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 10px;
        }
        .btn-restart { background: #ff9800; }
        .btn-restart:hover { background: #e68900; }
        .btn-stop { background: #f44336; }
        .btn-stop:hover { background: #da190b; }
        .btn-start { background: #4CAF50; }
        .btn-start:hover { background: #45a049; }
        iframe {
            width: 100%;
            height: 600px;
            border: 1px solid #ddd;
            border-radius: 4px;
            background: white;
        }
        .info { font-size: 12px; color: #666; margin-top: 5px; }
        .links { text-align: center; margin-top: 10px; }
        .links a { margin: 0 10px; }
        #iframeError {
            padding: 20px;
            background: #fff3cd;
            border-radius: 4px;
            text-align: center;
            display: none;
        }
        .refresh-btn {
            width: auto !important;
            padding: 8px 15px !important;
            float: right;
        }
    </style>
</head>
<body>
    <h1>🛩️ HfssHq OGN Station Manager</h1>
    
    <div class="card">
        <h2>Service Control</h2>
        <div class="status {{ status_class }}">
            Status: <strong>{{ status }}</strong>
        </div>
        <div class="btn-group">
            <form action="/restart" method="post" style="margin:0;">
                <button type="submit" class="btn-restart">🔄 Restart</button>
            </form>
            <form action="/stop" method="post" style="margin:0;">
                <button type="submit" class="btn-stop">⏹️ Stop</button>
            </form>
            <form action="/start" method="post" style="margin:0;">
                <button type="submit" class="btn-start">▶️ Start</button>
            </form>
        </div>
    </div>

    <div class="card">
        <h2>Current Configuration</h2>
        <div class="current-config">
            <strong>Station:</strong> {{ current.call }}<br>
            <strong>Latitude:</strong> {{ current.lat }}°<br>
            <strong>Longitude:</strong> {{ current.lon }}°<br>
            <strong>Altitude:</strong> {{ current.alt }} m AMSL<br>
            <strong>Freq Correction:</strong> {{ current.freqcorr }} ppm
        </div>
    </div>

    <div class="card">
        <h2>Update Configuration</h2>
        <form method="post" action="/update">
            <label>Station Name (max 9 chars):</label>
            <input type="text" name="call" value="{{ current.call }}" maxlength="9" required>
            <div class="info">CamelCase format recommended (e.g., HfssHq, Cannobio)</div>
            
            <label>Latitude (decimal degrees):</label>
            <input type="number" step="0.000001" name="lat" value="{{ current.lat }}" required>
            <div class="info">Example: 45.97317</div>
            
            <label>Longitude (decimal degrees):</label>
            <input type="number" step="0.000001" name="lon" value="{{ current.lon }}" required>
            <div class="info">Example: 8.87512</div>
            
            <label>Altitude (meters AMSL):</label>
            <input type="number" name="alt" value="{{ current.alt }}" required>
            <div class="info">Altitude above mean sea level</div>
            
            <label>Frequency Correction (ppm):</label>
            <input type="number" name="freqcorr" value="{{ current.freqcorr }}" required>
            <div class="info">Run gsm_scan to calibrate (default: 50 for R820T2)</div>
            
            <button type="submit">💾 Save & Restart Service</button>
        </form>
    </div>

    <div class="card">
        <h2>OGN Decoder Status</h2>
        <p>Live status from ogn-decode (port 8081):</p>
        <button onclick="refreshIframe()" class="refresh-btn">🔄 Refresh</button>
        <div style="clear:both; margin-bottom: 10px;"></div>
        <iframe id="statusFrame" src="/status-proxy"></iframe>
        <div id="iframeError">
            ⚠️ Status page not loading. RTL-SDR may not be connected.<br>
            <a href="http://{{ hostname }}:8081" target="_blank" style="font-weight: bold;">Open in new tab</a>
        </div>
        <div class="links">
            <a href="http://{{ hostname }}:8081" target="_blank">📊 Status Page</a> |
            <a href="http://live.glidernet.org/" target="_blank">🌍 OGN Live Map</a> |
            <a href="http://{{ hostname }}:8082" target="_blank">⚙️ Reload Manager</a>
        </div>
    </div>

    <div class="card">
        <h2>Quick Info</h2>
        <p>
            <strong>Hostname:</strong> {{ hostname }}<br>
            <strong>Manager:</strong> http://{{ hostname }}:8082<br>
            <strong>OGN Status:</strong> http://{{ hostname }}:8081<br>
            <strong>SSH:</strong> <code>ssh hfss@{{ hostname }}.local</code><br>
            <strong>Station on Map:</strong> <a href="http://live.glidernet.org/" target="_blank">Search for "{{ current.call }}"</a>
        </p>
    </div>

    <script>
        // Auto-refresh status after button click
        const forms = document.querySelectorAll('form[action^="/"]');
        forms.forEach(form => {
            form.addEventListener('submit', function() {
                const buttons = document.querySelectorAll('button');
                buttons.forEach(btn => {
                    btn.disabled = true;
                    btn.textContent = '⏳ Processing...';
                });
                // Reload page after 2 seconds
                setTimeout(() => {
                    window.location.reload();
                }, 2000);
            });
        });
        
        // Iframe handling
        function refreshIframe() {
            const iframe = document.getElementById('statusFrame');
            iframe.src = iframe.src + '?t=' + new Date().getTime();
        }
        
        // Auto-refresh iframe every 30 seconds
        setInterval(refreshIframe, 30000);
        
        // Auto-refresh page status every 10 seconds
        setInterval(() => {
            fetch('/')
                .then(response => response.text())
                .then(html => {
                    const parser = new DOMParser();
                    const doc = parser.parseFromString(html, 'text/html');
                    const newStatus = doc.querySelector('.status');
                    const currentStatus = document.querySelector('.status');
                    if (newStatus && currentStatus) {
                        currentStatus.innerHTML = newStatus.innerHTML;
                        currentStatus.className = newStatus.className;
                    }
                });
        }, 10000);
    </script>
</body>
</html>
'''

def read_config():
    """Read current configuration from file"""
    config = {
        'call': 'HfssHq',
        'lat': '45.97317',
        'lon': '8.87512',
        'alt': '210',
        'freqcorr': '50'
    }
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            content = f.read()
            
        # Extract values using regex
        call_match = re.search(r'Call\s*=\s*"([^"]+)"', content)
        lat_match = re.search(r'Latitude\s*=\s*([+-]?\d+\.?\d*)', content)
        lon_match = re.search(r'Longitude\s*=\s*([+-]?\d+\.?\d*)', content)
        alt_match = re.search(r'Altitude\s*=\s*(\d+)', content)
        freq_match = re.search(r'FreqCorr\s*=\s*([+-]?\d+)', content)
        
        if call_match: config['call'] = call_match.group(1)
        if lat_match: config['lat'] = lat_match.group(1)
        if lon_match: config['lon'] = lon_match.group(1)
        if alt_match: config['alt'] = alt_match.group(1)
        if freq_match: config['freqcorr'] = freq_match.group(1)
    except:
        pass
    
    return config

def update_config(call, lat, lon, alt, freqcorr):
    """Update configuration file"""
    try:
        with open(CONFIG_FILE, 'r') as f:
            content = f.read()
        
        # Update values
        content = re.sub(r'Call\s*=\s*"[^"]*"', f'Call = "{call}"', content)
        content = re.sub(r'(#\s*)?Call\s*=\s*"[^"]*"', f'Call = "{call}"', content)
        content = re.sub(r'Latitude\s*=\s*[+-]?\d+\.?\d*', f'Latitude   =  +{lat}', content)
        content = re.sub(r'Longitude\s*=\s*[+-]?\d+\.?\d*', f'Longitude  =   +{lon}', content)
        content = re.sub(r'Altitude\s*=\s*\d+', f'Altitude   =        {alt}', content)
        content = re.sub(r'FreqCorr\s*=\s*[+-]?\d+', f'FreqCorr = +{freqcorr}', content)
        
        # Backup old config
        subprocess.run(['cp', CONFIG_FILE, CONFIG_FILE + '.bak'])
        
        # Write new config
        with open(CONFIG_FILE, 'w') as f:
            f.write(content)
        
        return True
    except Exception as e:
        print(f"Error updating config: {e}")
        return False

def get_service_status():
    """Check if service is running"""
    try:
        result = subprocess.run(['systemctl', 'is-active', 'rtlsdr-ogn'], 
                              capture_output=True, text=True)
        return result.stdout.strip() == 'active'
    except:
        return False


@app.route('/')
def index():
    status = "Running ✅" if get_service_status() else "Stopped ⏹️"
    status_class = "running" if get_service_status() else "stopped"
    current = read_config()
    
    # Get the hostname with .local
    hostname = subprocess.run(['hostname'], capture_output=True, text=True).stdout.strip()
    
    # If accessing via IP, use that, otherwise use hostname.local
    if request.host:
        hostname = request.host.split(':')[0]  # Get host without port
    elif hostname:
        hostname = hostname + '.local'
    
    return render_template_string(HTML_TEMPLATE, 
                                 status=status, 
                                 status_class=status_class,
                                 current=current,
                                 hostname=hostname)


@app.route('/status-proxy')
def status_proxy():
    """Proxy the status page to avoid CORS issues"""
    try:
        with urllib.request.urlopen('http://localhost:8081', timeout=5) as response:
            content = response.read().decode('utf-8')
            return content
    except Exception as e:
        return f"""
        <html>
        <body style="font-family: Arial; padding: 40px; text-align: center;">
            <h2>⚠️ OGN Decoder Status Not Available</h2>
            <p>The decoder may not be running or the RTL-SDR dongle is not connected.</p>
            <p style="color: #666;">Error: {str(e)}</p>
            <p><a href="http://localhost:8081" target="_blank">Try opening port 8081 directly</a></p>
        </body>
        </html>
        """

@app.route('/update', methods=['POST'])
def update():
    call = request.form['call']
    lat = request.form['lat']
    lon = request.form['lon']
    alt = request.form['alt']
    freqcorr = request.form['freqcorr']
    
    if update_config(call, lat, lon, alt, freqcorr):
        # Restart service
        subprocess.run(['sudo', 'systemctl', 'restart', 'rtlsdr-ogn'])
    
    return redirect('/')

@app.route('/restart', methods=['POST'])
def restart():
    subprocess.run(['sudo', 'systemctl', 'restart', 'rtlsdr-ogn'])
    return redirect('/')

@app.route('/stop', methods=['POST'])
def stop():
    subprocess.run(['sudo', 'systemctl', 'stop', 'rtlsdr-ogn'])
    return redirect('/')

@app.route('/start', methods=['POST'])
def start():
    subprocess.run(['sudo', 'systemctl', 'start', 'rtlsdr-ogn'])
    return redirect('/')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8082, debug=False)

