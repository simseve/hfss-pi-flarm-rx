#!/usr/bin/env python3
"""
OGN Configuration Web API - FastAPI Backend
Professional backend for OGN receiver configuration and WiFi management
Includes HFSS station registration and heartbeat functionality
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import re
import subprocess
import os
import json
import hmac
import hashlib
import requests
import shutil
from typing import Optional, List
from datetime import datetime
from pathlib import Path
import logging
import asyncio

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="OGN Configuration API",
    description="REST API for configuring OGN receivers and managing WiFi with HFSS integration",
    version="2.0.0"
)

# CORS middleware for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration - use environment variables or defaults
CONFIG_FILE = os.getenv('CONFIG_FILE', '/home/hfss/ogn-pi34/rtlsdr-ogn-0.3.2/Template.conf')
WPA_SUPPLICANT = os.getenv('WPA_SUPPLICANT', '/etc/wpa_supplicant/wpa_supplicant.conf')
CREDENTIALS_FILE = os.getenv('CREDENTIALS_FILE', '/home/hfss/.ogn_credentials.json')
ENV_FILE = Path(__file__).parent.parent / '.env'

# HFSS Registration Configuration
HEARTBEAT_INTERVAL = 300  # 5 minutes in seconds
heartbeat_task = None  # Global task reference

# Pydantic Models
class OGNConfig(BaseModel):
    call: str = Field(..., min_length=1, max_length=9, description="Station callsign")
    latitude: float = Field(..., ge=-90, le=90, description="Latitude in degrees")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude in degrees")
    altitude: int = Field(..., description="Altitude in meters")
    freqcorr: float = Field(0.0, description="Frequency correction in PPM")
    centerfreq: float = Field(868.2, description="Center frequency in MHz")
    gain: float = Field(40.0, description="RF gain in dB")


class WiFiNetwork(BaseModel):
    ssid: str = Field(..., min_length=1, description="Network SSID")
    psk: str = Field(..., min_length=8, description="Network password")
    priority: int = Field(1, ge=0, le=100, description="Network priority")


class WiFiEditRequest(BaseModel):
    network_id: int
    psk: str = Field(..., min_length=8)


class WiFiDeleteRequest(BaseModel):
    network_id: int


class WiFiToggleRequest(BaseModel):
    interface: str = Field(..., pattern="^(wlan0|eth1)$")
    action: str = Field(..., pattern="^(on|off)$")


class NetworkInfo(BaseModel):
    id: int
    ssid: str
    status: str


class WiFiStatus(BaseModel):
    wlan0_status: str
    eth1_status: str
    wlan0_ip: str
    eth1_ip: str
    networks: List[NetworkInfo]


class SystemInfo(BaseModel):
    hostname: str
    uptime: str
    cpu_temp: Optional[float]
    memory_usage: Optional[str]


class HFSSRegistrationRequest(BaseModel):
    server_url: str = Field(..., description="HFSS server URL")
    station_id: str = Field(..., pattern="^OGN_STATION_.+", description="Station ID (must start with OGN_STATION_)")
    station_name: str = Field(..., description="Friendly station name")
    manufacturer_secret: str = Field(..., min_length=32, description="Manufacturer secret from server")


class HFSSRegistrationStatus(BaseModel):
    is_registered: bool
    station_id: Optional[str] = None
    server_url: Optional[str] = None
    registered_at: Optional[str] = None
    last_heartbeat: Optional[str] = None
    heartbeat_active: bool = False


# Utility Functions
def read_config() -> dict:
    """Read OGN configuration from Template.conf"""
    config = {
        'call': 'NOCALL',
        'latitude': 0.0,
        'longitude': 0.0,
        'altitude': 0,
        'freqcorr': 0.0,
        'centerfreq': 868.2,
        'gain': 40.0
    }

    try:
        with open(CONFIG_FILE, 'r') as f:
            content = f.read()

        if m := re.search(r'Call = "([^"]+)"', content):
            config['call'] = m.group(1)
        if m := re.search(r'Latitude\s*=\s*([\d.-]+)', content):
            config['latitude'] = float(m.group(1))
        if m := re.search(r'Longitude\s*=\s*([\d.-]+)', content):
            config['longitude'] = float(m.group(1))
        if m := re.search(r'Altitude\s*=\s*([\d.-]+)', content):
            config['altitude'] = int(float(m.group(1)))
        if m := re.search(r'FreqCorr\s*=\s*([\d.-]+)', content):
            config['freqcorr'] = float(m.group(1))
        if m := re.search(r'OGN:.*?CenterFreq\s*=\s*([\d.]+)', content, re.DOTALL):
            config['centerfreq'] = float(m.group(1))
        if m := re.search(r'OGN:.*?Gain\s*=\s*([\d.]+)', content, re.DOTALL):
            config['gain'] = float(m.group(1))
    except Exception as e:
        logger.error(f"Error reading config: {e}")

    return config


def write_config(config: OGNConfig) -> bool:
    """Write OGN configuration to Template.conf"""
    cfg = f'''RF:
{{
  FreqCorr = {config.freqcorr};
  GSM: {{ CenterFreq = 950.0; Gain = 30.0; }};
  OGN: {{ CenterFreq = {config.centerfreq}; Gain = {config.gain}; }};
}};

Position:
{{
  Latitude   =  {config.latitude};
  Longitude  =  {config.longitude};
  Altitude   =  {config.altitude};
}};

APRS:
{{
  Call = "{config.call}";
  Server = "aprs.glidernet.org:14580";
}};

HTTP:
{{
  Port = 8080;
}};
'''

    try:
        with open(CONFIG_FILE, 'w') as f:
            f.write(cfg)
        logger.info(f"Configuration written successfully for {config.call}")
        return True
    except Exception as e:
        logger.error(f"Error writing config: {e}")
        return False


def get_wifi_status() -> dict:
    """Get WiFi interface status and configured networks"""
    status = {
        'wlan0_status': 'unknown',
        'eth1_status': 'unknown',
        'wlan0_ip': 'N/A',
        'eth1_ip': 'N/A',
        'networks': []
    }

    try:
        # Check wlan0 status
        result = subprocess.run(['ip', 'link', 'show', 'wlan0'],
                              capture_output=True, text=True, timeout=5)
        status['wlan0_status'] = 'on' if 'state UP' in result.stdout else 'off'

        # Check eth1 status
        result = subprocess.run(['ip', 'link', 'show', 'eth1'],
                              capture_output=True, text=True, timeout=5)
        status['eth1_status'] = 'on' if 'state UP' in result.stdout else 'off'

        # Get wlan0 IP
        result = subprocess.run(['ip', 'addr', 'show', 'wlan0'],
                              capture_output=True, text=True, timeout=5)
        if m := re.search(r'inet ([\d.]+)', result.stdout):
            status['wlan0_ip'] = m.group(1)

        # Get eth1 IP
        result = subprocess.run(['ip', 'addr', 'show', 'eth1'],
                              capture_output=True, text=True, timeout=5)
        if m := re.search(r'inet ([\d.]+)', result.stdout):
            status['eth1_ip'] = m.group(1)

        # Parse wpa_supplicant networks
        if os.path.exists(WPA_SUPPLICANT):
            with open(WPA_SUPPLICANT, 'r') as f:
                content = f.read()

            networks = re.findall(r'network=\{([^}]+)\}', content, re.DOTALL)
            for i, net in enumerate(networks):
                ssid = re.search(r'ssid="([^"]+)"', net)
                priority = re.search(r'priority=(\d+)', net)
                if ssid:
                    status['networks'].append({
                        'id': i,
                        'ssid': ssid.group(1),
                        'status': f"Priority: {priority.group(1) if priority else '0'}"
                    })
    except Exception as e:
        logger.error(f"Error getting WiFi status: {e}")

    return status


def read_wpa_networks() -> List[str]:
    """Read WiFi networks from wpa_supplicant.conf"""
    networks = []
    try:
        if os.path.exists(WPA_SUPPLICANT):
            with open(WPA_SUPPLICANT, 'r') as f:
                content = f.read()
            networks = re.findall(r'network=\{([^}]+)\}', content, re.DOTALL)
    except Exception as e:
        logger.error(f"Error reading WPA networks: {e}")
    return networks


def write_wpa_config(networks: List[str]) -> bool:
    """Write WiFi networks to wpa_supplicant.conf"""
    header = '''ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=CH

'''
    try:
        with open(WPA_SUPPLICANT, 'w') as f:
            f.write(header)
            for net in networks:
                f.write(f'network={{{net}}}\n\n')

        # Reconfigure wpa_supplicant
        subprocess.run(['sudo', 'wpa_cli', '-i', 'wlan0', 'reconfigure'],
                      check=False, timeout=5)
        logger.info("WPA configuration updated")
        return True
    except Exception as e:
        logger.error(f"Error writing WPA config: {e}")
        return False


def get_system_info() -> dict:
    """Get system information"""
    info = {
        'hostname': 'unknown',
        'uptime': 'unknown',
        'cpu_temp': None,
        'memory_usage': None
    }

    try:
        # Hostname
        result = subprocess.run(['hostname'], capture_output=True, text=True, timeout=5)
        info['hostname'] = result.stdout.strip()

        # Uptime
        result = subprocess.run(['uptime', '-p'], capture_output=True, text=True, timeout=5)
        info['uptime'] = result.stdout.strip()

        # CPU Temperature (Raspberry Pi)
        if os.path.exists('/sys/class/thermal/thermal_zone0/temp'):
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                temp = float(f.read().strip()) / 1000.0
                info['cpu_temp'] = round(temp, 1)

        # Memory usage
        result = subprocess.run(['free', '-h'], capture_output=True, text=True, timeout=5)
        lines = result.stdout.split('\n')
        if len(lines) > 1:
            mem_line = lines[1].split()
            if len(mem_line) >= 3:
                info['memory_usage'] = f"{mem_line[2]} / {mem_line[1]}"

    except Exception as e:
        logger.error(f"Error getting system info: {e}")

    return info


# API Routes
@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "name": "OGN Configuration API",
        "version": "2.0.0",
        "status": "running"
    }


@app.get("/api/config", response_model=dict)
async def get_config():
    """Get current OGN configuration"""
    return read_config()


@app.post("/api/config")
async def save_config(config: OGNConfig):
    """Save OGN configuration and restart service"""
    try:
        if not write_config(config):
            raise HTTPException(status_code=500, detail="Failed to write configuration")

        # Restart OGN service
        subprocess.run(['sudo', 'service', 'rtlsdr-ogn', 'restart'],
                      check=True, timeout=10)

        logger.info(f"Configuration saved and service restarted for {config.call}")
        return {
            "success": True,
            "message": "Configuration saved and service restarted successfully!"
        }
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to restart service: {e}")
        raise HTTPException(status_code=500, detail="Failed to restart OGN service")
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/wifi/status", response_model=WiFiStatus)
async def wifi_status():
    """Get WiFi interface status and networks"""
    return get_wifi_status()


@app.post("/api/wifi/toggle")
async def wifi_toggle(request: WiFiToggleRequest):
    """Toggle WiFi interface on/off"""
    try:
        if request.action == 'on':
            subprocess.run(['sudo', 'ip', 'link', 'set', request.interface, 'up'],
                         check=True, timeout=5)
            message = f"{request.interface} turned ON"
        else:
            subprocess.run(['sudo', 'ip', 'link', 'set', request.interface, 'down'],
                         check=True, timeout=5)
            message = f"{request.interface} turned OFF"

        logger.info(message)
        return {"success": True, "message": message}
    except Exception as e:
        logger.error(f"Error toggling WiFi: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/wifi/add")
async def wifi_add(network: WiFiNetwork):
    """Add new WiFi network"""
    try:
        networks = read_wpa_networks()

        new_network = f'''
	ssid="{network.ssid}"
	psk="{network.psk}"
	priority={network.priority}
'''
        networks.append(new_network)

        if not write_wpa_config(networks):
            raise HTTPException(status_code=500, detail="Failed to write WiFi configuration")

        logger.info(f"WiFi network '{network.ssid}' added")
        return {"success": True, "message": f"Network '{network.ssid}' added successfully!"}
    except Exception as e:
        logger.error(f"Error adding WiFi network: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/wifi/edit")
async def wifi_edit(request: WiFiEditRequest):
    """Edit WiFi network password"""
    try:
        networks = read_wpa_networks()

        if request.network_id >= len(networks):
            raise HTTPException(status_code=404, detail="Network not found")

        # Update password
        networks[request.network_id] = re.sub(
            r'psk="[^"]*"',
            f'psk="{request.psk}"',
            networks[request.network_id]
        )

        if not write_wpa_config(networks):
            raise HTTPException(status_code=500, detail="Failed to write WiFi configuration")

        logger.info(f"WiFi network #{request.network_id} password updated")
        return {"success": True, "message": "Password updated successfully!"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error editing WiFi network: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/wifi/delete")
async def wifi_delete(request: WiFiDeleteRequest):
    """Delete WiFi network"""
    try:
        networks = read_wpa_networks()

        if request.network_id >= len(networks):
            raise HTTPException(status_code=404, detail="Network not found")

        del networks[request.network_id]

        if not write_wpa_config(networks):
            raise HTTPException(status_code=500, detail="Failed to write WiFi configuration")

        logger.info(f"WiFi network #{request.network_id} deleted")
        return {"success": True, "message": "Network deleted successfully!"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting WiFi network: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/system", response_model=SystemInfo)
async def system_info():
    """Get system information"""
    return get_system_info()


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


# HFSS Registration & Heartbeat Functions
def load_credentials() -> Optional[dict]:
    """Load saved HFSS credentials"""
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load credentials: {e}")
    return None


def save_credentials(credentials: dict) -> bool:
    """Save HFSS credentials to file"""
    try:
        with open(CREDENTIALS_FILE, 'w') as f:
            json.dump(credentials, f, indent=2)
        os.chmod(CREDENTIALS_FILE, 0o600)  # Owner read/write only
        logger.info(f"Credentials saved for {credentials.get('device_id')}")
        return True
    except Exception as e:
        logger.error(f"Failed to save credentials: {e}")
        return False


def generate_registration_token(device_id: str, manufacturer: str, secret: str) -> str:
    """Generate HMAC registration token"""
    message = f"{manufacturer}:{device_id}"
    token = hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    return token


def get_station_status() -> dict:
    """Collect current station status for heartbeat"""
    status = {"timestamp": datetime.utcnow().isoformat()}

    # CPU temperature
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            cpu_temp = float(f.read().strip()) / 1000.0
            status["cpu_temp"] = round(cpu_temp, 1)
    except:
        status["cpu_temp"] = None

    # System uptime
    try:
        with open('/proc/uptime', 'r') as f:
            uptime_seconds = int(float(f.read().split()[0]))
            status["uptime"] = uptime_seconds
    except:
        status["uptime"] = 0

    # Disk usage
    try:
        disk = shutil.disk_usage('/')
        status["disk_usage_percent"] = round(disk.used / disk.total * 100, 1)
    except:
        status["disk_usage_percent"] = None

    # Memory usage
    try:
        with open('/proc/meminfo', 'r') as f:
            meminfo = f.read()
            total = int([x for x in meminfo.split('\n') if 'MemTotal' in x][0].split()[1])
            available = int([x for x in meminfo.split('\n') if 'MemAvailable' in x][0].split()[1])
            used_percent = round((total - available) / total * 100, 1)
            status["memory_usage_percent"] = used_percent
    except:
        status["memory_usage_percent"] = None

    return status


async def send_heartbeat_task():
    """Background task to send periodic heartbeats"""
    global heartbeat_task

    while True:
        try:
            credentials = load_credentials()
            if not credentials:
                logger.warning("No credentials found, stopping heartbeat")
                break

            server_url = credentials.get('server_url')
            api_key = credentials.get('api_key')

            if not server_url or not api_key:
                logger.error("Invalid credentials, stopping heartbeat")
                break

            # Get current configuration for location
            config = read_config()
            status = get_station_status()

            # Prepare heartbeat payload
            payload = {
                "device_metadata": {
                    "heartbeat": True,
                    "station_status": "online",
                    "station_lat": config.get('latitude', 0.0),
                    "station_lon": config.get('longitude', 0.0),
                    "station_altitude": config.get('altitude', 0),
                    "cpu_temp": status["cpu_temp"],
                    "uptime": status["uptime"],
                    "disk_usage_percent": status["disk_usage_percent"],
                    "memory_usage_percent": status["memory_usage_percent"],
                    "ogn_clients": 0,  # TODO: Implement OGN client counting
                    "timestamp": status["timestamp"]
                }
            }

            # Send heartbeat
            response = requests.post(
                f"{server_url}/api/v1/gps",
                headers={"X-API-Key": api_key},
                json=payload,
                timeout=10
            )

            if response.status_code == 200:
                logger.info(
                    f"✓ Heartbeat sent - "
                    f"CPU: {status['cpu_temp']}°C, "
                    f"Uptime: {status['uptime']}s, "
                    f"Disk: {status['disk_usage_percent']}%"
                )
                # Update last heartbeat timestamp
                credentials['last_heartbeat'] = datetime.utcnow().isoformat()
                save_credentials(credentials)
            else:
                logger.warning(f"✗ Heartbeat failed: HTTP {response.status_code}")

        except Exception as e:
            logger.error(f"Error sending heartbeat: {e}")

        # Wait for next heartbeat
        await asyncio.sleep(HEARTBEAT_INTERVAL)


@app.on_event("startup")
async def startup_event():
    """Start heartbeat task on application startup if registered"""
    credentials = load_credentials()
    if credentials and credentials.get('api_key'):
        logger.info("Starting heartbeat task...")
        global heartbeat_task
        heartbeat_task = asyncio.create_task(send_heartbeat_task())


@app.on_event("shutdown")
async def shutdown_event():
    """Stop heartbeat task on application shutdown"""
    global heartbeat_task
    if heartbeat_task:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            logger.info("Heartbeat task stopped")


# HFSS Registration API Routes
@app.get("/api/hfss/status", response_model=HFSSRegistrationStatus)
async def hfss_status():
    """Get HFSS registration status"""
    credentials = load_credentials()

    if not credentials:
        return HFSSRegistrationStatus(
            is_registered=False,
            heartbeat_active=False
        )

    return HFSSRegistrationStatus(
        is_registered=True,
        station_id=credentials.get('device_id'),
        server_url=credentials.get('server_url'),
        registered_at=credentials.get('registered_at'),
        last_heartbeat=credentials.get('last_heartbeat'),
        heartbeat_active=heartbeat_task is not None and not heartbeat_task.done()
    )


@app.post("/api/hfss/register")
async def hfss_register(request: HFSSRegistrationRequest, background_tasks: BackgroundTasks):
    """Register station with HFSS server"""
    try:
        # Get current configuration for location
        config = read_config()

        # Generate registration token
        token = generate_registration_token(
            request.station_id,
            "OGN",
            request.manufacturer_secret
        )

        # Prepare registration payload
        payload = {
            "device_id": request.station_id,
            "manufacturer": "OGN",
            "registration_token": token,
            "name": request.station_name,
            "device_info": {
                "custom_data": {
                    "latitude": config.get('latitude', 0.0),
                    "longitude": config.get('longitude', 0.0),
                    "altitude": config.get('altitude', 0),
                    "is_station": True,
                    "station_type": "OGN_RECEIVER",
                    "raspberry_pi": True,
                    "callsign": config.get('call', 'NOCALL')
                }
            }
        }

        # Send registration request
        response = requests.post(
            f"{request.server_url}/api/v1/devices/register",
            json=payload,
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            credentials = {
                "device_id": data["device_id"],
                "api_key": data["api_key"],
                "mqtt_username": data["mqtt_username"],
                "mqtt_password": data["mqtt_password"],
                "server_url": request.server_url,
                "registered_at": datetime.utcnow().isoformat(),
                "last_heartbeat": None
            }

            # Save credentials
            if not save_credentials(credentials):
                raise HTTPException(status_code=500, detail="Failed to save credentials")

            # Start heartbeat task
            global heartbeat_task
            if heartbeat_task is None or heartbeat_task.done():
                heartbeat_task = asyncio.create_task(send_heartbeat_task())

            logger.info(f"✓ Station {request.station_id} registered successfully")
            return {
                "success": True,
                "message": f"Station registered successfully! Heartbeat started.",
                "device_id": credentials['device_id']
            }
        else:
            error_detail = response.text
            logger.error(f"✗ Registration failed: {response.status_code} - {error_detail}")
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Registration failed: {error_detail}"
            )

    except requests.exceptions.ConnectionError:
        logger.error(f"✗ Cannot connect to server: {request.server_url}")
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to server: {request.server_url}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"✗ Registration error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/hfss/unregister")
async def hfss_unregister():
    """Unregister station and stop heartbeat"""
    try:
        # Stop heartbeat task
        global heartbeat_task
        if heartbeat_task:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            heartbeat_task = None

        # Delete credentials
        if os.path.exists(CREDENTIALS_FILE):
            os.remove(CREDENTIALS_FILE)

        logger.info("Station unregistered and heartbeat stopped")
        return {
            "success": True,
            "message": "Station unregistered successfully. Heartbeat stopped."
        }
    except Exception as e:
        logger.error(f"Error during unregistration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/hfss/heartbeat/start")
async def start_heartbeat():
    """Manually start heartbeat task"""
    try:
        credentials = load_credentials()
        if not credentials:
            raise HTTPException(status_code=400, detail="Not registered. Register first.")

        global heartbeat_task
        if heartbeat_task and not heartbeat_task.done():
            return {"success": True, "message": "Heartbeat already running"}

        heartbeat_task = asyncio.create_task(send_heartbeat_task())
        logger.info("Heartbeat task started manually")
        return {"success": True, "message": "Heartbeat started"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting heartbeat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/hfss/heartbeat/stop")
async def stop_heartbeat():
    """Manually stop heartbeat task"""
    try:
        global heartbeat_task
        if heartbeat_task:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            heartbeat_task = None

        logger.info("Heartbeat task stopped manually")
        return {"success": True, "message": "Heartbeat stopped"}
    except Exception as e:
        logger.error(f"Error stopping heartbeat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8082,
        reload=False,
        log_level="info"
    )
