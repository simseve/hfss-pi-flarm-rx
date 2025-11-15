import { useState, useEffect } from 'react'
import axios from 'axios'
import { Server, CheckCircle, XCircle, Activity, Clock, Play, StopCircle } from 'lucide-react'

const API_BASE = '/api'

export default function HFSSRegistration({ showNotification, hfssStatus, refreshStatus }) {
  const [formData, setFormData] = useState({
    server_url: '',
    station_id: 'OGN_STATION_',
    station_name: '',
    manufacturer_secret: ''
  })
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)

    try {
      const response = await axios.post(`${API_BASE}/hfss/register`, formData)
      showNotification(response.data.message, 'success')
      refreshStatus()
      // Clear manufacturer secret after successful registration
      setFormData(prev => ({ ...prev, manufacturer_secret: '' }))
    } catch (error) {
      const message = error.response?.data?.detail || error.message
      showNotification(`Registration failed: ${message}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleUnregister = async () => {
    if (!confirm('Are you sure you want to unregister this station? This will stop heartbeats.')) {
      return
    }

    setLoading(true)
    try {
      const response = await axios.post(`${API_BASE}/hfss/unregister`)
      showNotification(response.data.message, 'success')
      refreshStatus()
    } catch (error) {
      const message = error.response?.data?.detail || error.message
      showNotification(`Unregistration failed: ${message}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleHeartbeatControl = async (action) => {
    setLoading(true)
    try {
      const response = await axios.post(`${API_BASE}/hfss/heartbeat/${action}`)
      showNotification(response.data.message, 'success')
      refreshStatus()
    } catch (error) {
      const message = error.response?.data?.detail || error.message
      showNotification(`Heartbeat ${action} failed: ${message}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Status Card */}
      <div className="card p-6">
        <div className="flex items-center space-x-3 mb-6">
          <Server className="w-6 h-6 text-blue-600" />
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">
            HFSS Registration Status
          </h2>
        </div>

        {hfssStatus && (
          <div className="space-y-4">
            <div className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Registration Status
              </span>
              <div className="flex items-center space-x-2">
                {hfssStatus.is_registered ? (
                  <>
                    <CheckCircle className="w-5 h-5 text-green-600" />
                    <span className="text-sm font-semibold text-green-600">Registered</span>
                  </>
                ) : (
                  <>
                    <XCircle className="w-5 h-5 text-red-600" />
                    <span className="text-sm font-semibold text-red-600">Not Registered</span>
                  </>
                )}
              </div>
            </div>

            {hfssStatus.is_registered && (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                    <p className="text-xs text-gray-600 dark:text-gray-400 mb-1">Station ID</p>
                    <p className="text-sm font-mono font-semibold text-gray-900 dark:text-white">
                      {hfssStatus.station_id}
                    </p>
                  </div>

                  <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                    <p className="text-xs text-gray-600 dark:text-gray-400 mb-1">Server URL</p>
                    <p className="text-sm font-mono font-semibold text-gray-900 dark:text-white break-all">
                      {hfssStatus.server_url}
                    </p>
                  </div>

                  <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                    <p className="text-xs text-gray-600 dark:text-gray-400 mb-1">Registered At</p>
                    <p className="text-sm font-semibold text-gray-900 dark:text-white">
                      {new Date(hfssStatus.registered_at).toLocaleString()}
                    </p>
                  </div>

                  <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                    <p className="text-xs text-gray-600 dark:text-gray-400 mb-1">Last Heartbeat</p>
                    <p className="text-sm font-semibold text-gray-900 dark:text-white">
                      {hfssStatus.last_heartbeat
                        ? new Date(hfssStatus.last_heartbeat).toLocaleString()
                        : 'Never'}
                    </p>
                  </div>
                </div>

                <div className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    Heartbeat Status
                  </span>
                  <div className="flex items-center space-x-2">
                    {hfssStatus.heartbeat_active ? (
                      <>
                        <Activity className="w-5 h-5 text-green-600 animate-pulse" />
                        <span className="text-sm font-semibold text-green-600">Active</span>
                      </>
                    ) : (
                      <>
                        <Clock className="w-5 h-5 text-gray-600" />
                        <span className="text-sm font-semibold text-gray-600">Stopped</span>
                      </>
                    )}
                  </div>
                </div>

                {/* Heartbeat Controls */}
                <div className="flex space-x-3">
                  {!hfssStatus.heartbeat_active ? (
                    <button
                      onClick={() => handleHeartbeatControl('start')}
                      disabled={loading}
                      className="btn btn-success flex items-center space-x-2"
                    >
                      <Play className="w-4 h-4" />
                      <span>Start Heartbeat</span>
                    </button>
                  ) : (
                    <button
                      onClick={() => handleHeartbeatControl('stop')}
                      disabled={loading}
                      className="btn btn-danger flex items-center space-x-2"
                    >
                      <StopCircle className="w-4 h-4" />
                      <span>Stop Heartbeat</span>
                    </button>
                  )}

                  <button
                    onClick={handleUnregister}
                    disabled={loading}
                    className="btn btn-danger"
                  >
                    Unregister Station
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {/* Registration Form */}
      {!hfssStatus?.is_registered && (
        <div className="card p-6">
          <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-6">
            Register New Station
          </h2>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="label">HFSS Server URL</label>
              <input
                type="url"
                className="input"
                placeholder="https://your-hfss-server.com"
                value={formData.server_url}
                onChange={(e) => setFormData({ ...formData, server_url: e.target.value })}
                required
              />
              <p className="text-xs text-gray-500 mt-1">
                The URL of your HFSS tracking server
              </p>
            </div>

            <div>
              <label className="label">Station ID</label>
              <input
                type="text"
                className="input font-mono"
                placeholder="OGN_STATION_YOUR_ID"
                pattern="^OGN_STATION_.+"
                value={formData.station_id}
                onChange={(e) => setFormData({ ...formData, station_id: e.target.value })}
                required
              />
              <p className="text-xs text-gray-500 mt-1">
                Must start with OGN_STATION_ (e.g., OGN_STATION_ALPINE01)
              </p>
            </div>

            <div>
              <label className="label">Station Name</label>
              <input
                type="text"
                className="input"
                placeholder="My OGN Station"
                value={formData.station_name}
                onChange={(e) => setFormData({ ...formData, station_name: e.target.value })}
                required
              />
              <p className="text-xs text-gray-500 mt-1">
                Friendly name for your station
              </p>
            </div>

            <div>
              <label className="label">Manufacturer Secret</label>
              <input
                type="password"
                className="input font-mono text-sm"
                placeholder="Paste secret from server admin"
                minLength="32"
                value={formData.manufacturer_secret}
                onChange={(e) => setFormData({ ...formData, manufacturer_secret: e.target.value })}
                required
              />
              <p className="text-xs text-gray-500 mt-1">
                Get this from your HFSS server administrator
              </p>
            </div>

            <div className="pt-4">
              <button
                type="submit"
                disabled={loading}
                className="btn btn-primary w-full flex items-center justify-center space-x-2"
              >
                {loading ? (
                  <>
                    <Activity className="w-5 h-5 animate-spin" />
                    <span>Registering...</span>
                  </>
                ) : (
                  <>
                    <Server className="w-5 h-5" />
                    <span>Register Station</span>
                  </>
                )}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Info Box */}
      <div className="card p-6 bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800">
        <h3 className="font-semibold text-blue-900 dark:text-blue-200 mb-3">
          About HFSS Registration
        </h3>
        <ul className="text-sm text-blue-800 dark:text-blue-300 space-y-2">
          <li>• Registration connects your OGN station to the HFSS tracking system</li>
          <li>• Heartbeats send system status every 5 minutes</li>
          <li>• Station location from OGN config is automatically included</li>
          <li>• Heartbeats start automatically after successful registration</li>
          <li>• All credentials are stored securely on this device</li>
        </ul>
      </div>
    </div>
  )
}
