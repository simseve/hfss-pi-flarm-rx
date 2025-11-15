import { useState, useEffect } from 'react'
import axios from 'axios'
import { Radio, Save, MapPin, Activity } from 'lucide-react'

const API_BASE = '/api'

export default function OGNConfig({ showNotification }) {
  const [config, setConfig] = useState({
    call: '',
    latitude: 0,
    longitude: 0,
    altitude: 0,
    freqcorr: 0,
    centerfreq: 868.2,
    gain: 40.0
  })
  const [loading, setLoading] = useState(false)
  const [initialLoad, setInitialLoad] = useState(true)

  useEffect(() => {
    loadConfig()
  }, [])

  const loadConfig = async () => {
    try {
      const response = await axios.get(`${API_BASE}/config`)
      setConfig(response.data)
      setInitialLoad(false)
    } catch (error) {
      showNotification('Failed to load configuration', 'error')
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)

    try {
      const response = await axios.post(`${API_BASE}/config`, config)
      showNotification(response.data.message, 'success')
      setTimeout(() => loadConfig(), 3000)
    } catch (error) {
      const message = error.response?.data?.detail || error.message
      showNotification(`Save failed: ${message}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  if (initialLoad) {
    return (
      <div className="card p-12">
        <div className="flex items-center justify-center space-x-3">
          <Activity className="w-6 h-6 animate-spin text-blue-600" />
          <span className="text-gray-600 dark:text-gray-400">Loading configuration...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Current Config Summary */}
      <div className="card p-6 bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800">
        <div className="flex items-center space-x-3 mb-4">
          <Radio className="w-6 h-6 text-blue-600" />
          <h3 className="font-semibold text-blue-900 dark:text-blue-200">Current Station</h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <p className="text-xs text-blue-700 dark:text-blue-400 mb-1">Callsign</p>
            <p className="text-lg font-bold text-blue-900 dark:text-blue-100">{config.call}</p>
          </div>
          <div>
            <p className="text-xs text-blue-700 dark:text-blue-400 mb-1">Location</p>
            <p className="text-sm font-mono text-blue-900 dark:text-blue-100">
              {config.latitude.toFixed(6)}, {config.longitude.toFixed(6)}
            </p>
          </div>
          <div>
            <p className="text-xs text-blue-700 dark:text-blue-400 mb-1">Altitude</p>
            <p className="text-lg font-bold text-blue-900 dark:text-blue-100">{config.altitude}m</p>
          </div>
        </div>
      </div>

      {/* Configuration Form */}
      <div className="card p-6">
        <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-6">
          OGN Receiver Configuration
        </h2>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Station Section */}
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center space-x-2">
              <Radio className="w-5 h-5" />
              <span>Station</span>
            </h3>
            <div>
              <label className="label">Callsign (max 9 characters)</label>
              <input
                type="text"
                className="input uppercase"
                maxLength="9"
                value={config.call}
                onChange={(e) => setConfig({ ...config, call: e.target.value.toUpperCase() })}
                required
              />
            </div>
          </div>

          {/* Location Section */}
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center space-x-2">
              <MapPin className="w-5 h-5" />
              <span>Location</span>
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="label">Latitude</label>
                <input
                  type="number"
                  className="input font-mono"
                  step="0.000001"
                  min="-90"
                  max="90"
                  value={config.latitude}
                  onChange={(e) => setConfig({ ...config, latitude: parseFloat(e.target.value) })}
                  required
                />
              </div>
              <div>
                <label className="label">Longitude</label>
                <input
                  type="number"
                  className="input font-mono"
                  step="0.000001"
                  min="-180"
                  max="180"
                  value={config.longitude}
                  onChange={(e) => setConfig({ ...config, longitude: parseFloat(e.target.value) })}
                  required
                />
              </div>
              <div>
                <label className="label">Altitude (meters)</label>
                <input
                  type="number"
                  className="input"
                  value={config.altitude}
                  onChange={(e) => setConfig({ ...config, altitude: parseInt(e.target.value) })}
                  required
                />
              </div>
            </div>
          </div>

          {/* RF Settings Section */}
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center space-x-2">
              <Activity className="w-5 h-5" />
              <span>RF Settings</span>
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="label">Frequency Correction (PPM)</label>
                <input
                  type="number"
                  className="input font-mono"
                  step="0.1"
                  value={config.freqcorr}
                  onChange={(e) => setConfig({ ...config, freqcorr: parseFloat(e.target.value) })}
                />
                <p className="text-xs text-gray-500 mt-1">Calibrate with gsm_scan</p>
              </div>
              <div>
                <label className="label">Center Frequency (MHz)</label>
                <input
                  type="number"
                  className="input font-mono"
                  step="0.1"
                  value={config.centerfreq}
                  onChange={(e) => setConfig({ ...config, centerfreq: parseFloat(e.target.value) })}
                />
                <p className="text-xs text-gray-500 mt-1">868.2 (EU), 915.0 (US)</p>
              </div>
              <div>
                <label className="label">Gain (dB)</label>
                <input
                  type="number"
                  className="input font-mono"
                  step="0.1"
                  value={config.gain}
                  onChange={(e) => setConfig({ ...config, gain: parseFloat(e.target.value) })}
                />
                <p className="text-xs text-gray-500 mt-1">Typical: 40.0</p>
              </div>
            </div>
          </div>

          {/* Submit Button */}
          <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
            <button
              type="submit"
              disabled={loading}
              className="btn btn-primary flex items-center space-x-2"
            >
              {loading ? (
                <>
                  <Activity className="w-5 h-5 animate-spin" />
                  <span>Saving & Restarting...</span>
                </>
              ) : (
                <>
                  <Save className="w-5 h-5" />
                  <span>Save Configuration & Restart OGN</span>
                </>
              )}
            </button>
            <p className="text-xs text-gray-500 mt-2">
              This will restart the rtlsdr-ogn service with new settings
            </p>
          </div>
        </form>
      </div>

      {/* OGN Web Interface */}
      <div className="card p-6">
        <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">
          OGN Receiver Status
        </h2>
        <div className="aspect-video bg-gray-900 rounded-lg overflow-hidden">
          <iframe
            src="http://localhost:8080"
            className="w-full h-full"
            title="OGN Receiver Status"
          />
        </div>
        <p className="text-xs text-gray-500 mt-2">
          Direct view of OGN receiver status interface (port 8080)
        </p>
      </div>
    </div>
  )
}
