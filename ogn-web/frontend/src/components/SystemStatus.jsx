import { Activity, Cpu, HardDrive, Clock, Server, CheckCircle, XCircle } from 'lucide-react'

export default function SystemStatus({ systemInfo, hfssStatus }) {
  const formatUptime = (uptime) => {
    if (!uptime) return 'Unknown'
    if (uptime.includes('up')) return uptime

    // If it's a string from API, return it directly
    return uptime
  }

  const getStatusColor = (value, type) => {
    if (type === 'temp') {
      if (value > 80) return 'text-red-600'
      if (value > 70) return 'text-yellow-600'
      return 'text-green-600'
    }
    if (type === 'usage') {
      if (value > 90) return 'text-red-600'
      if (value > 75) return 'text-yellow-600'
      return 'text-green-600'
    }
    return 'text-gray-600'
  }

  return (
    <div className="space-y-6">
      {/* System Info Card */}
      <div className="card p-6">
        <div className="flex items-center space-x-3 mb-6">
          <Activity className="w-6 h-6 text-blue-600" />
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">
            System Information
          </h2>
        </div>

        {systemInfo ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Hostname */}
            <div className="p-6 bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-800/20 rounded-lg border border-blue-200 dark:border-blue-800">
              <div className="flex items-center space-x-3 mb-3">
                <Server className="w-6 h-6 text-blue-600" />
                <h3 className="font-semibold text-blue-900 dark:text-blue-200">Hostname</h3>
              </div>
              <p className="text-2xl font-bold text-blue-900 dark:text-blue-100">
                {systemInfo.hostname}
              </p>
            </div>

            {/* CPU Temperature */}
            <div className="p-6 bg-gradient-to-br from-orange-50 to-orange-100 dark:from-orange-900/20 dark:to-orange-800/20 rounded-lg border border-orange-200 dark:border-orange-800">
              <div className="flex items-center space-x-3 mb-3">
                <Cpu className="w-6 h-6 text-orange-600" />
                <h3 className="font-semibold text-orange-900 dark:text-orange-200">CPU Temp</h3>
              </div>
              <p className={`text-2xl font-bold ${getStatusColor(systemInfo.cpu_temp, 'temp')}`}>
                {systemInfo.cpu_temp !== null ? `${systemInfo.cpu_temp}°C` : 'N/A'}
              </p>
              <p className="text-xs text-orange-700 dark:text-orange-400 mt-1">
                {systemInfo.cpu_temp > 70 ? 'Running Hot' : 'Normal'}
              </p>
            </div>

            {/* Uptime */}
            <div className="p-6 bg-gradient-to-br from-green-50 to-green-100 dark:from-green-900/20 dark:to-green-800/20 rounded-lg border border-green-200 dark:border-green-800">
              <div className="flex items-center space-x-3 mb-3">
                <Clock className="w-6 h-6 text-green-600" />
                <h3 className="font-semibold text-green-900 dark:text-green-200">Uptime</h3>
              </div>
              <p className="text-lg font-bold text-green-900 dark:text-green-100">
                {formatUptime(systemInfo.uptime)}
              </p>
            </div>

            {/* Memory Usage */}
            <div className="p-6 bg-gradient-to-br from-purple-50 to-purple-100 dark:from-purple-900/20 dark:to-purple-800/20 rounded-lg border border-purple-200 dark:border-purple-800">
              <div className="flex items-center space-x-3 mb-3">
                <HardDrive className="w-6 h-6 text-purple-600" />
                <h3 className="font-semibold text-purple-900 dark:text-purple-200">Memory</h3>
              </div>
              <p className="text-lg font-bold text-purple-900 dark:text-purple-100">
                {systemInfo.memory_usage || 'N/A'}
              </p>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center py-12">
            <Activity className="w-6 h-6 animate-spin text-blue-600 mr-3" />
            <span className="text-gray-600 dark:text-gray-400">Loading system info...</span>
          </div>
        )}
      </div>

      {/* HFSS Status Card */}
      <div className="card p-6">
        <div className="flex items-center space-x-3 mb-6">
          <Server className="w-6 h-6 text-blue-600" />
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">
            HFSS Integration Status
          </h2>
        </div>

        {hfssStatus ? (
          <div className="space-y-4">
            {/* Registration Status */}
            <div className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Registration
              </span>
              <div className="flex items-center space-x-2">
                {hfssStatus.is_registered ? (
                  <>
                    <CheckCircle className="w-5 h-5 text-green-600" />
                    <span className="text-sm font-semibold text-green-600">Registered</span>
                  </>
                ) : (
                  <>
                    <XCircle className="w-5 h-5 text-gray-400" />
                    <span className="text-sm font-semibold text-gray-400">Not Registered</span>
                  </>
                )}
              </div>
            </div>

            {hfssStatus.is_registered && (
              <>
                {/* Heartbeat Status */}
                <div className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    Heartbeat
                  </span>
                  <div className="flex items-center space-x-2">
                    {hfssStatus.heartbeat_active ? (
                      <>
                        <Activity className="w-5 h-5 text-green-600 animate-pulse" />
                        <span className="text-sm font-semibold text-green-600">Active</span>
                      </>
                    ) : (
                      <>
                        <XCircle className="w-5 h-5 text-red-600" />
                        <span className="text-sm font-semibold text-red-600">Stopped</span>
                      </>
                    )}
                  </div>
                </div>

                {/* Station Details */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                    <p className="text-xs text-gray-600 dark:text-gray-400 mb-1">Station ID</p>
                    <p className="text-sm font-mono font-semibold text-gray-900 dark:text-white">
                      {hfssStatus.station_id}
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
              </>
            )}

            {!hfssStatus.is_registered && (
              <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                <Server className="w-12 h-12 mx-auto mb-4 opacity-50" />
                <p className="font-medium">Not registered with HFSS</p>
                <p className="text-sm mt-2">
                  Go to "HFSS Registration" tab to register this station
                </p>
              </div>
            )}
          </div>
        ) : (
          <div className="flex items-center justify-center py-12">
            <Activity className="w-6 h-6 animate-spin text-blue-600 mr-3" />
            <span className="text-gray-600 dark:text-gray-400">Loading HFSS status...</span>
          </div>
        )}
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="card p-6 bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-800/20 border-blue-200 dark:border-blue-800">
          <h3 className="text-sm font-semibold text-blue-900 dark:text-blue-200 mb-3">
            System Status
          </h3>
          <div className="flex items-center space-x-2">
            <CheckCircle className="w-5 h-5 text-blue-600" />
            <span className="text-lg font-bold text-blue-900 dark:text-blue-100">Operational</span>
          </div>
        </div>

        <div className="card p-6 bg-gradient-to-br from-green-50 to-green-100 dark:from-green-900/20 dark:to-green-800/20 border-green-200 dark:border-green-800">
          <h3 className="text-sm font-semibold text-green-900 dark:text-green-200 mb-3">
            OGN Receiver
          </h3>
          <div className="flex items-center space-x-2">
            <Activity className="w-5 h-5 text-green-600" />
            <span className="text-lg font-bold text-green-900 dark:text-green-100">Running</span>
          </div>
        </div>

        <div className="card p-6 bg-gradient-to-br from-purple-50 to-purple-100 dark:from-purple-900/20 dark:to-purple-800/20 border-purple-200 dark:border-purple-800">
          <h3 className="text-sm font-semibold text-purple-900 dark:text-purple-200 mb-3">
            Network
          </h3>
          <div className="flex items-center space-x-2">
            <CheckCircle className="w-5 h-5 text-purple-600" />
            <span className="text-lg font-bold text-purple-900 dark:text-purple-100">Connected</span>
          </div>
        </div>
      </div>
    </div>
  )
}
