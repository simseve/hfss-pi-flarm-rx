import { useState, useEffect } from 'react'
import axios from 'axios'
import { Wifi, WifiOff, Plus, Trash2, Edit2, Activity, RefreshCw } from 'lucide-react'

const API_BASE = '/api'

export default function WiFiManagement({ showNotification }) {
  const [wifiStatus, setWifiStatus] = useState(null)
  const [loading, setLoading] = useState(false)
  const [showAddForm, setShowAddForm] = useState(false)
  const [newNetwork, setNewNetwork] = useState({
    ssid: '',
    psk: '',
    priority: 1
  })

  useEffect(() => {
    loadWiFiStatus()
  }, [])

  const loadWiFiStatus = async () => {
    try {
      const response = await axios.get(`${API_BASE}/wifi/status`)
      setWifiStatus(response.data)
    } catch (error) {
      showNotification('Failed to load WiFi status', 'error')
    }
  }

  const toggleInterface = async (iface, action) => {
    setLoading(true)
    try {
      const response = await axios.post(`${API_BASE}/wifi/toggle`, {
        interface: iface,
        action: action
      })
      showNotification(response.data.message, 'success')
      setTimeout(() => loadWiFiStatus(), 2000)
    } catch (error) {
      const message = error.response?.data?.detail || error.message
      showNotification(`Failed to toggle ${iface}: ${message}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  const addNetwork = async (e) => {
    e.preventDefault()
    setLoading(true)

    try {
      const response = await axios.post(`${API_BASE}/wifi/add`, newNetwork)
      showNotification(response.data.message, 'success')
      setNewNetwork({ ssid: '', psk: '', priority: 1 })
      setShowAddForm(false)
      setTimeout(() => loadWiFiStatus(), 1500)
    } catch (error) {
      const message = error.response?.data?.detail || error.message
      showNotification(`Failed to add network: ${message}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  const editNetwork = async (networkId) => {
    const newPassword = prompt('Enter new password:')
    if (!newPassword || newPassword.length < 8) {
      showNotification('Password must be at least 8 characters', 'warning')
      return
    }

    setLoading(true)
    try {
      const response = await axios.post(`${API_BASE}/wifi/edit`, {
        network_id: networkId,
        psk: newPassword
      })
      showNotification(response.data.message, 'success')
      setTimeout(() => loadWiFiStatus(), 1500)
    } catch (error) {
      const message = error.response?.data?.detail || error.message
      showNotification(`Failed to edit network: ${message}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  const deleteNetwork = async (networkId, ssid) => {
    if (!confirm(`Delete network "${ssid}"?`)) return

    setLoading(true)
    try {
      const response = await axios.post(`${API_BASE}/wifi/delete`, {
        network_id: networkId
      })
      showNotification(response.data.message, 'success')
      setTimeout(() => loadWiFiStatus(), 1500)
    } catch (error) {
      const message = error.response?.data?.detail || error.message
      showNotification(`Failed to delete network: ${message}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  if (!wifiStatus) {
    return (
      <div className="card p-12">
        <div className="flex items-center justify-center space-x-3">
          <Activity className="w-6 h-6 animate-spin text-blue-600" />
          <span className="text-gray-600 dark:text-gray-400">Loading WiFi status...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Interface Status */}
      <div className="card p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center space-x-2">
            <Wifi className="w-6 h-6" />
            <span>WiFi Interfaces</span>
          </h2>
          <button
            onClick={loadWiFiStatus}
            className="btn btn-secondary flex items-center space-x-2"
            disabled={loading}
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* wlan0 */}
          <div className="p-6 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center space-x-3">
                {wifiStatus.wlan0_status === 'on' ? (
                  <Wifi className="w-8 h-8 text-green-600" />
                ) : (
                  <WifiOff className="w-8 h-8 text-red-600" />
                )}
                <div>
                  <h3 className="font-bold text-gray-900 dark:text-white">wlan0</h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    Built-in WiFi
                  </p>
                </div>
              </div>
              <span
                className={`px-3 py-1 rounded-full text-sm font-semibold ${
                  wifiStatus.wlan0_status === 'on'
                    ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
                    : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
                }`}
              >
                {wifiStatus.wlan0_status.toUpperCase()}
              </span>
            </div>

            <div className="mb-4">
              <p className="text-xs text-gray-600 dark:text-gray-400 mb-1">IP Address</p>
              <p className="font-mono text-sm font-semibold text-gray-900 dark:text-white">
                {wifiStatus.wlan0_ip}
              </p>
            </div>

            <div className="flex space-x-2">
              <button
                onClick={() => toggleInterface('wlan0', 'on')}
                disabled={loading || wifiStatus.wlan0_status === 'on'}
                className="btn btn-success flex-1"
              >
                Turn ON
              </button>
              <button
                onClick={() => toggleInterface('wlan0', 'off')}
                disabled={loading || wifiStatus.wlan0_status === 'off'}
                className="btn btn-danger flex-1"
              >
                Turn OFF
              </button>
            </div>
          </div>

          {/* eth1 */}
          <div className="p-6 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center space-x-3">
                {wifiStatus.eth1_status === 'on' ? (
                  <Wifi className="w-8 h-8 text-green-600" />
                ) : (
                  <WifiOff className="w-8 h-8 text-red-600" />
                )}
                <div>
                  <h3 className="font-bold text-gray-900 dark:text-white">eth1</h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    USB WiFi Adapter
                  </p>
                </div>
              </div>
              <span
                className={`px-3 py-1 rounded-full text-sm font-semibold ${
                  wifiStatus.eth1_status === 'on'
                    ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
                    : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
                }`}
              >
                {wifiStatus.eth1_status.toUpperCase()}
              </span>
            </div>

            <div className="mb-4">
              <p className="text-xs text-gray-600 dark:text-gray-400 mb-1">IP Address</p>
              <p className="font-mono text-sm font-semibold text-gray-900 dark:text-white">
                {wifiStatus.eth1_ip}
              </p>
            </div>

            <div className="flex space-x-2">
              <button
                onClick={() => toggleInterface('eth1', 'on')}
                disabled={loading || wifiStatus.eth1_status === 'on'}
                className="btn btn-success flex-1"
              >
                Turn ON
              </button>
              <button
                onClick={() => toggleInterface('eth1', 'off')}
                disabled={loading || wifiStatus.eth1_status === 'off'}
                className="btn btn-danger flex-1"
              >
                Turn OFF
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Configured Networks */}
      <div className="card p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">
            Configured Networks (wlan0)
          </h2>
          <button
            onClick={() => setShowAddForm(!showAddForm)}
            className="btn btn-primary flex items-center space-x-2"
          >
            <Plus className="w-4 h-4" />
            <span>Add Network</span>
          </button>
        </div>

        {showAddForm && (
          <form onSubmit={addNetwork} className="mb-6 p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg space-y-4">
            <div>
              <label className="label">SSID</label>
              <input
                type="text"
                className="input"
                placeholder="Network Name"
                value={newNetwork.ssid}
                onChange={(e) => setNewNetwork({ ...newNetwork, ssid: e.target.value })}
                required
              />
            </div>
            <div>
              <label className="label">Password</label>
              <input
                type="password"
                className="input"
                placeholder="Network Password"
                minLength="8"
                value={newNetwork.psk}
                onChange={(e) => setNewNetwork({ ...newNetwork, psk: e.target.value })}
                required
              />
            </div>
            <div>
              <label className="label">Priority (higher = preferred)</label>
              <input
                type="number"
                className="input"
                min="0"
                max="100"
                value={newNetwork.priority}
                onChange={(e) => setNewNetwork({ ...newNetwork, priority: parseInt(e.target.value) })}
              />
            </div>
            <div className="flex space-x-2">
              <button
                type="submit"
                disabled={loading}
                className="btn btn-success flex-1"
              >
                Add Network
              </button>
              <button
                type="button"
                onClick={() => setShowAddForm(false)}
                className="btn btn-secondary flex-1"
              >
                Cancel
              </button>
            </div>
          </form>
        )}

        <div className="space-y-3">
          {wifiStatus.networks.length === 0 ? (
            <div className="text-center py-12 text-gray-500 dark:text-gray-400">
              <Wifi className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p>No networks configured</p>
              <p className="text-sm">Click "Add Network" to get started</p>
            </div>
          ) : (
            wifiStatus.networks.map((network) => (
              <div
                key={network.id}
                className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              >
                <div className="flex-1">
                  <h3 className="font-semibold text-gray-900 dark:text-white">
                    {network.ssid}
                  </h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    {network.status}
                  </p>
                </div>
                <div className="flex space-x-2">
                  <button
                    onClick={() => editNetwork(network.id)}
                    disabled={loading}
                    className="btn btn-secondary flex items-center space-x-1 px-3 py-2"
                    title="Change Password"
                  >
                    <Edit2 className="w-4 h-4" />
                    <span className="hidden sm:inline">Edit</span>
                  </button>
                  <button
                    onClick={() => deleteNetwork(network.id, network.ssid)}
                    disabled={loading}
                    className="btn btn-danger flex items-center space-x-1 px-3 py-2"
                    title="Delete Network"
                  >
                    <Trash2 className="w-4 h-4" />
                    <span className="hidden sm:inline">Delete</span>
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
