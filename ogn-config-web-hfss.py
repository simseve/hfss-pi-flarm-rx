#!/usr/bin/env python3
"""
OGN Config Web + HFSS Registration
Enhanced Flask app with HFSS integration for Pi 3
"""
from flask import Flask, render_template_string, request, jsonify
import re
import subprocess
import os
import json
import hmac
import hashlib
import requests
import threading
import time
from datetime import datetime

app = Flask(__name__)
CONFIG_FILE = '/home/hfss/ogn-pi34/rtlsdr-ogn-0.3.2/Template.conf'
WPA_SUPPLICANT = '/etc/wpa_supplicant/wpa_supplicant.conf'
CREDENTIALS_FILE = '/home/hfss/.ogn_credentials.json'
ENV_FILE = '/home/hfss/hfss-pi-flarm-rx/.env'
HEARTBEAT_LOG_FILE = '/home/hfss/.ogn_heartbeat_log.json'

# HFSS Configuration
HEARTBEAT_INTERVAL = 300  # 5 minutes
heartbeat_thread = None
heartbeat_running = False
heartbeat_history = []  # Store last 1000 heartbeats

# Load environment variables from .env
def load_env_var(var_name):
    try:
        if os.path.exists(ENV_FILE):
            with open(ENV_FILE, 'r') as f:
                for line in f:
                    if line.startswith(f'{var_name}='):
                        return line.split('=', 1)[1].strip()
    except:
        pass
    return None

def get_cloudflare_headers():
    """Get Cloudflare Access service token headers if configured"""
    headers = {}
    client_id = load_env_var('CF_ACCESS_CLIENT_ID')
    client_secret = load_env_var('CF_ACCESS_CLIENT_SECRET')

    if client_id and client_secret:
        headers['CF-Access-Client-Id'] = client_id
        headers['CF-Access-Client-Secret'] = client_secret

    return headers

def get_raspberry_pi_serial():
    """Get Raspberry Pi CPU serial number"""
    try:
        with open('/proc/cpuinfo', 'r') as f:
            for line in f:
                if line.startswith('Serial'):
                    return line.split(':')[1].strip()[-8:]  # Last 8 chars
    except:
        pass
    return 'UNKNOWN'

def get_tailscale_ip():
    """Get Tailscale IP address if available"""
    try:
        result = subprocess.run(
            ['tailscale', 'ip', '-4'],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except:
        pass
    return None

def get_default_hfss_config():
    """Get default HFSS configuration with auto-populated values"""
    config = read_config()
    serial = get_raspberry_pi_serial()

    return {
        'server_url': load_env_var('HFSS_SERVER_URL') or 'https://app.alpium.io',
        'station_id': f'OGN_STATION_{serial}',
        'station_name': config.get('call', 'NOCALL'),
        'manufacturer_secret': load_env_var('MANUFACTURER_SECRET_OGN') or ''
    }

# HTML Template with Neon Cyberpunk Styling
HTML = '''<!DOCTYPE html>
<html><head><title>OGN Config - Alpium</title><meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700;900&family=Rajdhani:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Rajdhani',sans-serif;background:#0a0e1a;color:#fff;padding:20px;min-height:100vh}
h1,h2,h3{font-family:'Orbitron',monospace;letter-spacing:1px}
.container{max-width:1200px;margin:0 auto;background:rgba(15,20,32,0.95);border-radius:12px;box-shadow:0 0 40px rgba(0,255,255,0.15);border:1px solid rgba(0,255,255,0.2);overflow:hidden}
.header{background:linear-gradient(135deg,rgba(15,20,32,0.98),rgba(20,26,40,0.98));color:#00ffff;padding:24px;border-bottom:2px solid rgba(0,255,255,0.3);position:relative}
.header::after{content:'';position:absolute;bottom:0;left:0;right:0;height:2px;background:linear-gradient(90deg,transparent,#00ffff,transparent);animation:glow-line 3s ease-in-out infinite}
.header h1{font-size:28px;margin-bottom:5px;text-shadow:0 0 20px rgba(0,255,255,0.8),0 0 40px rgba(0,255,255,0.4)}
.content{padding:24px}
.form-section{background:rgba(20,26,40,0.6);padding:24px;border-radius:10px;margin-bottom:24px;border:1px solid rgba(0,255,255,0.2);transition:all 0.3s ease}
.form-section:hover{border-color:rgba(0,255,255,0.4);box-shadow:0 0 20px rgba(0,255,255,0.1)}
.form-section h2{font-size:22px;margin-bottom:20px;color:#00ffff;text-shadow:0 0 10px rgba(0,255,255,0.6)}
.form-group{margin-bottom:18px}
.form-group label{display:block;margin-bottom:8px;font-weight:600;color:#00a6fb;font-size:14px;text-transform:uppercase;letter-spacing:0.5px}
.form-group input,.form-group select{width:100%;padding:12px;border:1px solid rgba(0,166,251,0.3);border-radius:6px;font-size:14px;background:rgba(10,14,26,0.8);color:#fff;font-family:'Rajdhani',sans-serif;transition:all 0.3s ease}
.form-group input:focus,.form-group select:focus{outline:none;border-color:#00ffff;box-shadow:0 0 15px rgba(0,255,255,0.3)}
.btn{background:linear-gradient(135deg,#00a6fb,#0080c8);color:#fff;padding:12px 28px;border:none;border-radius:6px;cursor:pointer;font-size:16px;margin-right:12px;font-weight:700;text-transform:uppercase;letter-spacing:1px;transition:all 0.3s ease;font-family:'Orbitron',monospace}
.btn:hover{transform:translateY(-2px);box-shadow:0 0 25px rgba(0,166,251,0.6);background:linear-gradient(135deg,#00c0ff,#00a6fb)}
.btn-danger{background:linear-gradient(135deg,#ff006e,#c8005a)}
.btn-danger:hover{box-shadow:0 0 25px rgba(255,0,110,0.6);background:linear-gradient(135deg,#ff2080,#ff006e)}
.btn-success{background:linear-gradient(135deg,#14f195,#0ac97a)}
.btn-success:hover{box-shadow:0 0 25px rgba(20,241,149,0.6);background:linear-gradient(135deg,#20ff9e,#14f195)}
.status{padding:16px;border-radius:8px;margin-bottom:20px;border:1px solid;font-weight:600}
.status.success{background:rgba(20,241,149,0.1);color:#14f195;border-color:rgba(20,241,149,0.3)}
.status.error{background:rgba(255,0,110,0.1);color:#ff006e;border-color:rgba(255,0,110,0.3)}
.info-box{background:rgba(0,166,251,0.05);border-left:4px solid #00a6fb;padding:16px;margin-bottom:20px;border-radius:6px}
.info-box strong{color:#00ffff}
iframe{width:100%;height:600px;border:1px solid rgba(0,255,255,0.2);border-radius:8px;margin-top:20px;background:#f5f5f5}
.wifi-status{display:inline-block;padding:6px 12px;border-radius:6px;font-weight:700;font-size:13px;text-transform:uppercase;letter-spacing:0.5px}
.wifi-on{background:rgba(20,241,149,0.2);color:#14f195;border:1px solid rgba(20,241,149,0.4)}
.wifi-off{background:rgba(255,0,110,0.2);color:#ff006e;border:1px solid rgba(255,0,110,0.4)}
.network-list{list-style:none;padding:0}
.network-item{background:rgba(20,26,40,0.5);padding:16px;margin:12px 0;border:1px solid rgba(0,166,251,0.2);border-radius:8px;display:flex;justify-content:space-between;align-items:center;transition:all 0.3s ease}
.network-item:hover{border-color:rgba(0,255,255,0.4);box-shadow:0 0 15px rgba(0,255,255,0.1)}
.network-item .network-info{flex:1}
.network-item .network-ssid{font-weight:700;color:#00ffff;font-size:16px}
.network-item .network-status{font-size:12px;color:#adb5bd;margin-top:4px}
.btn-small{padding:8px 18px;font-size:13px}
.hfss-status{padding:12px;border-radius:8px;margin:12px 0;font-weight:700;text-transform:uppercase;letter-spacing:1px;border:2px solid}
.hfss-registered{background:rgba(20,241,149,0.1);color:#14f195;border-color:rgba(20,241,149,0.4);animation:pulse-glow 2s ease-in-out infinite}
.hfss-notregistered{background:rgba(153,69,255,0.1);color:#9945ff;border-color:rgba(153,69,255,0.4)}
@keyframes glow-line{0%,100%{opacity:0.5;transform:scaleX(0.8)}50%{opacity:1;transform:scaleX(1)}}
@keyframes pulse-glow{0%,100%{box-shadow:0 0 10px rgba(20,241,149,0.3)}50%{box-shadow:0 0 20px rgba(20,241,149,0.6)}}
</style>
</head><body><div class="container"><div class="header"><h1>⚡ OGN Receiver Configuration - Alpium</h1></div>
<div class="content"><div id="status"></div>

<div class="form-section">
<h2>Alpium Registration</h2>
<div class="hfss-status {{hfss.status_class}}">Status: {{hfss.status_text}}</div>
{% if hfss.is_registered %}
<div class="info-box">
<strong>Station ID:</strong> {{hfss.station_id}}<br>
<strong>Server:</strong> {{hfss.server_url}}<br>
<strong>Last Heartbeat:</strong> {{hfss.last_heartbeat}}<br>
<strong>Heartbeat:</strong> {{hfss.heartbeat_status}}
</div>
<button class="btn" onclick="viewHeartbeatLogs()">View Heartbeat Logs</button>
<button class="btn btn-danger" onclick="unregisterHFSS()">Unregister</button>
<div id="heartbeat-logs" style="display:none;margin-top:20px;">
<h3 style="color:#00ffff;font-size:18px;margin-bottom:12px;">Heartbeat Logs (Last 1000)</h3>
<div id="logs-container" style="max-height:400px;overflow-y:auto;background:rgba(10,14,26,0.6);padding:12px;border-radius:8px;font-family:monospace;font-size:12px;border:1px solid rgba(0,166,251,0.2);"></div>
</div>
{% else %}
<form id="hfssForm">
<div class="form-group"><label>Server URL</label><input name="server_url" value="{{hfss_defaults.server_url}}" required></div>
<div class="form-group"><label>Station ID</label><input name="station_id" value="{{hfss_defaults.station_id}}" pattern="^OGN_STATION_.+" required readonly></div>
<div class="form-group"><label>Station Name</label><input name="station_name" value="{{hfss_defaults.station_name}}" required></div>
<div class="form-group"><label>Manufacturer Secret</label><input type="password" name="manufacturer_secret" value="{{hfss_defaults.manufacturer_secret}}" required></div>
<button type="submit" class="btn">Register with Alpium</button>
</form>
{% endif %}
</div>

<div class="form-section">
<h2>WiFi Management</h2>
<div class="info-box">
<strong>WiFi Status:</strong> <span class="wifi-status wifi-{{wifi.wlan0_status}}">wlan0: {{wifi.wlan0_status|upper}}</span>
<span class="wifi-status wifi-{{wifi.eth1_status}}">eth1: {{wifi.eth1_status|upper}}</span><br>
<strong>Active IP:</strong> wlan0: {{wifi.wlan0_ip}} | eth1: {{wifi.eth1_ip}}
</div>
<button class="btn btn-danger" onclick="toggleWifi('wlan0','off')">Turn OFF wlan0</button>
<button class="btn btn-success" onclick="toggleWifi('wlan0','on')">Turn ON wlan0</button>
<button class="btn btn-danger" onclick="toggleWifi('eth1','off')">Turn OFF eth1</button>
<button class="btn btn-success" onclick="toggleWifi('eth1','on')">Turn ON eth1</button>
</div>

<div class="form-section">
<h2>WiFi Networks (wlan0)</h2>
<ul class="network-list">
{% for net in wifi.networks %}
<li class="network-item">
<div class="network-info">
<div class="network-ssid">{{net.ssid}}</div>
<div class="network-status">{{net.status}}</div>
</div>
<button class="btn btn-small" onclick="editNetwork('{{net.id}}','{{net.ssid}}')">Edit</button>
<button class="btn btn-small btn-danger" onclick="deleteNetwork('{{net.id}}')">Delete</button>
</li>
{% endfor %}
</ul>
<h3 style="margin-top:20px">Add New Network</h3>
<form id="wifiForm">
<div class="form-group"><label>SSID</label><input name="ssid" required></div>
<div class="form-group"><label>Password</label><input type="password" name="psk" required></div>
<div class="form-group"><label>Priority (higher = preferred)</label><input type="number" name="priority" value="1"></div>
<button type="submit" class="btn">Add Network</button>
</form>
</div>

<div class="info-box"><strong>Station:</strong> {{config.call}}<br><strong>Location:</strong> {{config.latitude}}, {{config.longitude}} @ {{config.altitude}}m</div>
<form id="f"><div class="form-section"><h2>Station</h2>
<div class="form-group"><label>Callsign</label><input name="call" value="{{config.call}}" maxlength="9" required></div></div>
<div class="form-section"><h2>Location</h2>
<div class="form-group"><label>Latitude</label><input type="number" name="latitude" value="{{config.latitude}}" step="0.000001" required></div>
<div class="form-group"><label>Longitude</label><input type="number" name="longitude" value="{{config.longitude}}" step="0.000001" required></div>
<div class="form-group"><label>Altitude (m)</label><input type="number" name="altitude" value="{{config.altitude}}" required></div></div>
<div class="form-section"><h2>RF</h2>
<div class="form-group"><label>Freq Correction (PPM)</label><input type="number" name="freqcorr" value="{{config.freqcorr}}" step="0.1"></div>
<div class="form-group"><label>Center Freq (MHz)</label><input type="number" name="centerfreq" value="{{config.centerfreq}}" step="0.1"></div>
<div class="form-group"><label>Gain (dB)</label><input type="number" name="gain" value="{{config.gain}}" step="0.1"></div></div>
<button type="submit" class="btn" id="b">Save & Restart</button></form>
<iframe src="http://{{ip}}:8080"></iframe></div></div>
<script>
async function toggleWifi(iface,action){
const r=await fetch('/api/wifi/toggle',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({interface:iface,action:action})});
const j=await r.json();document.getElementById('status').innerHTML='<div class="status '+(j.success?'success':'error')+'">'+j.message+'</div>';
if(j.success)setTimeout(()=>location.reload(),2000);
}
async function deleteNetwork(id){
if(!confirm('Delete this network?'))return;
const r=await fetch('/api/wifi/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({network_id:id})});
const j=await r.json();document.getElementById('status').innerHTML='<div class="status '+(j.success?'success':'error')+'">'+j.message+'</div>';
if(j.success)setTimeout(()=>location.reload(),1500);
}
function editNetwork(id,ssid){
const psk=prompt('Enter new password for '+ssid+':');
if(!psk)return;
fetch('/api/wifi/edit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({network_id:id,psk:psk})})
.then(r=>r.json()).then(j=>{document.getElementById('status').innerHTML='<div class="status '+(j.success?'success':'error')+'">'+j.message+'</div>';
if(j.success)setTimeout(()=>location.reload(),1500);});
}
async function unregisterHFSS(){
if(!confirm('Unregister from Alpium? Heartbeat will stop.'))return;
const r=await fetch('/api/hfss/unregister',{method:'POST'});
const j=await r.json();document.getElementById('status').innerHTML='<div class="status '+(j.success?'success':'error')+'">'+j.message+'</div>';
if(j.success)setTimeout(()=>location.reload(),1500);
}
async function viewHeartbeatLogs(){
const container=document.getElementById('heartbeat-logs');
if(container.style.display==='none'){
const r=await fetch('/api/hfss/heartbeat-logs');
const j=await r.json();
if(j.success){
const logsDiv=document.getElementById('logs-container');
logsDiv.innerHTML='';
j.logs.reverse().forEach(log=>{
const entry=document.createElement('div');
entry.style.cssText='margin-bottom:15px;padding:12px;background:rgba(20,26,40,0.5);border-radius:8px;border:1px solid rgba(0,166,251,0.2)';
const statusColor=log.response_status===200?'#14f195':log.response_status===0?'#9945ff':'#ff006e';
const toggleId='log-'+Math.random().toString(36).substr(2,9);
const header=document.createElement('div');
header.style.marginBottom='10px';
header.innerHTML='<strong style="color:'+statusColor+'">'+log.timestamp+'</strong> - <span style="font-weight:bold;color:'+statusColor+'">Status: '+log.response_status+'</span>';
const btn=document.createElement('button');
btn.className='btn btn-small';
btn.textContent='Toggle Details';
btn.onclick=function(){const d=document.getElementById(toggleId);d.style.display=d.style.display==='none'?'block':'none'};
const details=document.createElement('div');
details.id=toggleId;
details.style.cssText='display:none;margin-top:10px';
const payloadPre=document.createElement('pre');
payloadPre.style.cssText='background:rgba(10,14,26,0.8);padding:10px;border-radius:6px;overflow-x:auto;font-size:11px;color:#adb5bd;border:1px solid rgba(0,166,251,0.2)';
payloadPre.textContent=JSON.stringify(log.payload,null,2);
const respPre=document.createElement('pre');
respPre.style.cssText='background:rgba(10,14,26,0.8);padding:10px;border-radius:6px;overflow-x:auto;font-size:11px;margin-top:10px;color:#adb5bd;border:1px solid rgba(0,166,251,0.2)';
respPre.textContent=log.response_text;
details.innerHTML='<strong style="color:#00a6fb;">Payload:</strong>';
details.appendChild(payloadPre);
details.innerHTML+='<strong style="color:#00a6fb;display:block;margin-top:12px;">Response:</strong>';
details.appendChild(respPre);
entry.appendChild(header);
entry.appendChild(btn);
entry.appendChild(details);
logsDiv.appendChild(entry);
});
container.style.display='block';
}else{
alert('Failed to load logs: '+j.message);
}
}else{
container.style.display='none';
}
}
document.getElementById('wifiForm').onsubmit=async(e)=>{e.preventDefault();
const d=Object.fromEntries(new FormData(e.target));
const r=await fetch('/api/wifi/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});
const j=await r.json();document.getElementById('status').innerHTML='<div class="status '+(j.success?'success':'error')+'">'+j.message+'</div>';
if(j.success){e.target.reset();setTimeout(()=>location.reload(),1500);}
};
if(document.getElementById('hfssForm')){
document.getElementById('hfssForm').onsubmit=async(e)=>{e.preventDefault();
const d=Object.fromEntries(new FormData(e.target));
const r=await fetch('/api/hfss/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});
const j=await r.json();document.getElementById('status').innerHTML='<div class="status '+(j.success?'success':'error')+'">'+j.message+'</div>';
if(j.success)setTimeout(()=>location.reload(),2000);
};
}
document.getElementById('f').onsubmit=async(e)=>{e.preventDefault();document.getElementById('b').disabled=true;
const d=Object.fromEntries(new FormData(e.target));
try{const r=await fetch('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});
const j=await r.json();document.getElementById('status').innerHTML='<div class="status '+(j.success?'success':'error')+'">'+j.message+'</div>';
if(j.success)setTimeout(()=>location.reload(),2000);}catch(e){document.getElementById('status').innerHTML='<div class="status error">Error: '+e.message+'</div>';}
document.getElementById('b').disabled=false;};
</script></body></html>'''

def read_config():
    config = {'call':'NOCALL','latitude':0.0,'longitude':0.0,'altitude':0,'freqcorr':0.0,'centerfreq':868.2,'gain':40.0}
    try:
        with open(CONFIG_FILE,'r') as f:content=f.read()
        if m:=re.search(r'Call = "([^"]+)"',content):config['call']=m.group(1)
        if m:=re.search(r'Latitude\s*=\s*([\d.-]+)',content):config['latitude']=float(m.group(1))
        if m:=re.search(r'Longitude\s*=\s*([\d.-]+)',content):config['longitude']=float(m.group(1))
        if m:=re.search(r'Altitude\s*=\s*([\d.-]+)',content):config['altitude']=int(float(m.group(1)))
        if m:=re.search(r'FreqCorr\s*=\s*([+\d.-]+)',content):config['freqcorr']=float(m.group(1))
        if m:=re.search(r'OGN:.*?CenterFreq\s*=\s*([\d.]+)',content,re.DOTALL):config['centerfreq']=float(m.group(1))
        if m:=re.search(r'OGN:.*?Gain\s*=\s*([\d.]+)',content,re.DOTALL):config['gain']=float(m.group(1))
    except:pass
    return config

def write_config(d):
    cfg=f'''RF:
{{
  FreqCorr = {d['freqcorr']};
  GSM: {{ CenterFreq = 950.0; Gain = 30.0; }};
  OGN: {{ CenterFreq = {d['centerfreq']}; Gain = {d['gain']}; }};
}};

Position:
{{
  Latitude   =  {d['latitude']};
  Longitude  =  {d['longitude']};
  Altitude   =  {d['altitude']};
}};

APRS:
{{
  Call = "{d['call']}";
  Server = "aprs.glidernet.org:14580";
}};

HTTP:
{{
  Port = 8080;
}};
'''
    try:
        with open(CONFIG_FILE,'w') as f:f.write(cfg)
        return True
    except:return False

def get_ip():
    try:return subprocess.run(['hostname','-I'],capture_output=True,text=True).stdout.strip().split()[0]
    except:return 'localhost'

def get_wifi_status():
    status = {'wlan0_status':'unknown','eth1_status':'unknown','wlan0_ip':'N/A','eth1_ip':'N/A','networks':[]}
    try:
        result = subprocess.run(['ip','link','show','wlan0'],capture_output=True,text=True)
        status['wlan0_status'] = 'on' if 'state UP' in result.stdout else 'off'
        result = subprocess.run(['ip','link','show','eth1'],capture_output=True,text=True)
        status['eth1_status'] = 'on' if 'state UP' in result.stdout else 'off'
        result = subprocess.run(['ip','addr','show','wlan0'],capture_output=True,text=True)
        if m:=re.search(r'inet ([\d.]+)',result.stdout):status['wlan0_ip']=m.group(1)
        result = subprocess.run(['ip','addr','show','eth1'],capture_output=True,text=True)
        if m:=re.search(r'inet ([\d.]+)',result.stdout):status['eth1_ip']=m.group(1)
        if os.path.exists(WPA_SUPPLICANT):
            with open(WPA_SUPPLICANT,'r') as f:content=f.read()
            networks = re.findall(r'network=\{([^}]+)\}',content,re.DOTALL)
            for i,net in enumerate(networks):
                ssid = re.search(r'ssid="([^"]+)"',net)
                priority = re.search(r'priority=(\d+)',net)
                if ssid:
                    status['networks'].append({
                        'id':i,
                        'ssid':ssid.group(1),
                        'status':f"Priority: {priority.group(1) if priority else '0'}"
                    })
    except:pass
    return status

def read_wpa_networks():
    networks = []
    try:
        if os.path.exists(WPA_SUPPLICANT):
            with open(WPA_SUPPLICANT,'r') as f:content=f.read()
            networks = re.findall(r'network=\{([^}]+)\}',content,re.DOTALL)
    except:pass
    return networks

def write_wpa_config(networks):
    header = '''ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=CH

'''
    try:
        with open(WPA_SUPPLICANT,'w') as f:
            f.write(header)
            for net in networks:
                f.write(f'network={{{net}}}\n\n')
        subprocess.run(['sudo','wpa_cli','-i','wlan0','reconfigure'],check=False)
        return True
    except:return False

# HFSS Functions
def load_credentials():
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return None

def save_credentials(creds):
    try:
        with open(CREDENTIALS_FILE, 'w') as f:
            json.dump(creds, f, indent=2)
        os.chmod(CREDENTIALS_FILE, 0o600)
        return True
    except:
        return False

def load_heartbeat_history():
    global heartbeat_history
    if os.path.exists(HEARTBEAT_LOG_FILE):
        try:
            with open(HEARTBEAT_LOG_FILE, 'r') as f:
                heartbeat_history = json.load(f)
        except:
            heartbeat_history = []
    else:
        heartbeat_history = []

def save_heartbeat_log(payload, response_status, response_text):
    global heartbeat_history
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "payload": payload,
        "response_status": response_status,
        "response_text": response_text
    }
    heartbeat_history.append(entry)
    # Keep only last 100 entries to prevent file from growing too large
    if len(heartbeat_history) > 100:
        heartbeat_history = heartbeat_history[-100:]
    try:
        with open(HEARTBEAT_LOG_FILE, 'w') as f:
            json.dump(heartbeat_history, f, indent=2)
    except Exception as e:
        print(f"Failed to save heartbeat log: {e}")

def generate_registration_token(device_id, manufacturer, secret):
    message = f"{manufacturer}:{device_id}"
    token = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return token

def get_station_status():
    status = {"timestamp": datetime.utcnow().isoformat()}

    # CPU Temperature
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            cpu_temp = float(f.read().strip()) / 1000.0
            status["cpu_temp"] = round(cpu_temp, 1)
    except:
        status["cpu_temp"] = None

    # Uptime
    try:
        with open('/proc/uptime', 'r') as f:
            uptime_seconds = int(float(f.read().split()[0]))
            status["uptime"] = uptime_seconds
    except:
        status["uptime"] = 0

    # Disk Usage
    try:
        import shutil
        disk_stat = shutil.disk_usage('/')
        status["disk_usage_percent"] = round((disk_stat.used / disk_stat.total) * 100, 1)
    except:
        status["disk_usage_percent"] = None

    # Memory Usage
    try:
        with open('/proc/meminfo', 'r') as f:
            lines = f.readlines()
            mem_total = int([l for l in lines if l.startswith('MemTotal:')][0].split()[1])
            mem_available = int([l for l in lines if l.startswith('MemAvailable:')][0].split()[1])
            mem_used = mem_total - mem_available
            status["memory_usage_percent"] = round((mem_used / mem_total) * 100, 1)
    except:
        status["memory_usage_percent"] = None

    # OGN Status (check if RF and decoder are running)
    try:
        result = subprocess.run(['pgrep', '-x', 'ogn-rf'], capture_output=True, text=True, timeout=2)
        ogn_rf_running = bool(result.stdout.strip())
        result = subprocess.run(['pgrep', '-x', 'ogn-decode'], capture_output=True, text=True, timeout=2)
        ogn_decode_running = bool(result.stdout.strip())
        status["ogn_rf_running"] = ogn_rf_running
        status["ogn_decode_running"] = ogn_decode_running
        status["ogn_status"] = "online" if (ogn_rf_running and ogn_decode_running) else "offline"
    except:
        status["ogn_rf_running"] = None
        status["ogn_decode_running"] = None
        status["ogn_status"] = "unknown"

    # WireGuard VPN IP
    try:
        result = subprocess.run(['ip', 'addr', 'show', 'wg0'], capture_output=True, text=True, timeout=2)
        vpn_match = re.search(r'inet ([\d.]+)', result.stdout)
        status["vpn_ip"] = vpn_match.group(1) if vpn_match else None
    except:
        status["vpn_ip"] = None

    return status

def heartbeat_worker():
    global heartbeat_running
    while heartbeat_running:
        try:
            creds = load_credentials()
            if not creds or not heartbeat_running:
                break

            config = read_config()
            status = get_station_status()
            serial = get_raspberry_pi_serial()
            tailscale_ip = get_tailscale_ip()

            payload = {
                "device_id": creds["device_id"],
                "latitude": config.get("latitude", 0.0),
                "longitude": config.get("longitude", 0.0),
                "altitude": config.get("altitude", 0),
                "speed": 0,
                "heading": 0,
                "timestamp": status["timestamp"],
                "flight_id": "00000000-0000-0000-0000-000000000000",
                "device_metadata": {
                    "heartbeat": True,
                    "station_status": status.get("ogn_status", "unknown"),
                    "station_lat": config.get('latitude', 0.0),
                    "station_lon": config.get('longitude', 0.0),
                    "station_altitude": config.get('altitude', 0),
                    "device_serial": serial,
                    "vpn_ip": tailscale_ip,
                    "ssh_hostname": f"ssh_{serial}.alpium.io",
                    "web_server_url": f"http://{tailscale_ip}:8082" if tailscale_ip else f"https://web_ogn.alpium.io",
                    "ogn_web_ui_url": f"http://{tailscale_ip}:8080" if tailscale_ip else f"https://ogn_ogn.alpium.io",
                    "cpu_temp": status["cpu_temp"],
                    "uptime": status["uptime"],
                    "disk_usage_percent": status.get("disk_usage_percent"),
                    "memory_usage_percent": status.get("memory_usage_percent"),
                    "ogn_rf_running": status.get("ogn_rf_running"),
                    "ogn_decode_running": status.get("ogn_decode_running"),
                    "timestamp": status["timestamp"]
                }
            }

            response = requests.post(
                f"{creds['server_url']}/gps/",
                headers={
                    "Authorization": f"Bearer {creds['api_key']}",
                    **get_cloudflare_headers()
                },
                json=payload,
                timeout=10
            )

            save_heartbeat_log(payload, response.status_code, response.text)

            if response.status_code == 200:
                creds['last_heartbeat'] = datetime.utcnow().isoformat()
                save_credentials(creds)
                print(f"✓ Heartbeat sent - CPU: {status['cpu_temp']}°C")
            else:
                print(f"✗ Heartbeat failed - Status: {response.status_code}, Response: {response.text}")

        except Exception as e:
            print(f"Heartbeat error: {e}")
            save_heartbeat_log(payload if 'payload' in locals() else {}, 0, str(e))

        time.sleep(HEARTBEAT_INTERVAL)

def start_heartbeat():
    global heartbeat_thread, heartbeat_running
    if heartbeat_thread and heartbeat_thread.is_alive():
        return
    heartbeat_running = True
    heartbeat_thread = threading.Thread(target=heartbeat_worker, daemon=True)
    heartbeat_thread.start()

def stop_heartbeat():
    global heartbeat_running
    heartbeat_running = False

def get_hfss_status():
    creds = load_credentials()
    if not creds:
        return {
            'is_registered': False,
            'status_class': 'hfss-notregistered',
            'status_text': 'Not Registered',
            'station_id': '',
            'server_url': '',
            'last_heartbeat': 'Never',
            'heartbeat_status': 'Stopped'
        }

    return {
        'is_registered': True,
        'status_class': 'hfss-registered',
        'status_text': 'Registered',
        'station_id': creds.get('device_id', ''),
        'server_url': creds.get('server_url', ''),
        'last_heartbeat': creds.get('last_heartbeat', 'Never'),
        'heartbeat_status': 'Running' if (heartbeat_thread and heartbeat_thread.is_alive()) else 'Stopped'
    }

@app.route('/')
def index():
    return render_template_string(HTML,config=read_config(),ip=get_ip(),wifi=get_wifi_status(),hfss=get_hfss_status(),hfss_defaults=get_default_hfss_config())

@app.route('/api/save',methods=['POST'])
def save():
    try:
        d=request.json
        if not d.get('call') or len(d['call'])>9:return jsonify({'success':False,'message':'Invalid callsign'})
        if not write_config(d):return jsonify({'success':False,'message':'Failed to write config'})
        subprocess.run(['sudo','service','rtlsdr-ogn','restart'],check=True)
        return jsonify({'success':True,'message':'Configuration saved and service restarted!'})
    except Exception as e:return jsonify({'success':False,'message':str(e)})

@app.route('/api/wifi/toggle',methods=['POST'])
def wifi_toggle():
    try:
        d=request.json
        iface=d.get('interface','wlan0')
        action=d.get('action','on')
        if iface not in ['wlan0','eth1']:return jsonify({'success':False,'message':'Invalid interface'})
        if action=='on':
            subprocess.run(['sudo','ip','link','set',iface,'up'],check=True)
            msg=f'{iface} turned ON'
        else:
            subprocess.run(['sudo','ip','link','set',iface,'down'],check=True)
            msg=f'{iface} turned OFF'
        return jsonify({'success':True,'message':msg})
    except Exception as e:return jsonify({'success':False,'message':str(e)})

@app.route('/api/wifi/add',methods=['POST'])
def wifi_add():
    try:
        d=request.json
        ssid=d.get('ssid','')
        psk=d.get('psk','')
        priority=d.get('priority',1)
        if not ssid or not psk:return jsonify({'success':False,'message':'SSID and password required'})
        networks=read_wpa_networks()
        new_network=f'''
	ssid="{ssid}"
	psk="{psk}"
	priority={priority}
'''
        networks.append(new_network)
        if not write_wpa_config(networks):return jsonify({'success':False,'message':'Failed to write config'})
        return jsonify({'success':True,'message':f'Network {ssid} added!'})
    except Exception as e:return jsonify({'success':False,'message':str(e)})

@app.route('/api/wifi/edit',methods=['POST'])
def wifi_edit():
    try:
        d=request.json
        net_id=int(d.get('network_id',0))
        new_psk=d.get('psk','')
        if not new_psk:return jsonify({'success':False,'message':'Password required'})
        networks=read_wpa_networks()
        if net_id>=len(networks):return jsonify({'success':False,'message':'Network not found'})
        networks[net_id]=re.sub(r'psk="[^"]*"',f'psk="{new_psk}"',networks[net_id])
        if not write_wpa_config(networks):return jsonify({'success':False,'message':'Failed to write config'})
        return jsonify({'success':True,'message':'Password updated!'})
    except Exception as e:return jsonify({'success':False,'message':str(e)})

@app.route('/api/wifi/delete',methods=['POST'])
def wifi_delete():
    try:
        d=request.json
        net_id=int(d.get('network_id',0))
        networks=read_wpa_networks()
        if net_id>=len(networks):return jsonify({'success':False,'message':'Network not found'})
        del networks[net_id]
        if not write_wpa_config(networks):return jsonify({'success':False,'message':'Failed to write config'})
        return jsonify({'success':True,'message':'Network deleted!'})
    except Exception as e:return jsonify({'success':False,'message':str(e)})

@app.route('/api/hfss/register',methods=['POST'])
def hfss_register():
    try:
        d=request.json
        config = read_config()
        status = get_station_status()

        token = generate_registration_token(
            d['station_id'],
            "OGN",
            d['manufacturer_secret']
        )

        payload = {
            "device_id": d['station_id'],
            "manufacturer": "OGN",
            "registration_token": token,
            "name": d['station_name'],
            "device_info": {
                "custom_data": {
                    "latitude": config.get('latitude', 0.0),
                    "longitude": config.get('longitude', 0.0),
                    "altitude": config.get('altitude', 0),
                    "is_station": True,
                    "station_type": "OGN_RECEIVER",
                    "raspberry_pi": True,
                    "callsign": config.get('call', 'NOCALL'),
                    "vpn_ip": status.get("vpn_ip"),
                    "api_endpoint": f"http://{status.get('vpn_ip')}:8082" if status.get('vpn_ip') else None,
                    "ogn_web_ui": f"http://{status.get('vpn_ip')}:8080" if status.get('vpn_ip') else None,
                    "registered_at": status.get("timestamp")
                }
            }
        }

        response = requests.post(
            f"{d['server_url']}/devices/register",
            headers=get_cloudflare_headers(),
            json=payload,
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            creds = {
                "device_id": data["device_id"],
                "api_key": data["api_key"],
                "mqtt_username": data["mqtt_username"],
                "mqtt_password": data["mqtt_password"],
                "server_url": d['server_url'],
                "registered_at": datetime.utcnow().isoformat(),
                "last_heartbeat": None
            }

            if not save_credentials(creds):
                return jsonify({'success':False,'message':'Failed to save credentials'})

            start_heartbeat()
            return jsonify({'success':True,'message':'Registered successfully! Heartbeat started.'})
        else:
            return jsonify({'success':False,'message':f'Registration failed: {response.text}'})

    except Exception as e:
        return jsonify({'success':False,'message':str(e)})

@app.route('/api/hfss/unregister',methods=['POST'])
def hfss_unregister():
    try:
        stop_heartbeat()
        if os.path.exists(CREDENTIALS_FILE):
            os.remove(CREDENTIALS_FILE)
        return jsonify({'success':True,'message':'Unregistered successfully'})
    except Exception as e:
        return jsonify({'success':False,'message':str(e)})

@app.route('/api/hfss/heartbeat-logs')
def heartbeat_logs():
    try:
        return jsonify({'success':True,'logs':heartbeat_history})
    except Exception as e:
        return jsonify({'success':False,'message':str(e),'logs':[]})

@app.route('/api/health')
def health():
    """Health check endpoint with station status"""
    try:
        config = read_config()
        status = get_station_status()
        wifi = get_wifi_status()
        hfss = get_hfss_status()

        return jsonify({
            'status': 'ok',
            'timestamp': status['timestamp'],
            'station': {
                'callsign': config.get('call', 'NOCALL'),
                'location': {
                    'latitude': config.get('latitude', 0.0),
                    'longitude': config.get('longitude', 0.0),
                    'altitude': config.get('altitude', 0)
                },
                'vpn_ip': status.get('vpn_ip'),
                'local_ip': get_ip()
            },
            'system': {
                'cpu_temp': status.get('cpu_temp'),
                'uptime': status.get('uptime'),
                'disk_usage_percent': status.get('disk_usage_percent'),
                'memory_usage_percent': status.get('memory_usage_percent')
            },
            'ogn': {
                'status': status.get('ogn_status', 'unknown'),
                'rf_running': status.get('ogn_rf_running'),
                'decode_running': status.get('ogn_decode_running'),
                'web_ui': f"http://{status.get('vpn_ip')}:8080" if status.get('vpn_ip') else f"http://{get_ip()}:8080"
            },
            'hfss': {
                'registered': hfss['is_registered'],
                'heartbeat_running': hfss['heartbeat_status'] == 'Running',
                'last_heartbeat': hfss.get('last_heartbeat', 'Never')
            },
            'network': {
                'wlan0': wifi['wlan0_status'],
                'eth1': wifi['eth1_status']
            }
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__=='__main__':
    # Load heartbeat history
    load_heartbeat_history()
    # Start heartbeat if already registered
    if load_credentials():
        start_heartbeat()
    app.run(host='0.0.0.0',port=8082,debug=False)
