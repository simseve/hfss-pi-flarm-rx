#!/usr/bin/env python3
from flask import Flask, render_template_string, request, jsonify
import re
import subprocess
import os

app = Flask(__name__)
CONFIG_FILE = '/home/hfss/ogn-pi34/rtlsdr-ogn-0.3.2/Template.conf'
WPA_SUPPLICANT = '/etc/wpa_supplicant/wpa_supplicant.conf'

HTML = '''<!DOCTYPE html>
<html><head><title>OGN Config</title><meta name="viewport" content="width=device-width, initial-scale=1">
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:Arial,sans-serif;background:#f0f2f5;padding:20px}.container{max-width:1200px;margin:0 auto;background:white;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.1)}.header{background:#2c3e50;color:white;padding:20px}.header h1{font-size:24px;margin-bottom:5px}.content{padding:20px}.form-section{background:#f8f9fa;padding:20px;border-radius:6px;margin-bottom:20px}.form-section h2{font-size:18px;margin-bottom:15px;color:#2c3e50}.form-group{margin-bottom:15px}.form-group label{display:block;margin-bottom:5px;font-weight:bold;color:#555}.form-group input,.form-group select{width:100%;padding:10px;border:1px solid #ddd;border-radius:4px;font-size:14px}.btn{background:#3498db;color:white;padding:12px 24px;border:none;border-radius:4px;cursor:pointer;font-size:16px;margin-right:10px}.btn:hover{background:#2980b9}.btn-danger{background:#e74c3c}.btn-danger:hover{background:#c0392b}.btn-success{background:#27ae60}.btn-success:hover{background:#229954}.status{padding:15px;border-radius:4px;margin-bottom:20px}.status.success{background:#d4edda;color:#155724}.status.error{background:#f8d7da;color:#721c24}.info-box{background:#e8f4f8;border-left:4px solid #3498db;padding:15px;margin-bottom:20px}iframe{width:100%;height:600px;border:1px solid #ddd;border-radius:6px;margin-top:20px}.wifi-status{display:inline-block;padding:5px 10px;border-radius:4px;font-weight:bold}.wifi-on{background:#d4edda;color:#155724}.wifi-off{background:#f8d7da;color:#721c24}.network-list{list-style:none;padding:0}.network-item{background:white;padding:15px;margin:10px 0;border:1px solid #ddd;border-radius:4px;display:flex;justify-content:space-between;align-items:center}.network-item .network-info{flex:1}.network-item .network-ssid{font-weight:bold;color:#2c3e50}.network-item .network-status{font-size:12px;color:#7f8c8d;margin-top:5px}.btn-small{padding:8px 16px;font-size:14px}</style>
</head><body><div class="container"><div class="header"><h1>OGN Receiver Configuration</h1></div>
<div class="content"><div id="status"></div>

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
document.getElementById('wifiForm').onsubmit=async(e)=>{e.preventDefault();
const d=Object.fromEntries(new FormData(e.target));
const r=await fetch('/api/wifi/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});
const j=await r.json();document.getElementById('status').innerHTML='<div class="status '+(j.success?'success':'error')+'">'+j.message+'</div>';
if(j.success){e.target.reset();setTimeout(()=>location.reload(),1500);}
};
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
        if m:=re.search(r'FreqCorr\s*=\s*([\d.-]+)',content):config['freqcorr']=float(m.group(1))
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
        # Check interface status
        result = subprocess.run(['ip','link','show','wlan0'],capture_output=True,text=True)
        status['wlan0_status'] = 'on' if 'state UP' in result.stdout else 'off'

        result = subprocess.run(['ip','link','show','eth1'],capture_output=True,text=True)
        status['eth1_status'] = 'on' if 'state UP' in result.stdout else 'off'

        # Get IP addresses
        result = subprocess.run(['ip','addr','show','wlan0'],capture_output=True,text=True)
        if m:=re.search(r'inet ([\d.]+)',result.stdout):status['wlan0_ip']=m.group(1)

        result = subprocess.run(['ip','addr','show','eth1'],capture_output=True,text=True)
        if m:=re.search(r'inet ([\d.]+)',result.stdout):status['eth1_ip']=m.group(1)

        # Parse wpa_supplicant networks
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
                f.write(f'network={{{net}}}\\n\\n')
        subprocess.run(['sudo','wpa_cli','-i','wlan0','reconfigure'],check=False)
        return True
    except:return False

@app.route('/')
def index():
    return render_template_string(HTML,config=read_config(),ip=get_ip(),wifi=get_wifi_status())

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

        # Update password
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

if __name__=='__main__':app.run(host='0.0.0.0',port=8082,debug=False)
