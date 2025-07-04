<!-- frontend/src/views/Settings.vue -->
<template>
    <div class="space-y-6">
        <!-- Header -->
        <div class="sm:flex sm:items-center sm:justify-between">
            <div>
                <h1 class="text-2xl font-bold text-gray-900">System Settings</h1>
                <p class="mt-2 text-sm text-gray-700">
                    Configure global system parameters and rotation settings
                </p>
            </div>
            <div class="mt-4 sm:mt-0 sm:ml-16 sm:flex-none space-x-3 flex">
                <button
                    @click="resetToDefaults"
                    class="btn btn-secondary btn-sm"
                >
                    <ArrowPathIcon class="h-4 w-4 mr-2"/>
                    Reset to Defaults
                </button>
                <button
                    @click="saveAllSettings"
                    :disabled="isSaving"
                    class="btn btn-primary btn-sm"
                >
                    <CheckIcon class="h-4 w-4 mr-2"/>
                    {{ isSaving ? 'Saving...' : 'Save Settings' }}
                </button>
            </div>
        </div>

        <!-- System Status -->
        <div class="bg-white shadow rounded-lg p-6">
            <h3 class="text-lg font-medium text-gray-900 mb-4">System Status</h3>
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <div class="text-center">
                    <div :class="systemStatus.database.color" class="w-3 h-3 rounded-full mx-auto mb-2"></div>
                    <p class="text-sm font-medium text-gray-900">Database</p>
                    <p class="text-xs text-gray-500">{{ systemStatus.database.text }}</p>
                </div>
                <div class="text-center">
                    <div :class="systemStatus.redis.color" class="w-3 h-3 rounded-full mx-auto mb-2"></div>
                    <p class="text-sm font-medium text-gray-900">Redis</p>
                    <p class="text-xs text-gray-500">{{ systemStatus.redis.text }}</p>
                </div>
                <div class="text-center">
                    <div :class="systemStatus.proxyServer.color" class="w-3 h-3 rounded-full mx-auto mb-2"></div>
                    <p class="text-sm font-medium text-gray-900">Proxy Server</p>
                    <p class="text-xs text-gray-500">{{ systemStatus.proxyServer.text }}</p>
                </div>
                <div class="text-center">
                    <div :class="systemStatus.rotationManager.color" class="w-3 h-3 rounded-full mx-auto mb-2"></div>
                    <p class="text-sm font-medium text-gray-900">Rotation Manager</p>
                    <p class="text-xs text-gray-500">{{ systemStatus.rotationManager.text }}</p>
                </div>
            </div>
        </div>

        <!-- Rotation Settings -->
        <div class="bg-white shadow rounded-lg p-6">
            <h3 class="text-lg font-medium text-gray-900 mb-4">IP Rotation Settings</h3>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <!-- Auto Rotation -->
                <div>
                    <label class="flex items-center">
                        <input
                            v-model="settings.autoRotationEnabled"
                            type="checkbox"
                            class="rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                        >
                        <span class="ml-2 text-sm font-medium text-gray-700">
              Enable Automatic Rotation
            </span>
                    </label>
                    <p class="mt-1 text-sm text-gray-500">
                        Automatically rotate IP addresses on all devices
                    </p>
                </div>

                <!-- Default Rotation Interval -->
                <div>
                    <label class="block text-sm font-medium text-gray-700">
                        Default Rotation Interval (seconds)
                    </label>
                    <input
                        v-model.number="settings.defaultRotationInterval"
                        type="number"
                        min="60"
                        max="7200"
                        class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                    >
                    <p class="mt-1 text-sm text-gray-500">
                        Default interval for new devices (60-7200 seconds)
                    </p>
                </div>

                <!-- Max Rotation Attempts -->
                <div>
                    <label class="block text-sm font-medium text-gray-700">
                        Max Rotation Attempts
                    </label>
                    <input
                        v-model.number="settings.maxRotationAttempts"
                        type="number"
                        min="1"
                        max="10"
                        class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                    >
                    <p class="mt-1 text-sm text-gray-500">
                        Maximum retry attempts for failed rotations
                    </p>
                </div>

                <!-- Rotation Timeout -->
                <div>
                    <label class="block text-sm font-medium text-gray-700">
                        Rotation Timeout (seconds)
                    </label>
                    <input
                        v-model.number="settings.rotationTimeout"
                        type="number"
                        min="10"
                        max="300"
                        class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                    >
                    <p class="mt-1 text-sm text-gray-500">
                        Timeout for rotation operations
                    </p>
                </div>
            </div>
        </div>

        <!-- Proxy Settings -->
        <div class="bg-white shadow rounded-lg p-6">
            <h3 class="text-lg font-medium text-gray-900 mb-4">Proxy Server Settings</h3>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <!-- Max Devices -->
                <div>
                    <label class="block text-sm font-medium text-gray-700">
                        Maximum Devices
                    </label>
                    <input
                        v-model.number="settings.maxDevices"
                        type="number"
                        min="1"
                        max="1000"
                        class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                    >
                    <p class="mt-1 text-sm text-gray-500">
                        Maximum number of devices allowed
                    </p>
                </div>

                <!-- Max Requests per Minute -->
                <div>
                    <label class="block text-sm font-medium text-gray-700">
                        Max Requests per Minute (per device)
                    </label>
                    <input
                        v-model.number="settings.maxRequestsPerMinute"
                        type="number"
                        min="1"
                        max="10000"
                        class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                    >
                    <p class="mt-1 text-sm text-gray-500">
                        Rate limit for each device
                    </p>
                </div>

                <!-- Request Timeout -->
                <div>
                    <label class="block text-sm font-medium text-gray-700">
                        Request Timeout (seconds)
                    </label>
                    <input
                        v-model.number="settings.requestTimeout"
                        type="number"
                        min="5"
                        max="300"
                        class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                    >
                    <p class="mt-1 text-sm text-gray-500">
                        Timeout for proxy requests
                    </p>
                </div>

                <!-- Connection Pool Size -->
                <div>
                    <label class="block text-sm font-medium text-gray-700">
                        Connection Pool Size
                    </label>
                    <input
                        v-model.number="settings.connectionPoolSize"
                        type="number"
                        min="10"
                        max="1000"
                        class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                    >
                    <p class="mt-1 text-sm text-gray-500">
                        Maximum concurrent connections
                    </p>
                </div>
            </div>
        </div>

        <!-- Monitoring Settings -->
        <div class="bg-white shadow rounded-lg p-6">
            <h3 class="text-lg font-medium text-gray-900 mb-4">Monitoring & Logging</h3>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <!-- Health Check Interval -->
                <div>
                    <label class="block text-sm font-medium text-gray-700">
                        Health Check Interval (seconds)
                    </label>
                    <input
                        v-model.number="settings.healthCheckInterval"
                        type="number"
                        min="10"
                        max="300"
                        class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                    >
                    <p class="mt-1 text-sm text-gray-500">
                        Interval for device health checks
                    </p>
                </div>

                <!-- Heartbeat Timeout -->
                <div>
                    <label class="block text-sm font-medium text-gray-700">
                        Heartbeat Timeout (seconds)
                    </label>
                    <input
                        v-model.number="settings.heartbeatTimeout"
                        type="number"
                        min="30"
                        max="600"
                        class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                    >
                    <p class="mt-1 text-sm text-gray-500">
                        Timeout for device heartbeat
                    </p>
                </div>

                <!-- Log Retention Days -->
                <div>
                    <label class="block text-sm font-medium text-gray-700">
                        Log Retention (days)
                    </label>
                    <input
                        v-model.number="settings.logRetentionDays"
                        type="number"
                        min="1"
                        max="365"
                        class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                    >
                    <p class="mt-1 text-sm text-gray-500">
                        Number of days to keep logs
                    </p>
                </div>

                <!-- Stats Retention Days -->
                <div>
                    <label class="block text-sm font-medium text-gray-700">
                        Statistics Retention (days)
                    </label>
                    <input
                        v-model.number="settings.statsRetentionDays"
                        type="number"
                        min="1"
                        max="365"
                        class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                    >
                    <p class="mt-1 text-sm text-gray-500">
                        Number of days to keep statistics
                    </p>
                </div>
            </div>
        </div>

        <!-- Notifications Settings -->
        <div class="bg-white shadow rounded-lg p-6">
            <h3 class="text-lg font-medium text-gray-900 mb-4">Notification Settings</h3>
            <div class="space-y-4">
                <!-- Email Notifications -->
                <div>
                    <label class="flex items-center">
                        <input
                            v-model="settings.emailNotificationsEnabled"
                            type="checkbox"
                            class="rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                        >
                        <span class="ml-2 text-sm font-medium text-gray-700">
              Enable Email Notifications
            </span>
                    </label>
                </div>

                <!-- Admin Email -->
                <div v-if="settings.emailNotificationsEnabled">
                    <label class="block text-sm font-medium text-gray-700">
                        Admin Email Address
                    </label>
                    <input
                        v-model="settings.adminEmail"
                        type="email"
                        class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                    >
                    <p class="mt-1 text-sm text-gray-500">
                        Email address for system notifications
                    </p>
                </div>

                <!-- Telegram Notifications -->
                <div>
                    <label class="flex items-center">
                        <input
                            v-model="settings.telegramNotificationsEnabled"
                            type="checkbox"
                            class="rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                        >
                        <span class="ml-2 text-sm font-medium text-gray-700">
              Enable Telegram Notifications
            </span>
                    </label>
                </div>

                <!-- Telegram Bot Token -->
                <div v-if="settings.telegramNotificationsEnabled">
                    <label class="block text-sm font-medium text-gray-700">
                        Telegram Bot Token
                    </label>
                    <input
                        v-model="settings.telegramBotToken"
                        type="password"
                        class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                    >
                    <p class="mt-1 text-sm text-gray-500">
                        Bot token for Telegram notifications
                    </p>
                </div>

                <!-- Telegram Chat ID -->
                <div v-if="settings.telegramNotificationsEnabled">
                    <label class="block text-sm font-medium text-gray-700">
                        Telegram Chat ID
                    </label>
                    <input
                        v-model="settings.telegramChatId"
                        type="text"
                        class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                    >
                    <p class="mt-1 text-sm text-gray-500">
                        Chat ID for notifications
                    </p>
                </div>
            </div>
        </div>

        <!-- Alert Thresholds -->
        <div class="bg-white shadow rounded-lg p-6">
            <h3 class="text-lg font-medium text-gray-900 mb-4">Alert Thresholds</h3>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <!-- Device Offline Threshold -->
                <div>
                    <label class="block text-sm font-medium text-gray-700">
                        Device Offline Alert (minutes)
                    </label>
                    <input
                        v-model.number="settings.deviceOfflineThreshold"
                        type="number"
                        min="1"
                        max="60"
                        class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                    >
                    <p class="mt-1 text-sm text-gray-500">
                        Alert when device is offline for this duration
                    </p>
                </div>

                <!-- Success Rate Threshold -->
                <div>
                    <label class="block text-sm font-medium text-gray-700">
                        Success Rate Alert (%)
                    </label>
                    <input
                        v-model.number="settings.successRateThreshold"
                        type="number"
                        min="50"
                        max="100"
                        class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                    >
                    <p class="mt-1 text-sm text-gray-500">
                        Alert when success rate drops below this percentage
                    </p>
                </div>

                <!-- Response Time Threshold -->
                <div>
                    <label class="block text-sm font-medium text-gray-700">
                        Response Time Alert (ms)
                    </label>
                    <input
                        v-model.number="settings.responseTimeThreshold"
                        type="number"
                        min="100"
                        max="10000"
                        class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                    >
                    <p class="mt-1 text-sm text-gray-500">
                        Alert when average response time exceeds this value
                    </p>
                </div>

                <!-- Rotation Failure Threshold -->
                <div>
                    <label class="block text-sm font-medium text-gray-700">
                        Rotation Failure Alert (%)
                    </label>
                    <input
                        v-model.number="settings.rotationFailureThreshold"
                        type="number"
                        min="10"
                        max="100"
                        class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                    >
                    <p class="mt-1 text-sm text-gray-500">
                        Alert when rotation failure rate exceeds this percentage
                    </p>
                </div>
            </div>
        </div>

        <!-- System Actions -->
        <div class="bg-white shadow rounded-lg p-6">
            <h3 class="text-lg font-medium text-gray-900 mb-4">System Actions</h3>
            <div class="space-y-4">
                <div class="flex items-center justify-between p-4 border border-gray-200 rounded-lg">
                    <div>
                        <h4 class="text-sm font-medium text-gray-900">Restart System Components</h4>
                        <p class="text-sm text-gray-500">Restart rotation manager and proxy server</p>
                    </div>
                    <button
                        @click="restartSystem"
                        :disabled="isRestarting"
                        class="btn btn-warning btn-sm"
                    >
                        <ArrowPathIcon class="h-4 w-4 mr-2"/>
                        {{ isRestarting ? 'Restarting...' : 'Restart' }}
                    </button>
                </div>

                <div class="flex items-center justify-between p-4 border border-gray-200 rounded-lg">
                    <div>
                        <h4 class="text-sm font-medium text-gray-900">Clear Old Logs</h4>
                        <p class="text-sm text-gray-500">Remove logs older than retention period</p>
                    </div>
                    <button
                        @click="clearOldLogs"
                        :disabled="isClearing"
                        class="btn btn-secondary btn-sm"
                    >
                        <TrashIcon class="h-4 w-4 mr-2"/>
                        {{ isClearing ? 'Clearing...' : 'Clear Logs' }}
                    </button>
                </div>

                <div class="flex items-center justify-between p-4 border border-gray-200 rounded-lg">
                    <div>
                        <h4 class="text-sm font-medium text-gray-900">Export System Configuration</h4>
                        <p class="text-sm text-gray-500">Download current system configuration as JSON</p>
                    </div>
                    <button
                        @click="exportConfiguration"
                        class="btn btn-secondary btn-sm"
                    >
                        <DocumentArrowDownIcon class="h-4 w-4 mr-2"/>
                        Export Config
                    </button>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup>
import {ref, onMounted} from 'vue'
import {useToast} from 'vue-toastification'
import api from '@/utils/api'

// Icons
import {
    CheckIcon,
    ArrowPathIcon,
    TrashIcon,
    DocumentArrowDownIcon
} from '@heroicons/vue/24/outline'

const toast = useToast()

// State
const isSaving = ref(false)
const isRestarting = ref(false)
const isClearing = ref(false)

// System Status
const systemStatus = ref({
    database: {text: 'Unknown', color: 'bg-gray-400'},
    redis: {text: 'Unknown', color: 'bg-gray-400'},
    proxyServer: {text: 'Unknown', color: 'bg-gray-400'},
    rotationManager: {text: 'Unknown', color: 'bg-gray-400'}
})

// Settings
const settings = ref({
    // Rotation Settings
    autoRotationEnabled: true,
    defaultRotationInterval: 600,
    maxRotationAttempts: 3,
    rotationTimeout: 60,

    // Proxy Settings
    maxDevices: 50,
    maxRequestsPerMinute: 100,
    requestTimeout: 30,
    connectionPoolSize: 100,

    // Monitoring Settings
    healthCheckInterval: 30,
    heartbeatTimeout: 60,
    logRetentionDays: 30,
    statsRetentionDays: 90,

    // Notification Settings
    emailNotificationsEnabled: false,
    adminEmail: '',
    telegramNotificationsEnabled: false,
    telegramBotToken: '',
    telegramChatId: '',

    // Alert Thresholds
    deviceOfflineThreshold: 5,
    successRateThreshold: 85,
    responseTimeThreshold: 5000,
    rotationFailureThreshold: 20
})

// Default settings for reset
const defaultSettings = {...settings.value}

// Methods
const fetchSystemStatus = async () => {
    try {
        const response = await api.get('/admin/system/health')
        const components = response.data.components

        systemStatus.value = {
            database: {
                text: components.database === 'up' ? 'Connected' : 'Disconnected',
                color: components.database === 'up' ? 'bg-green-400' : 'bg-red-400'
            },
            redis: {
                text: components.redis === 'up' ? 'Connected' : 'Disconnected',
                color: components.redis === 'up' ? 'bg-green-400' : 'bg-red-400'
            },
            proxyServer: {
                text: components.proxy_server === 'running' ? 'Running' : 'Stopped',
                color: components.proxy_server === 'running' ? 'bg-green-400' : 'bg-red-400'
            },
            rotationManager: {
                text: components.modem_manager === 'up' ? 'Running' : 'Stopped',
                color: components.modem_manager === 'up' ? 'bg-green-400' : 'bg-red-400'
            }
        }
    } catch (error) {
        console.error('Failed to fetch system status:', error)
    }
}

const fetchSettings = async () => {
    try {
        const response = await api.get('/admin/system/config')

        // Map API response to settings object
        const config = response.data

        settings.value = {
            autoRotationEnabled: config.auto_rotation_enabled ?? true,
            defaultRotationInterval: config.default_rotation_interval ?? 600,
            maxRotationAttempts: config.max_rotation_attempts ?? 3,
            rotationTimeout: config.rotation_timeout ?? 60,
            maxDevices: config.max_devices ?? 50,
            maxRequestsPerMinute: config.max_requests_per_minute ?? 100,
            requestTimeout: config.request_timeout ?? 30,
            connectionPoolSize: config.connection_pool_size ?? 100,
            healthCheckInterval: config.health_check_interval ?? 30,
            heartbeatTimeout: config.heartbeat_timeout ?? 60,
            logRetentionDays: config.log_retention_days ?? 30,
            statsRetentionDays: config.stats_retention_days ?? 90,
            emailNotificationsEnabled: config.email_notifications_enabled ?? false,
            adminEmail: config.admin_email ?? '',
            telegramNotificationsEnabled: config.telegram_notifications_enabled ?? false,
            telegramBotToken: config.telegram_bot_token ?? '',
            telegramChatId: config.telegram_chat_id ?? '',
            deviceOfflineThreshold: config.device_offline_threshold ?? 5,
            successRateThreshold: config.success_rate_threshold ?? 85,
            responseTimeThreshold: config.response_time_threshold ?? 5000,
            rotationFailureThreshold: config.rotation_failure_threshold ?? 20
        }
    } catch (error) {
        console.error('Failed to fetch settings:', error)
        toast.error('Failed to load settings')
    }
}

const saveAllSettings = async () => {
    try {
        isSaving.value = true

        // Convert settings to API format
        const config = {
            auto_rotation_enabled: settings.value.autoRotationEnabled,
            default_rotation_interval: settings.value.defaultRotationInterval,
            max_rotation_attempts: settings.value.maxRotationAttempts,
            rotation_timeout: settings.value.rotationTimeout,
            max_devices: settings.value.maxDevices,
            max_requests_per_minute: settings.value.maxRequestsPerMinute,
            request_timeout: settings.value.requestTimeout,
            connection_pool_size: settings.value.connectionPoolSize,
            health_check_interval: settings.value.healthCheckInterval,
            heartbeat_timeout: settings.value.heartbeatTimeout,
            log_retention_days: settings.value.logRetentionDays,
            stats_retention_days: settings.value.statsRetentionDays,
            email_notifications_enabled: settings.value.emailNotificationsEnabled,
            admin_email: settings.value.adminEmail,
            telegram_notifications_enabled: settings.value.telegramNotificationsEnabled,
            telegram_bot_token: settings.value.telegramBotToken,
            telegram_chat_id: settings.value.telegramChatId,
            device_offline_threshold: settings.value.deviceOfflineThreshold,
            success_rate_threshold: settings.value.successRateThreshold,
            response_time_threshold: settings.value.responseTimeThreshold,
            rotation_failure_threshold: settings.value.rotationFailureThreshold
        }

        await api.put('/admin/system/config', config)
        toast.success('Settings saved successfully')
    } catch (error) {
        console.error('Failed to save settings:', error)
        toast.error('Failed to save settings')
    } finally {
        isSaving.value = false
    }
}

const resetToDefaults = () => {
    if (confirm('Are you sure you want to reset all settings to defaults?')) {
        settings.value = {...defaultSettings}
        toast.info('Settings reset to defaults')
    }
}

const restartSystem = async () => {
    if (!confirm('Are you sure you want to restart system components? This may temporarily interrupt service.')) {
        return
    }

    try {
        isRestarting.value = true
        await api.post('/admin/system/restart')
        toast.success('System components restarted successfully')

        // Refresh status after restart
        setTimeout(fetchSystemStatus, 2000)
    } catch (error) {
        console.error('Failed to restart system:', error)
        toast.error('Failed to restart system')
    } finally {
        isRestarting.value = false
    }
}

const clearOldLogs = async () => {
    if (!confirm('Are you sure you want to clear old logs? This action cannot be undone.')) {
        return
    }

    try {
        isClearing.value = true
        const response = await api.delete(`/admin/logs/cleanup?days_to_keep=${settings.value.logRetentionDays}`)
        toast.success(response.data.message || 'Old logs cleared successfully')
    } catch (error) {
        console.error('Failed to clear logs:', error)
        toast.error('Failed to clear logs')
    } finally {
        isClearing.value = false
    }
}

const exportConfiguration = async () => {
    try {
        const config = {
            settings: settings.value,
            exported_at: new Date().toISOString(),
            version: '1.0'
        }

        const blob = new Blob([JSON.stringify(config, null, 2)], {type: 'application/json'})
        const url = window.URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.href = url
        link.download = `proxy-config-${new Date().toISOString().split('T')[0]}.json`
        link.click()
        window.URL.revokeObjectURL(url)

        toast.success('Configuration exported successfully')
    } catch (error) {
        console.error('Failed to export configuration:', error)
        toast.error('Failed to export configuration')
    }
}

// Lifecycle
onMounted(async () => {
    await Promise.all([
        fetchSystemStatus(),
        fetchSettings()
    ])
})
</script>
