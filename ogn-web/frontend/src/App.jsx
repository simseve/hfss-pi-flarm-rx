import { useState, useEffect } from 'react'
import axios from 'axios'
import {
  Radio,
  Wifi,
  WifiOff,
  Settings,
  Save,
  Globe,
  MapPin,
  Activity,
  Server,
  CheckCircle,
  XCircle,
  AlertCircle,
  Plus,
  Trash2,
  Edit2,
  RefreshCw
} from 'lucide-react'

import HFSSRegistration from './components/HFSSRegistration'
import OGNConfig from './components/OGNConfig'
import WiFiManagement from './components/WiFiManagement'
import SystemStatus from './components/SystemStatus'

const API_BASE = '/api'

function App() {
  const [activeTab, setActiveTab] = useState('config')
  const [notification, setNotification] = useState(null)
  const [systemInfo, setSystemInfo] = useState(null)
  const [hfssStatus, setHFSSStatus] = useState(null)

  useEffect(() => {
    loadSystemInfo()
    loadHFSSStatus()
    const interval = setInterval(() => {
      loadSystemInfo()
      loadHFSSStatus()
    }, 30000) // Refresh every 30 seconds
    return () => clearInterval(interval)
  }, [])

  const loadSystemInfo = async () => {
    try {
      const response = await axios.get(`${API_BASE}/system`)
      setSystemInfo(response.data)
    } catch (error) {
      console.error('Failed to load system info:', error)
    }
  }

  const loadHFSSStatus = async () => {
    try {
      const response = await axios.get(`${API_BASE}/hfss/status`)
      setHFSSStatus(response.data)
    } catch (error) {
      console.error('Failed to load HFSS status:', error)
    }
  }

  const showNotification = (message, type = 'success') => {
    setNotification({ message, type })
    setTimeout(() => setNotification(null), 5000)
  }

  const tabs = [
    { id: 'config', label: 'OGN Configuration', icon: Radio },
    { id: 'wifi', label: 'WiFi Management', icon: Wifi },
    { id: 'hfss', label: 'HFSS Registration', icon: Server },
    { id: 'status', label: 'System Status', icon: Activity }
  ]

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-800">
      {/* Header */}
      <header className="bg-white dark:bg-gray-800 shadow-md border-b border-gray-200 dark:border-gray-700">
        <div className="container mx-auto px-4 py-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <Radio className="w-8 h-8 text-blue-600" />
              <div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                  OGN Receiver Configuration
                </h1>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  {systemInfo?.hostname || 'Loading...'}
                </p>
              </div>
            </div>

            {hfssStatus?.is_registered && (
              <div className="flex items-center space-x-2 bg-green-100 dark:bg-green-900/30 px-4 py-2 rounded-lg">
                <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400" />
                <span className="text-sm font-medium text-green-700 dark:text-green-300">
                  HFSS Connected
                </span>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Navigation Tabs */}
      <nav className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 sticky top-0 z-10">
        <div className="container mx-auto px-4">
          <div className="flex space-x-1">
            {tabs.map((tab) => {
              const Icon = tab.icon
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center space-x-2 px-6 py-4 font-medium transition-all ${
                    activeTab === tab.id
                      ? 'text-blue-600 dark:text-blue-400 border-b-2 border-blue-600 dark:border-blue-400'
                      : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
                  }`}
                >
                  <Icon className="w-5 h-5" />
                  <span>{tab.label}</span>
                </button>
              )
            })}
          </div>
        </div>
      </nav>

      {/* Notification */}
      {notification && (
        <div className="container mx-auto px-4 mt-6">
          <div
            className={`flex items-center space-x-3 p-4 rounded-lg ${
              notification.type === 'success'
                ? 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-200'
                : notification.type === 'error'
                ? 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-200'
                : 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-200'
            }`}
          >
            {notification.type === 'success' && <CheckCircle className="w-5 h-5" />}
            {notification.type === 'error' && <XCircle className="w-5 h-5" />}
            {notification.type === 'warning' && <AlertCircle className="w-5 h-5" />}
            <span className="font-medium">{notification.message}</span>
          </div>
        </div>
      )}

      {/* Main Content */}
      <main className="container mx-auto px-4 py-8">
        {activeTab === 'config' && (
          <OGNConfig showNotification={showNotification} />
        )}
        {activeTab === 'wifi' && (
          <WiFiManagement showNotification={showNotification} />
        )}
        {activeTab === 'hfss' && (
          <HFSSRegistration
            showNotification={showNotification}
            hfssStatus={hfssStatus}
            refreshStatus={loadHFSSStatus}
          />
        )}
        {activeTab === 'status' && (
          <SystemStatus systemInfo={systemInfo} hfssStatus={hfssStatus} />
        )}
      </main>

      {/* Footer */}
      <footer className="bg-white dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700 mt-12">
        <div className="container mx-auto px-4 py-6">
          <div className="flex justify-between items-center text-sm text-gray-600 dark:text-gray-400">
            <p>OGN Receiver Configuration v2.0.0</p>
            <p>Built with React + FastAPI + Uvicorn</p>
          </div>
        </div>
      </footer>
    </div>
  )
}

export default App
