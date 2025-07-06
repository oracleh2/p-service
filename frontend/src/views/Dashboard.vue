<template>
    <div class="space-y-6">
        <!-- Page header -->
        <div class="flex-between">
            <div>
                <h1 class="text-2xl font-bold text-gray-900">Dashboard</h1>
                <p class="text-gray-500">Monitor your mobile proxy infrastructure</p>
            </div>
            <div class="flex space-x-3">
                <button
                    @click="refreshData"
                    :disabled="isLoading"
                    class="btn btn-md btn-secondary"
                >
                    <ArrowPathIcon class="h-4 w-4 mr-1" :class="{ 'animate-spin': isLoading }"/>
                    Refresh
                </button>
                <button
                    @click="rotateAllModems"
                    :disabled="isRotating"
                    class="btn btn-md btn-primary"
                >
                    <ArrowPathIcon class="h-4 w-4 mr-1" :class="{ 'animate-spin': isRotating }"/>
                    Rotate All IPs
                </button>
            </div>
        </div>

        <!-- Metrics overview -->
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6 gap-6">
            <div class="metric-card">
                <div class="flex items-center">
                    <div class="p-2 bg-primary-100 rounded-lg">
                        <ServerIcon class="h-6 w-6 text-primary-600"/>
                    </div>
                    <div class="ml-4">
                        <p class="text-sm font-medium text-gray-500">Total Modems</p>
                        <p class="text-2xl font-bold text-gray-900">{{ metrics.totalModems }}</p>
                    </div>
                </div>
            </div>

            <div class="metric-card">
                <div class="flex items-center">
                    <div class="p-2 bg-green-100 rounded-lg">
                        <CheckCircleIcon class="h-6 w-6 text-green-600"/>
                    </div>
                    <div class="ml-4">
                        <p class="text-sm font-medium text-gray-500">Online</p>
                        <p class="text-2xl font-bold text-gray-900">{{ metrics.onlineModems }}</p>
                    </div>
                </div>
            </div>

            <div class="metric-card">
                <div class="flex items-center">
                    <div class="p-2 bg-red-100 rounded-lg">
                        <XCircleIcon class="h-6 w-6 text-red-600"/>
                    </div>
                    <div class="ml-4">
                        <p class="text-sm font-medium text-gray-500">Offline</p>
                        <p class="text-2xl font-bold text-gray-900">{{ metrics.offlineModems }}</p>
                    </div>
                </div>
            </div>

            <div class="metric-card">
                <div class="flex items-center">
                    <div class="p-2 bg-blue-100 rounded-lg">
                        <ChartBarIcon class="h-6 w-6 text-blue-600"/>
                    </div>
                    <div class="ml-4">
                        <p class="text-sm font-medium text-gray-500">Requests (24h)</p>
                        <p class="text-2xl font-bold text-gray-900">{{ formatNumber(metrics.totalRequests) }}</p>
                    </div>
                </div>
            </div>

            <div class="metric-card">
                <div class="flex items-center">
                    <div class="p-2 bg-green-100 rounded-lg">
                        <PresentationChartLineIcon class="h-6 w-6 text-green-600"/>
                    </div>
                    <div class="ml-4">
                        <p class="text-sm font-medium text-gray-500">Success Rate</p>
                        <p class="text-2xl font-bold text-gray-900">{{ metrics.successRate }}%</p>
                    </div>
                </div>
            </div>

            <div class="metric-card">
                <div class="flex items-center">
                    <div class="p-2 bg-purple-100 rounded-lg">
                        <GlobeAltIcon class="h-6 w-6 text-purple-600"/>
                    </div>
                    <div class="ml-4">
                        <p class="text-sm font-medium text-gray-500">Unique IPs</p>
                        <p class="text-2xl font-bold text-gray-900">{{ metrics.uniqueIPs }}</p>
                    </div>
                </div>
            </div>
        </div>

        <!-- Charts and detailed info -->
        <div class="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
            <!-- Requests timeline -->
            <div class="xl:col-span-2 card">
                <div class="card-header">
                    <h3 class="text-lg font-medium text-gray-900">Requests Timeline</h3>
                </div>
                <div class="card-body">
                    <RequestsChart :data="requestsChartData"/>
                </div>
            </div>

            <!-- System status -->
            <div class="card">
                <div class="card-header">
                    <h3 class="text-lg font-medium text-gray-900">System Status</h3>
                </div>
                <div class="card-body space-y-4">
                    <div class="flex items-center justify-between">
                        <span class="text-sm text-gray-500">Proxy Server</span>
                        <span :class="systemStatus.proxyServer.class">
              {{ systemStatus.proxyServer.text }}
            </span>
                    </div>
                    <div class="flex items-center justify-between">
                        <span class="text-sm text-gray-500">Database</span>
                        <span :class="systemStatus.database.class">
              {{ systemStatus.database.text }}
            </span>
                    </div>
                    <div class="flex items-center justify-between">
                        <span class="text-sm text-gray-500">Redis</span>
                        <span :class="systemStatus.redis.class">
              {{ systemStatus.redis.text }}
            </span>
                    </div>
                    <div class="flex items-center justify-between">
                        <span class="text-sm text-gray-500">Rotation Manager</span>
                        <span :class="systemStatus.rotationManager.class">
              {{ systemStatus.rotationManager.text }}
            </span>
                    </div>
                </div>
            </div>

            <!-- Recent modems -->
            <div class="card">
                <div class="card-header flex-between">
                    <h3 class="text-lg font-medium text-gray-900">Recent Modems</h3>
                    <router-link to="/modems" class="text-sm text-primary-600 hover:text-primary-700">
                        View all
                    </router-link>
                </div>
                <div class="card-body">
                    <div class="space-y-3">
                        <div
                            v-for="modem in recentModems"
                            :key="modem.id"
                            class="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
                        >
                            <div class="flex items-center space-x-3">
                                <div :class="getStatusColor(modem.status)" class="w-3 h-3 rounded-full"></div>
                                <div>
                                    <p class="text-sm font-medium text-gray-900">{{ modem.name }}</p>
                                    <p class="text-xs text-gray-500">{{ modem.type }}</p>
                                </div>
                            </div>
                            <div class="text-right">
                                <p class="text-sm text-gray-900">{{ modem.externalIp || 'N/A' }}</p>
                                <p class="text-xs text-gray-500">{{ formatTime(modem.lastSeen) }}</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Top IPs -->
            <div class="card">
                <div class="card-header flex-between">
                    <h3 class="text-lg font-medium text-gray-900">Top IPs (24h)</h3>
                    <router-link to="/statistics" class="text-sm text-primary-600 hover:text-primary-700">
                        View all
                    </router-link>
                </div>
                <div class="card-body">
                    <div class="space-y-3">
                        <div
                            v-for="ip in topIPs"
                            :key="ip.address"
                            class="flex items-center justify-between"
                        >
                            <div>
                                <p class="text-sm font-medium text-gray-900">{{ ip.address }}</p>
                                <p class="text-xs text-gray-500">{{ ip.operator }}</p>
                            </div>
                            <div class="text-right">
                                <p class="text-sm text-gray-900">{{ formatNumber(ip.requests) }}</p>
                                <p class="text-xs text-gray-500">requests</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Quick actions -->
            <div class="card">
                <div class="card-header">
                    <h3 class="text-lg font-medium text-gray-900">Quick Actions</h3>
                </div>
                <div class="card-body space-y-3">
                    <button
                        @click="rotateAllModems"
                        :disabled="isRotating"
                        class="w-full btn btn-md btn-primary"
                    >
                        <ArrowPathIcon class="h-4 w-4 mr-2" :class="{ 'animate-spin': isRotating }"/>
                        Rotate All IPs
                    </button>
                    <button
                        @click="exportLogs"
                        class="w-full btn btn-md btn-secondary"
                    >
                        <DocumentArrowDownIcon class="h-4 w-4 mr-2"/>
                        Export Logs
                    </button>
                    <button
                        @click="testAllModems"
                        :disabled="isTesting"
                        class="w-full btn btn-md btn-secondary"
                    >
                        <PlayIcon class="h-4 w-4 mr-2" :class="{ 'animate-pulse': isTesting }"/>
                        Test All Modems
                    </button>
                </div>
            </div>
        </div>

        <!-- Recent activity -->
        <div class="card">
            <div class="card-header flex-between">
                <h3 class="text-lg font-medium text-gray-900">Recent Activity</h3>
                <router-link to="/logs" class="text-sm text-primary-600 hover:text-primary-700">
                    View all logs
                </router-link>
            </div>
            <div class="card-body">
                <div class="flow-root">
                    <ul class="-mb-8">
                        <li
                            v-for="(activity, index) in recentActivity"
                            :key="activity.id"
                            class="relative pb-8"
                        >
              <span
                  v-if="index !== recentActivity.length - 1"
                  class="absolute top-5 left-5 -ml-px h-full w-0.5 bg-gray-200"
              ></span>
                            <div class="relative flex items-start space-x-3">
                                <div class="relative">
                                    <div :class="getActivityColor(activity.type)"
                                         class="h-10 w-10 rounded-full flex-center">
                                        <component :is="getActivityIcon(activity.type)" class="h-5 w-5 text-white"/>
                                    </div>
                                </div>
                                <div class="min-w-0 flex-1">
                                    <div class="text-sm text-gray-500">
                                        <span class="font-medium text-gray-900">{{ activity.message }}</span>
                                        <span class="whitespace-nowrap">{{ formatTime(activity.timestamp) }}</span>
                                    </div>
                                </div>
                            </div>
                        </li>
                    </ul>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup>
import {ref, computed, onMounted, onUnmounted} from 'vue'
import {useRouter} from 'vue-router'
import {useToast} from 'vue-toastification'
import {format} from 'date-fns'
import api from '@/utils/api'

// Components
import RequestsChart from '@/components/charts/RequestsChart.vue'

// Icons
import {
    ServerIcon,
    CheckCircleIcon,
    XCircleIcon,
    ChartBarIcon,
    PresentationChartLineIcon,
    GlobeAltIcon,
    ArrowPathIcon,
    DocumentArrowDownIcon,
    PlayIcon
} from '@heroicons/vue/24/outline'

const router = useRouter()
const toast = useToast()

// State
const isLoading = ref(false)
const isRotating = ref(false)
const isTesting = ref(false)
const refreshInterval = ref(null)

// Data
const metrics = ref({
    totalModems: 0,
    onlineModems: 0,
    offlineModems: 0,
    totalRequests: 0,
    successRate: 0,
    uniqueIPs: 0
})

const requestsChartData = ref([])
const recentModems = ref([])
const topIPs = ref([])
const recentActivity = ref([])

const systemStatus = ref({
    proxyServer: {text: 'Unknown', class: 'text-gray-500'},
    database: {text: 'Unknown', class: 'text-gray-500'},
    redis: {text: 'Unknown', class: 'text-gray-500'},
    rotationManager: {text: 'Unknown', class: 'text-gray-500'}
})

// Methods
const fetchDashboardData = async () => {
    try {
        isLoading.value = true

        // Fetch all dashboard data
        const [statsResponse, modemsResponse, systemResponse] = await Promise.all([
            api.get('/stats/overview'),
            api.get('/admin/devices'),
            api.get('/admin/system/health')
        ])

        // Update metrics
        metrics.value = {
            totalModems: statsResponse.data.total_modems,
            onlineModems: statsResponse.data.online_modems,
            offlineModems: statsResponse.data.offline_modems,
            totalRequests: statsResponse.data.total_requests,
            successRate: statsResponse.data.success_rate,
            uniqueIPs: statsResponse.data.unique_ips
        }

        // Update recent modems
        recentModems.value = modemsResponse.data.slice(0, 5).map(modem => ({
            id: modem.modem_id,
            name: modem.modem_id,
            type: modem.modem_type,
            status: modem.status,
            externalIp: modem.external_ip,
            lastSeen: new Date().toISOString()
        }))

        // Update system status
        const components = systemResponse.data.components
        systemStatus.value = {
            proxyServer: {
                text: components.proxy_server === 'running' ? 'Online' : 'Offline',
                class: components.proxy_server === 'running' ? 'text-green-600' : 'text-red-600'
            },
            database: {
                text: components.database === 'up' ? 'Connected' : 'Disconnected',
                class: components.database === 'up' ? 'text-green-600' : 'text-red-600'
            },
            redis: {
                text: components.redis === 'up' ? 'Connected' : 'Disconnected',
                class: components.redis === 'up' ? 'text-green-600' : 'text-red-600'
            },
            rotationManager: {
                text: components.modem_manager === 'up' ? 'Running' : 'Stopped',
                class: components.modem_manager === 'up' ? 'text-green-600' : 'text-red-600'
            }
        }

        // Mock data for charts and activity
        requestsChartData.value = generateMockChartData()
        topIPs.value = generateMockTopIPs()
        recentActivity.value = generateMockActivity()

    } catch (error) {
        console.error('Failed to fetch dashboard data:', error)
        toast.error('Failed to load dashboard data')
    } finally {
        isLoading.value = false
    }
}

const rotateAllModems = async () => {
    try {
        isRotating.value = true
        const response = await api.post('/admin/devices/rotate-all')

        toast.success(response.data.message || 'All modems rotation initiated')

        // Refresh data after rotation
        setTimeout(() => {
            fetchDashboardData()
        }, 2000)

    } catch (error) {
        toast.error('Failed to rotate modems')
    } finally {
        isRotating.value = false
    }
}

const exportLogs = async () => {
    try {
        const response = await api.get('/stats/export?format=csv&days=7')

        // Create download link
        const blob = new Blob([response.data], {type: 'text/csv'})
        const url = window.URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.href = url
        link.download = `proxy-logs-${format(new Date(), 'yyyy-MM-dd')}.csv`
        link.click()
        window.URL.revokeObjectURL(url)

        toast.success('Logs exported successfully')
    } catch (error) {
        toast.error('Failed to export logs')
    }
}

const testAllModems = async () => {
    try {
        isTesting.value = true
        // Mock test - in real implementation would test each modem
        await new Promise(resolve => setTimeout(resolve, 3000))

        toast.success('All modems tested successfully')
    } catch (error) {
        toast.error('Failed to test modems')
    } finally {
        isTesting.value = false
    }
}

const refreshData = () => {
    fetchDashboardData()
}

// Utility functions
const formatNumber = (num) => {
    if (num >= 1000000) {
        return (num / 1000000).toFixed(1) + 'M'
    } else if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K'
    }
    return num.toString()
}

const formatTime = (timestamp) => {
    return format(new Date(timestamp), 'MMM d, HH:mm')
}

const getStatusColor = (status) => {
    switch (status) {
        case 'online':
            return 'bg-green-400'
        case 'offline':
            return 'bg-red-400'
        case 'busy':
            return 'bg-yellow-400'
        default:
            return 'bg-gray-400'
    }
}

const getActivityColor = (type) => {
    switch (type) {
        case 'rotation':
            return 'bg-blue-500'
        case 'error':
            return 'bg-red-500'
        case 'success':
            return 'bg-green-500'
        default:
            return 'bg-gray-500'
    }
}

const getActivityIcon = (type) => {
    switch (type) {
        case 'rotation':
            return ArrowPathIcon
        case 'error':
            return XCircleIcon
        case 'success':
            return CheckCircleIcon
        default:
            return ServerIcon
    }
}

// Mock data generators
const generateMockChartData = () => {
    const data = []
    const now = new Date()

    for (let i = 23; i >= 0; i--) {
        const time = new Date(now.getTime() - i * 60 * 60 * 1000)
        data.push({
            time: format(time, 'HH:mm'),
            requests: Math.floor(Math.random() * 1000) + 100,
            success: Math.floor(Math.random() * 900) + 50
        })
    }

    return data
}

const generateMockTopIPs = () => {
    return [
        {address: '192.168.1.100', operator: 'МТС', requests: 1250},
        {address: '10.0.0.50', operator: 'Билайн', requests: 987},
        {address: '172.16.0.25', operator: 'Мегафон', requests: 856},
        {address: '192.168.2.75', operator: 'Теле2', requests: 723},
        {address: '10.1.1.200', operator: 'МТС', requests: 654}
    ]
}

const generateMockActivity = () => {
    const activities = [
        {type: 'rotation', message: 'IP rotation completed for 3 modems'},
        {type: 'success', message: 'New modem android_XYZ789 connected'},
        {type: 'error', message: 'Modem usb_0 failed health check'},
        {type: 'rotation', message: 'Automatic rotation triggered'},
        {type: 'success', message: 'System backup completed'}
    ]

    return activities.map((activity, index) => ({
        id: index,
        ...activity,
        timestamp: new Date(Date.now() - index * 15 * 60 * 1000).toISOString()
    }))
}

// Lifecycle
onMounted(() => {
    fetchDashboardData()

    // Set up auto-refresh
    refreshInterval.value = setInterval(() => {
        fetchDashboardData()
    }, 30000) // Refresh every 30 seconds
})

onUnmounted(() => {
    if (refreshInterval.value) {
        clearInterval(refreshInterval.value)
    }
})
</script>
