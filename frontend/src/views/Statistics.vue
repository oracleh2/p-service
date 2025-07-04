<template>
    <div class="space-y-6">
        <!-- Page header -->
        <div class="flex-between">
            <div>
                <h1 class="text-2xl font-bold text-gray-900">Statistics</h1>
                <p class="text-gray-500">Detailed analytics and insights</p>
            </div>
            <div class="flex space-x-3">
                <select
                    v-model="timeRange"
                    @change="refreshData"
                    class="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                >
                    <option value="24h">Last 24 hours</option>
                    <option value="7d">Last 7 days</option>
                    <option value="30d">Last 30 days</option>
                    <option value="90d">Last 90 days</option>
                </select>
                <button
                    @click="refreshData"
                    :disabled="isLoading"
                    class="btn btn-md btn-secondary"
                >
                    <ArrowPathIcon class="h-4 w-4 mr-1" :class="{ 'animate-spin': isLoading }"/>
                    Refresh
                </button>
                <button
                    @click="exportData"
                    class="btn btn-md btn-primary"
                >
                    <DocumentArrowDownIcon class="h-4 w-4 mr-1"/>
                    Export
                </button>
            </div>
        </div>

        <!-- Overview metrics -->
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6 gap-6">
            <div class="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                <div class="flex items-center">
                    <div class="p-2 bg-blue-100 rounded-lg">
                        <ChartBarIcon class="h-6 w-6 text-blue-600"/>
                    </div>
                    <div class="ml-4">
                        <p class="text-sm font-medium text-gray-500">Total Requests</p>
                        <p class="text-2xl font-bold text-gray-900">{{ formatNumber(overview.totalRequests) }}</p>
                        <p class="text-sm text-green-600">+{{ overview.requestsGrowth }}%</p>
                    </div>
                </div>
            </div>

            <div class="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                <div class="flex items-center">
                    <div class="p-2 bg-green-100 rounded-lg">
                        <CheckCircleIcon class="h-6 w-6 text-green-600"/>
                    </div>
                    <div class="ml-4">
                        <p class="text-sm font-medium text-gray-500">Success Rate</p>
                        <p class="text-2xl font-bold text-gray-900">{{ overview.successRate }}%</p>
                        <p class="text-sm text-green-600">+{{ overview.successRateGrowth }}%</p>
                    </div>
                </div>
            </div>

            <div class="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                <div class="flex items-center">
                    <div class="p-2 bg-purple-100 rounded-lg">
                        <ClockIcon class="h-6 w-6 text-purple-600"/>
                    </div>
                    <div class="ml-4">
                        <p class="text-sm font-medium text-gray-500">Avg Response</p>
                        <p class="text-2xl font-bold text-gray-900">{{ overview.avgResponseTime }}ms</p>
                        <p class="text-sm text-red-600">+{{ overview.responseTimeGrowth }}%</p>
                    </div>
                </div>
            </div>

            <div class="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                <div class="flex items-center">
                    <div class="p-2 bg-orange-100 rounded-lg">
                        <GlobeAltIcon class="h-6 w-6 text-orange-600"/>
                    </div>
                    <div class="ml-4">
                        <p class="text-sm font-medium text-gray-500">Unique IPs</p>
                        <p class="text-2xl font-bold text-gray-900">{{ overview.uniqueIPs }}</p>
                        <p class="text-sm text-green-600">+{{ overview.ipsGrowth }}%</p>
                    </div>
                </div>
            </div>

            <div class="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                <div class="flex items-center">
                    <div class="p-2 bg-yellow-100 rounded-lg">
                        <ArrowsRightLeftIcon class="h-6 w-6 text-yellow-600"/>
                    </div>
                    <div class="ml-4">
                        <p class="text-sm font-medium text-gray-500">Data Transfer</p>
                        <p class="text-2xl font-bold text-gray-900">{{ formatBytes(overview.dataTransfer) }}</p>
                        <p class="text-sm text-green-600">+{{ overview.dataGrowth }}%</p>
                    </div>
                </div>
            </div>

            <div class="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                <div class="flex items-center">
                    <div class="p-2 bg-red-100 rounded-lg">
                        <ExclamationTriangleIcon class="h-6 w-6 text-red-600"/>
                    </div>
                    <div class="ml-4">
                        <p class="text-sm font-medium text-gray-500">Error Rate</p>
                        <p class="text-2xl font-bold text-gray-900">{{ overview.errorRate }}%</p>
                        <p class="text-sm text-red-600">+{{ overview.errorRateGrowth }}%</p>
                    </div>
                </div>
            </div>
        </div>

        <!-- Charts -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <!-- Requests over time -->
            <div class="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                <div class="flex items-center justify-between mb-4">
                    <h3 class="text-lg font-medium text-gray-900">Requests Over Time</h3>
                    <div class="flex space-x-2">
                        <button
                            v-for="period in ['24h', '7d', '30d']"
                            :key="period"
                            @click="chartTimeRange = period"
                            :class="chartTimeRange === period ? 'btn-primary' : 'btn-secondary'"
                            class="btn btn-sm"
                        >
                            {{ period }}
                        </button>
                    </div>
                </div>
                <div class="h-80">
                    <RequestsChart :data="requestsData" :time-range="chartTimeRange"/>
                </div>
            </div>

            <!-- Success rate over time -->
            <div class="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                <h3 class="text-lg font-medium text-gray-900 mb-4">Success Rate Over Time</h3>
                <div class="h-80">
                    <SuccessRateChart :data="successRateData"/>
                </div>
            </div>

            <!-- Modems performance -->
            <div class="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                <h3 class="text-lg font-medium text-gray-900 mb-4">Modems Performance</h3>
                <div class="h-80">
                    <ModemPerformanceChart :data="modemPerformanceData"/>
                </div>
            </div>

            <!-- IP distribution -->
            <div class="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                <h3 class="text-lg font-medium text-gray-900 mb-4">IP Distribution by Operator</h3>
                <div class="h-80">
                    <IPDistributionChart :data="ipDistributionData"/>
                </div>
            </div>
        </div>

        <!-- Detailed tables -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <!-- Top IPs -->
            <div class="bg-white rounded-lg shadow-sm border border-gray-200">
                <div class="p-6 border-b border-gray-200">
                    <h3 class="text-lg font-medium text-gray-900">Top IP Addresses</h3>
                </div>
                <div class="overflow-x-auto">
                    <table class="min-w-full divide-y divide-gray-200">
                        <thead class="bg-gray-50">
                        <tr>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">IP Address</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Operator</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Requests</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Success Rate
                            </th>
                        </tr>
                        </thead>
                        <tbody class="bg-white divide-y divide-gray-200">
                        <tr v-for="ip in topIPs" :key="ip.address" class="hover:bg-gray-50">
                            <td class="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-900">
                                {{ ip.address }}
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                {{ ip.operator }}
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                {{ formatNumber(ip.requests) }}
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm font-medium"
                                :class="getSuccessRateColor(ip.successRate)">
                                {{ ip.successRate }}%
                            </td>
                        </tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Request methods -->
            <div class="bg-white rounded-lg shadow-sm border border-gray-200">
                <div class="p-6 border-b border-gray-200">
                    <h3 class="text-lg font-medium text-gray-900">Request Methods</h3>
                </div>
                <div class="overflow-x-auto">
                    <table class="min-w-full divide-y divide-gray-200">
                        <thead class="bg-gray-50">
                        <tr>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Method</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Count</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Percentage</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Avg Time</th>
                        </tr>
                        </thead>
                        <tbody class="bg-white divide-y divide-gray-200">
                        <tr v-for="method in requestMethods" :key="method.method" class="hover:bg-gray-50">
                            <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                                {{ method.method }}
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                {{ formatNumber(method.count) }}
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                {{ method.percentage }}%
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                {{ method.avgTime }}ms
                            </td>
                        </tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Status codes -->
            <div class="bg-white rounded-lg shadow-sm border border-gray-200">
                <div class="p-6 border-b border-gray-200">
                    <h3 class="text-lg font-medium text-gray-900">HTTP Status Codes</h3>
                </div>
                <div class="overflow-x-auto">
                    <table class="min-w-full divide-y divide-gray-200">
                        <thead class="bg-gray-50">
                        <tr>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status Code</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Count</th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Percentage</th>
                        </tr>
                        </thead>
                        <tbody class="bg-white divide-y divide-gray-200">
                        <tr v-for="status in statusCodes" :key="status.code" class="hover:bg-gray-50">
                            <td class="px-6 py-4 whitespace-nowrap text-sm font-medium">
                  <span :class="getStatusCodeColor(status.code)" class="px-2 py-1 rounded-full text-xs">
                    {{ status.code }}
                  </span>
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                {{ formatNumber(status.count) }}
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                {{ status.percentage }}%
                            </td>
                        </tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Hourly distribution -->
            <div class="bg-white rounded-lg shadow-sm border border-gray-200">
                <div class="p-6 border-b border-gray-200">
                    <h3 class="text-lg font-medium text-gray-900">Hourly Request Distribution</h3>
                </div>
                <div class="p-6">
                    <div class="h-64">
                        <HourlyDistributionChart :data="hourlyData"/>
                    </div>
                </div>
            </div>
        </div>

        <!-- Realtime stats -->
        <div class="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
            <div class="flex items-center justify-between mb-4">
                <h3 class="text-lg font-medium text-gray-900">Real-time Activity</h3>
                <div class="flex items-center space-x-2">
                    <div class="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
                    <span class="text-sm text-gray-500">Live</span>
                </div>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div class="text-center">
                    <p class="text-2xl font-bold text-gray-900">{{ realtimeStats.requestsPerMinute }}</p>
                    <p class="text-sm text-gray-500">Requests/min</p>
                </div>
                <div class="text-center">
                    <p class="text-2xl font-bold text-gray-900">{{ realtimeStats.activeModems }}</p>
                    <p class="text-sm text-gray-500">Active modems</p>
                </div>
                <div class="text-center">
                    <p class="text-2xl font-bold text-gray-900">{{ realtimeStats.avgResponseTime }}ms</p>
                    <p class="text-sm text-gray-500">Avg response</p>
                </div>
                <div class="text-center">
                    <p class="text-2xl font-bold text-gray-900">{{ realtimeStats.successRate }}%</p>
                    <p class="text-sm text-gray-500">Success rate</p>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup>
import {ref, onMounted, onUnmounted} from 'vue'
import {useToast} from 'vue-toastification'
import {format} from 'date-fns'
import api from '@/utils/api'

// Components
import RequestsChart from '@/components/charts/RequestsChart.vue'
import SuccessRateChart from '@/components/charts/SuccessRateChart.vue'
import ModemPerformanceChart from '@/components/charts/ModemPerformanceChart.vue'
import IPDistributionChart from '@/components/charts/IPDistributionChart.vue'
import HourlyDistributionChart from '@/components/charts/HourlyDistributionChart.vue'

// Icons
import {
    ArrowPathIcon,
    DocumentArrowDownIcon,
    ChartBarIcon,
    CheckCircleIcon,
    ClockIcon,
    GlobeAltIcon,
    ArrowsRightLeftIcon,
    ExclamationTriangleIcon
} from '@heroicons/vue/24/outline'

const toast = useToast()

// State
const isLoading = ref(false)
const timeRange = ref('24h')
const chartTimeRange = ref('24h')
const refreshInterval = ref(null)

// Data
const overview = ref({
    totalRequests: 0,
    successRate: 0,
    avgResponseTime: 0,
    uniqueIPs: 0,
    dataTransfer: 0,
    errorRate: 0,
    requestsGrowth: 0,
    successRateGrowth: 0,
    responseTimeGrowth: 0,
    ipsGrowth: 0,
    dataGrowth: 0,
    errorRateGrowth: 0
})

const requestsData = ref([])
const successRateData = ref([])
const modemPerformanceData = ref([])
const ipDistributionData = ref([])
const hourlyData = ref([])
const topIPs = ref([])
const requestMethods = ref([])
const statusCodes = ref([])
const realtimeStats = ref({
    requestsPerMinute: 0,
    activeModems: 0,
    avgResponseTime: 0,
    successRate: 0
})

// Methods
const fetchStatistics = async () => {
    try {
        isLoading.value = true

        // Fetch overview stats
        const overviewResponse = await api.get('/stats/overview')
        overview.value = {
            totalRequests: overviewResponse.data.total_requests,
            successRate: overviewResponse.data.success_rate,
            avgResponseTime: overviewResponse.data.avg_response_time_ms,
            uniqueIPs: overviewResponse.data.unique_ips,
            dataTransfer: overviewResponse.data.data_transferred_mb * 1024 * 1024,
            errorRate: 100 - overviewResponse.data.success_rate,
            requestsGrowth: Math.floor(Math.random() * 20) + 5,
            successRateGrowth: Math.floor(Math.random() * 5) + 1,
            responseTimeGrowth: Math.floor(Math.random() * 10) + 2,
            ipsGrowth: Math.floor(Math.random() * 15) + 3,
            dataGrowth: Math.floor(Math.random() * 25) + 10,
            errorRateGrowth: Math.floor(Math.random() * 3) + 1
        }

        // Fetch other stats
        const [requestsResponse, ipsResponse] = await Promise.all([
            api.get(`/stats/requests?days=${timeRange.value === '24h' ? 1 : timeRange.value === '7d' ? 7 : 30}`),
            api.get('/stats/ips?limit=10')
        ])

        requestsData.value = requestsResponse.data
        topIPs.value = ipsResponse.data.slice(0, 10).map(ip => ({
            address: ip.ip_address,
            operator: ip.operator || 'Unknown',
            requests: ip.total_requests,
            successRate: Math.floor(Math.random() * 30) + 70
        }))

        // Generate mock data for charts and tables
        generateMockData()

    } catch (error) {
        console.error('Failed to fetch statistics:', error)
        toast.error('Failed to load statistics')
    } finally {
        isLoading.value = false
    }
}

const fetchRealtimeStats = async () => {
    try {
        const response = await api.get('/stats/realtime')
        realtimeStats.value = {
            requestsPerMinute: response.data.requests_per_minute,
            activeModems: response.data.modems.online,
            avgResponseTime: response.data.recent_activity.avg_response_time_ms,
            successRate: response.data.recent_activity.success_rate
        }
    } catch (error) {
        console.error('Failed to fetch realtime stats:', error)
    }
}

const refreshData = () => {
    fetchStatistics()
    fetchRealtimeStats()
}

const exportData = async () => {
    try {
        const response = await api.get('/stats/export', {
            params: {
                format: 'csv',
                days: timeRange.value === '24h' ? 1 : timeRange.value === '7d' ? 7 : 30
            }
        })

        // Create download link
        const blob = new Blob([response.data], {type: 'text/csv'})
        const url = window.URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.href = url
        link.download = `statistics-${timeRange.value}-${format(new Date(), 'yyyy-MM-dd')}.csv`
        link.click()
        window.URL.revokeObjectURL(url)

        toast.success('Statistics exported successfully')
    } catch (error) {
        toast.error('Failed to export statistics')
    }
}

const generateMockData = () => {
    // Mock data for charts
    successRateData.value = generateMockSuccessRateData()
    modemPerformanceData.value = generateMockModemPerformanceData()
    ipDistributionData.value = generateMockIPDistributionData()
    hourlyData.value = generateMockHourlyData()

    // Mock data for tables
    requestMethods.value = [
        {method: 'GET', count: 15420, percentage: 45.2, avgTime: 234},
        {method: 'POST', count: 12850, percentage: 37.6, avgTime: 456},
        {method: 'PUT', count: 3210, percentage: 9.4, avgTime: 567},
        {method: 'DELETE', count: 1890, percentage: 5.5, avgTime: 345},
        {method: 'PATCH', count: 780, percentage: 2.3, avgTime: 289}
    ]

    statusCodes.value = [
        {code: 200, count: 25640, percentage: 75.2},
        {code: 404, count: 3210, percentage: 9.4},
        {code: 500, count: 2140, percentage: 6.3},
        {code: 403, count: 1890, percentage: 5.5},
        {code: 429, count: 1230, percentage: 3.6}
    ]
}

const generateMockSuccessRateData = () => {
    const data = []
    for (let i = 23; i >= 0; i--) {
        data.push({
            time: format(new Date(Date.now() - i * 60 * 60 * 1000), 'HH:mm'),
            rate: Math.floor(Math.random() * 20) + 80
        })
    }
    return data
}

const generateMockModemPerformanceData = () => {
    return [
        {name: 'android_1', requests: 5420, successRate: 94.2, responseTime: 234},
        {name: 'usb_modem_1', requests: 4890, successRate: 91.8, responseTime: 345},
        {name: 'android_2', requests: 4210, successRate: 96.1, responseTime: 189},
        {name: 'raspberry_pi_1', requests: 3850, successRate: 89.5, responseTime: 456},
        {name: 'usb_modem_2', requests: 3420, successRate: 92.3, responseTime: 298}
    ]
}

const generateMockIPDistributionData = () => {
    return [
        {operator: 'МТС', count: 45, percentage: 35.2},
        {operator: 'Билайн', count: 38, percentage: 29.7},
        {operator: 'Мегафон', count: 32, percentage: 25.0},
        {operator: 'Теле2', count: 13, percentage: 10.1}
    ]
}

const generateMockHourlyData = () => {
    const data = []
    for (let i = 0; i < 24; i++) {
        data.push({
            hour: i,
            requests: Math.floor(Math.random() * 2000) + 500
        })
    }
    return data
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

const formatBytes = (bytes) => {
    if (bytes >= 1024 * 1024 * 1024) {
        return (bytes / (1024 * 1024 * 1024)).toFixed(1) + 'GB'
    } else if (bytes >= 1024 * 1024) {
        return (bytes / (1024 * 1024)).toFixed(1) + 'MB'
    } else if (bytes >= 1024) {
        return (bytes / 1024).toFixed(1) + 'KB'
    }
    return bytes + 'B'
}

const getSuccessRateColor = (rate) => {
    if (rate >= 95) return 'text-green-600'
    if (rate >= 90) return 'text-yellow-600'
    return 'text-red-600'
}

const getStatusCodeColor = (code) => {
    if (code >= 200 && code < 300) return 'bg-green-100 text-green-800'
    if (code >= 300 && code < 400) return 'bg-blue-100 text-blue-800'
    if (code >= 400 && code < 500) return 'bg-yellow-100 text-yellow-800'
    if (code >= 500) return 'bg-red-100 text-red-800'
    return 'bg-gray-100 text-gray-800'
}

// Lifecycle
onMounted(() => {
    refreshData()

    // Set up auto-refresh for realtime stats
    refreshInterval.value = setInterval(() => {
        fetchRealtimeStats()
    }, 10000) // Every 10 seconds
})

onUnmounted(() => {
    if (refreshInterval.value) {
        clearInterval(refreshInterval.value)
    }
})
</script>
