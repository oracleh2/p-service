<!-- frontend/src/views/Logs.vue -->
<template>
    <div class="space-y-6">
        <!-- Header -->
        <div class="sm:flex sm:items-center sm:justify-between">
            <div>
                <h1 class="text-2xl font-bold text-gray-900">Request Logs</h1>
                <p class="mt-2 text-sm text-gray-700">
                    Monitor all proxy requests and troubleshoot issues
                </p>
            </div>
            <div class="mt-4 sm:mt-0 sm:ml-16 sm:flex-none space-x-3 flex">
                <button
                    @click="exportLogs"
                    :disabled="isExporting"
                    class="btn btn-secondary btn-sm"
                >
                    <DocumentArrowDownIcon class="h-4 w-4 mr-2"/>
                    {{ isExporting ? 'Exporting...' : 'Export CSV' }}
                </button>
                <button
                    @click="clearLogs"
                    class="btn btn-error btn-sm"
                >
                    <TrashIcon class="h-4 w-4 mr-2"/>
                    Clear Old Logs
                </button>
            </div>
        </div>

        <!-- Filters -->
        <div class="bg-white shadow rounded-lg p-6">
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <!-- Time Range -->
                <div>
                    <label class="block text-sm font-medium text-gray-700">Time Range</label>
                    <select
                        v-model="filters.timeRange"
                        @change="fetchLogs"
                        class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                    >
                        <option value="1h">Last Hour</option>
                        <option value="24h">Last 24 Hours</option>
                        <option value="7d">Last 7 Days</option>
                        <option value="30d">Last 30 Days</option>
                    </select>
                </div>

                <!-- Modem Filter -->
                <div>
                    <label class="block text-sm font-medium text-gray-700">Modem</label>
                    <select
                        v-model="filters.modemId"
                        @change="fetchLogs"
                        class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                    >
                        <option value="">All Modems</option>
                        <option
                            v-for="modem in availableModems"
                            :key="modem.id"
                            :value="modem.id"
                        >
                            {{ modem.name }}
                        </option>
                    </select>
                </div>

                <!-- Status Filter -->
                <div>
                    <label class="block text-sm font-medium text-gray-700">Status</label>
                    <select
                        v-model="filters.statusCode"
                        @change="fetchLogs"
                        class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                    >
                        <option value="">All Status</option>
                        <option value="200">Success (200)</option>
                        <option value="400">Bad Request (400)</option>
                        <option value="404">Not Found (404)</option>
                        <option value="500">Server Error (500)</option>
                    </select>
                </div>

                <!-- Search -->
                <div>
                    <label class="block text-sm font-medium text-gray-700">Search URL</label>
                    <input
                        v-model="filters.search"
                        @input="debounceSearch"
                        type="text"
                        placeholder="Search in URLs..."
                        class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                    >
                </div>
            </div>

            <!-- Log Level Filters -->
            <div class="mt-4">
                <label class="block text-sm font-medium text-gray-700 mb-2">Log Levels</label>
                <div class="flex space-x-4">
                    <label
                        v-for="level in logLevels"
                        :key="level.value"
                        class="inline-flex items-center"
                    >
                        <input
                            type="checkbox"
                            :value="level.value"
                            v-model="filters.enabledLevels"
                            @change="fetchLogs"
                            class="rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500"
                        >
                        <span class="ml-2 text-sm" :class="level.class">
              {{ level.label }}
            </span>
                    </label>
                </div>
            </div>
        </div>

        <!-- Stats Summary -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-6">
            <div class="bg-white overflow-hidden shadow rounded-lg">
                <div class="p-5">
                    <div class="flex items-center">
                        <div class="flex-shrink-0">
                            <DocumentTextIcon class="h-6 w-6 text-gray-400"/>
                        </div>
                        <div class="ml-5 w-0 flex-1">
                            <dl>
                                <dt class="text-sm font-medium text-gray-500 truncate">Total Requests</dt>
                                <dd class="text-lg font-medium text-gray-900">{{
                                        stats.totalRequests.toLocaleString()
                                    }}
                                </dd>
                            </dl>
                        </div>
                    </div>
                </div>
            </div>

            <div class="bg-white overflow-hidden shadow rounded-lg">
                <div class="p-5">
                    <div class="flex items-center">
                        <div class="flex-shrink-0">
                            <CheckCircleIcon class="h-6 w-6 text-green-400"/>
                        </div>
                        <div class="ml-5 w-0 flex-1">
                            <dl>
                                <dt class="text-sm font-medium text-gray-500 truncate">Success Rate</dt>
                                <dd class="text-lg font-medium text-gray-900">{{ stats.successRate }}%</dd>
                            </dl>
                        </div>
                    </div>
                </div>
            </div>

            <div class="bg-white overflow-hidden shadow rounded-lg">
                <div class="p-5">
                    <div class="flex items-center">
                        <div class="flex-shrink-0">
                            <ClockIcon class="h-6 w-6 text-blue-400"/>
                        </div>
                        <div class="ml-5 w-0 flex-1">
                            <dl>
                                <dt class="text-sm font-medium text-gray-500 truncate">Avg Response Time</dt>
                                <dd class="text-lg font-medium text-gray-900">{{ stats.avgResponseTime }}ms</dd>
                            </dl>
                        </div>
                    </div>
                </div>
            </div>

            <div class="bg-white overflow-hidden shadow rounded-lg">
                <div class="p-5">
                    <div class="flex items-center">
                        <div class="flex-shrink-0">
                            <ExclamationTriangleIcon class="h-6 w-6 text-red-400"/>
                        </div>
                        <div class="ml-5 w-0 flex-1">
                            <dl>
                                <dt class="text-sm font-medium text-gray-500 truncate">Error Rate</dt>
                                <dd class="text-lg font-medium text-gray-900">{{ stats.errorRate }}%</dd>
                            </dl>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Logs Table -->
        <div class="bg-white shadow overflow-hidden sm:rounded-md">
            <div class="px-4 py-5 sm:p-6">
                <div class="flex items-center justify-between mb-4">
                    <h3 class="text-lg leading-6 font-medium text-gray-900">
                        Request Logs
                    </h3>
                    <div class="flex items-center space-x-2">
            <span class="text-sm text-gray-500">
              Auto-refresh:
            </span>
                        <button
                            @click="toggleAutoRefresh"
                            :class="[
                autoRefresh ? 'bg-primary-600 text-white' : 'bg-gray-200 text-gray-700',
                'px-3 py-1 rounded-md text-sm font-medium transition-colors'
              ]"
                        >
                            {{ autoRefresh ? 'ON' : 'OFF' }}
                        </button>
                    </div>
                </div>

                <!-- Loading State -->
                <div v-if="isLoading" class="flex justify-center py-8">
                    <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
                </div>

                <!-- Empty State -->
                <div v-else-if="!logs.length" class="text-center py-8">
                    <DocumentTextIcon class="mx-auto h-12 w-12 text-gray-400"/>
                    <h3 class="mt-2 text-sm font-medium text-gray-900">No logs found</h3>
                    <p class="mt-1 text-sm text-gray-500">
                        No request logs match your current filters.
                    </p>
                </div>

                <!-- Logs Table -->
                <div v-else class="overflow-x-auto">
                    <table class="min-w-full divide-y divide-gray-200">
                        <thead class="bg-gray-50">
                        <tr>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Timestamp
                            </th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Method
                            </th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Status
                            </th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                URL
                            </th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Client IP
                            </th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                External IP
                            </th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Response Time
                            </th>
                            <th class="relative px-6 py-3">
                                <span class="sr-only">Actions</span>
                            </th>
                        </tr>
                        </thead>
                        <tbody class="bg-white divide-y divide-gray-200">
                        <tr
                            v-for="log in logs"
                            :key="log.id"
                            class="hover:bg-gray-50 cursor-pointer"
                            @click="selectLog(log)"
                        >
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                {{ formatDate(log.created_at) }}
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap">
                  <span :class="getMethodClass(log.method)" class="px-2 py-1 text-xs font-medium rounded-full">
                    {{ log.method }}
                  </span>
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap">
                  <span :class="getStatusClass(log.status_code)" class="px-2 py-1 text-xs font-medium rounded-full">
                    {{ log.status_code }}
                  </span>
                            </td>
                            <td class="px-6 py-4 text-sm text-gray-900 max-w-xs truncate">
                                {{ log.target_url }}
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                {{ log.client_ip }}
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                {{ log.external_ip }}
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                {{ log.response_time_ms }}ms
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                <button
                                    @click.stop="selectLog(log)"
                                    class="text-primary-600 hover:text-primary-900"
                                >
                                    View Details
                                </button>
                            </td>
                        </tr>
                        </tbody>
                    </table>
                </div>

                <!-- Pagination -->
                <div class="bg-white px-4 py-3 flex items-center justify-between border-t border-gray-200 sm:px-6">
                    <div class="flex-1 flex justify-between sm:hidden">
                        <button
                            @click="previousPage"
                            :disabled="pagination.offset === 0"
                            class="relative inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50"
                        >
                            Previous
                        </button>
                        <button
                            @click="nextPage"
                            :disabled="pagination.offset + pagination.limit >= totalLogs"
                            class="ml-3 relative inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50"
                        >
                            Next
                        </button>
                    </div>
                    <div class="hidden sm:flex-1 sm:flex sm:items-center sm:justify-between">
                        <div>
                            <p class="text-sm text-gray-700">
                                Showing
                                <span class="font-medium">{{ pagination.offset + 1 }}</span>
                                to
                                <span class="font-medium">{{
                                        Math.min(pagination.offset + pagination.limit, totalLogs)
                                    }}</span>
                                of
                                <span class="font-medium">{{ totalLogs }}</span>
                                results
                            </p>
                        </div>
                        <div>
                            <nav class="relative z-0 inline-flex rounded-md shadow-sm -space-x-px">
                                <button
                                    @click="previousPage"
                                    :disabled="pagination.offset === 0"
                                    class="relative inline-flex items-center px-2 py-2 rounded-l-md border border-gray-300 bg-white text-sm font-medium text-gray-500 hover:bg-gray-50 disabled:opacity-50"
                                >
                                    <ChevronLeftIcon class="h-5 w-5"/>
                                </button>
                                <button
                                    @click="nextPage"
                                    :disabled="pagination.offset + pagination.limit >= totalLogs"
                                    class="relative inline-flex items-center px-2 py-2 rounded-r-md border border-gray-300 bg-white text-sm font-medium text-gray-500 hover:bg-gray-50 disabled:opacity-50"
                                >
                                    <ChevronRightIcon class="h-5 w-5"/>
                                </button>
                            </nav>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Log Detail Modal -->
        <div v-if="selectedLog" class="fixed inset-0 z-50 overflow-y-auto">
            <div class="flex items-end justify-center min-h-screen pt-4 px-4 pb-20 text-center sm:block sm:p-0">
                <div class="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity"
                     @click="selectedLog = null"></div>

                <div
                    class="inline-block align-bottom bg-white rounded-lg text-left overflow-hidden shadow-xl transform transition-all sm:my-8 sm:align-middle sm:max-w-4xl sm:w-full">
                    <div class="bg-white px-4 pt-5 pb-4 sm:p-6 sm:pb-4">
                        <div class="sm:flex sm:items-start">
                            <div class="mt-3 text-center sm:mt-0 sm:text-left w-full">
                                <h3 class="text-lg leading-6 font-medium text-gray-900 mb-4">
                                    Request Details
                                </h3>

                                <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                                    <div>
                                        <h4 class="text-sm font-medium text-gray-900 mb-2">Basic Information</h4>
                                        <dl class="space-y-2">
                                            <div>
                                                <dt class="text-sm font-medium text-gray-500">Timestamp</dt>
                                                <dd class="text-sm text-gray-900">{{
                                                        formatDate(selectedLog.created_at)
                                                    }}
                                                </dd>
                                            </div>
                                            <div>
                                                <dt class="text-sm font-medium text-gray-500">Method</dt>
                                                <dd class="text-sm text-gray-900">{{ selectedLog.method }}</dd>
                                            </div>
                                            <div>
                                                <dt class="text-sm font-medium text-gray-500">Status Code</dt>
                                                <dd class="text-sm text-gray-900">{{ selectedLog.status_code }}</dd>
                                            </div>
                                            <div>
                                                <dt class="text-sm font-medium text-gray-500">Response Time</dt>
                                                <dd class="text-sm text-gray-900">{{
                                                        selectedLog.response_time_ms
                                                    }}ms
                                                </dd>
                                            </div>
                                        </dl>
                                    </div>

                                    <div>
                                        <h4 class="text-sm font-medium text-gray-900 mb-2">Network Information</h4>
                                        <dl class="space-y-2">
                                            <div>
                                                <dt class="text-sm font-medium text-gray-500">Client IP</dt>
                                                <dd class="text-sm text-gray-900">{{ selectedLog.client_ip }}</dd>
                                            </div>
                                            <div>
                                                <dt class="text-sm font-medium text-gray-500">External IP</dt>
                                                <dd class="text-sm text-gray-900">{{ selectedLog.external_ip }}</dd>
                                            </div>
                                            <div>
                                                <dt class="text-sm font-medium text-gray-500">Modem ID</dt>
                                                <dd class="text-sm text-gray-900">{{ selectedLog.modem_id }}</dd>
                                            </div>
                                        </dl>
                                    </div>
                                </div>

                                <div class="mt-6">
                                    <h4 class="text-sm font-medium text-gray-900 mb-2">Target URL</h4>
                                    <p class="text-sm text-gray-600 bg-gray-50 p-3 rounded break-all">
                                        {{ selectedLog.target_url }}
                                    </p>
                                </div>

                                <div v-if="selectedLog.user_agent" class="mt-6">
                                    <h4 class="text-sm font-medium text-gray-900 mb-2">User Agent</h4>
                                    <p class="text-sm text-gray-600 bg-gray-50 p-3 rounded break-all">
                                        {{ selectedLog.user_agent }}
                                    </p>
                                </div>

                                <div v-if="selectedLog.error_message" class="mt-6">
                                    <h4 class="text-sm font-medium text-gray-900 mb-2">Error Message</h4>
                                    <p class="text-sm text-red-600 bg-red-50 p-3 rounded">
                                        {{ selectedLog.error_message }}
                                    </p>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="bg-gray-50 px-4 py-3 sm:px-6 sm:flex sm:flex-row-reverse">
                        <button
                            @click="copyLogDetails"
                            class="w-full inline-flex justify-center rounded-md border border-transparent shadow-sm px-4 py-2 bg-primary-600 text-base font-medium text-white hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 sm:ml-3 sm:w-auto sm:text-sm"
                        >
                            Copy Details
                        </button>
                        <button
                            @click="selectedLog = null"
                            class="mt-3 w-full inline-flex justify-center rounded-md border border-gray-300 shadow-sm px-4 py-2 bg-white text-base font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 sm:mt-0 sm:ml-3 sm:w-auto sm:text-sm"
                        >
                            Close
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup>
import {ref, onMounted, onUnmounted, computed} from 'vue'
import {format} from 'date-fns'
import {useToast} from 'vue-toastification'
import api from '@/utils/api'
import {debounce} from 'lodash-es'

// Icons
import {
    DocumentTextIcon,
    DocumentArrowDownIcon,
    TrashIcon,
    CheckCircleIcon,
    ClockIcon,
    ExclamationTriangleIcon,
    ChevronLeftIcon,
    ChevronRightIcon
} from '@heroicons/vue/24/outline'

const toast = useToast()

// State
const isLoading = ref(false)
const isExporting = ref(false)
const logs = ref([])
const selectedLog = ref(null)
const totalLogs = ref(0)
const autoRefresh = ref(true)
const availableModems = ref([])

// Filters
const filters = ref({
    timeRange: '24h',
    modemId: '',
    statusCode: '',
    search: '',
    enabledLevels: ['INFO', 'WARN', 'ERROR']
})

// Pagination
const pagination = ref({
    limit: 50,
    offset: 0
})

// Stats
const stats = ref({
    totalRequests: 0,
    successRate: 0,
    avgResponseTime: 0,
    errorRate: 0
})

// Constants
const logLevels = [
    {value: 'INFO', label: 'Info', class: 'text-blue-600'},
    {value: 'WARN', label: 'Warning', class: 'text-yellow-600'},
    {value: 'ERROR', label: 'Error', class: 'text-red-600'}
]

// Auto-refresh interval
let refreshInterval = null

// Methods
const fetchLogs = async () => {
    try {
        isLoading.value = true

        const params = {
            limit: pagination.value.limit,
            offset: pagination.value.offset
        }

        if (filters.value.modemId) params.modem_id = filters.value.modemId
        if (filters.value.statusCode) params.status_code = filters.value.statusCode
        if (filters.value.search) params.search = filters.value.search

        const response = await api.get('/stats/logs', {params})

        logs.value = response.data.logs || response.data || []
        totalLogs.value = response.data.total || logs.value.length

        // Calculate stats from current logs
        calculateStats()

    } catch (error) {
        console.error('Failed to fetch logs:', error)
        toast.error('Failed to load logs')
    } finally {
        isLoading.value = false
    }
}

const fetchModems = async () => {
    try {
        const response = await api.get('/admin/modems')
        availableModems.value = response.data.map(modem => ({
            id: modem.modem_id,
            name: modem.modem_id
        }))
    } catch (error) {
        console.error('Failed to fetch modems:', error)
    }
}

const calculateStats = () => {
    const total = logs.value.length
    if (total === 0) {
        stats.value = {
            totalRequests: 0,
            successRate: 0,
            avgResponseTime: 0,
            errorRate: 0
        }
        return
    }

    const successful = logs.value.filter(log => log.status_code >= 200 && log.status_code < 400).length
    const errors = logs.value.filter(log => log.status_code >= 400).length
    const totalResponseTime = logs.value.reduce((sum, log) => sum + (log.response_time_ms || 0), 0)

    stats.value = {
        totalRequests: total,
        successRate: Math.round((successful / total) * 100),
        avgResponseTime: Math.round(totalResponseTime / total),
        errorRate: Math.round((errors / total) * 100)
    }
}

const exportLogs = async () => {
    try {
        isExporting.value = true

        const params = {
            format: 'csv',
            days: filters.value.timeRange === '1h' ? 1 :
                filters.value.timeRange === '24h' ? 1 :
                    filters.value.timeRange === '7d' ? 7 : 30
        }

        if (filters.value.modemId) params.modem_id = filters.value.modemId

        const response = await api.get('/stats/export', {
            params,
            responseType: 'blob'
        })

        // Create download link
        const blob = new Blob([response.data], {type: 'text/csv'})
        const url = window.URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.href = url
        link.download = `logs-${format(new Date(), 'yyyy-MM-dd')}.csv`
        link.click()
        window.URL.revokeObjectURL(url)

        toast.success('Logs exported successfully')
    } catch (error) {
        console.error('Failed to export logs:', error)
        toast.error('Failed to export logs')
    } finally {
        isExporting.value = false
    }
}

const clearLogs = async () => {
    if (!confirm('Are you sure you want to clear old logs? This action cannot be undone.')) {
        return
    }

    try {
        await api.delete('/admin/logs/cleanup?days_to_keep=30')
        toast.success('Old logs cleared successfully')
        await fetchLogs()
    } catch (error) {
        console.error('Failed to clear logs:', error)
        toast.error('Failed to clear logs')
    }
}

const selectLog = (log) => {
    selectedLog.value = log
}

const copyLogDetails = () => {
    if (selectedLog.value) {
        const details = {
            id: selectedLog.value.id,
            timestamp: selectedLog.value.created_at,
            method: selectedLog.value.method,
            status_code: selectedLog.value.status_code,
            target_url: selectedLog.value.target_url,
            client_ip: selectedLog.value.client_ip,
            external_ip: selectedLog.value.external_ip,
            modem_id: selectedLog.value.modem_id,
            response_time_ms: selectedLog.value.response_time_ms,
            user_agent: selectedLog.value.user_agent,
            error_message: selectedLog.value.error_message
        }

        navigator.clipboard.writeText(JSON.stringify(details, null, 2))
        toast.success('Log details copied to clipboard')
    }
}

const toggleAutoRefresh = () => {
    autoRefresh.value = !autoRefresh.value

    if (autoRefresh.value) {
        startAutoRefresh()
    } else {
        stopAutoRefresh()
    }
}

const startAutoRefresh = () => {
    if (refreshInterval) clearInterval(refreshInterval)
    refreshInterval = setInterval(fetchLogs, 30000) // 30 seconds
}

const stopAutoRefresh = () => {
    if (refreshInterval) {
        clearInterval(refreshInterval)
        refreshInterval = null
    }
}

const previousPage = () => {
    if (pagination.value.offset > 0) {
        pagination.value.offset = Math.max(0, pagination.value.offset - pagination.value.limit)
        fetchLogs()
    }
}

const nextPage = () => {
    if (pagination.value.offset + pagination.value.limit < totalLogs.value) {
        pagination.value.offset += pagination.value.limit
        fetchLogs()
    }
}

// Debounced search
const debounceSearch = debounce(() => {
    pagination.value.offset = 0
    fetchLogs()
}, 500)

// Utility functions
const formatDate = (dateString) => {
    return format(new Date(dateString), 'MMM dd, yyyy HH:mm:ss')
}

const getMethodClass = (method) => {
    const classes = {
        'GET': 'bg-blue-100 text-blue-800',
        'POST': 'bg-green-100 text-green-800',
        'PUT': 'bg-yellow-100 text-yellow-800',
        'DELETE': 'bg-red-100 text-red-800',
        'PATCH': 'bg-purple-100 text-purple-800'
    }
    return classes[method] || 'bg-gray-100 text-gray-800'
}

const getStatusClass = (statusCode) => {
    if (statusCode >= 200 && statusCode < 300) {
        return 'bg-green-100 text-green-800'
    } else if (statusCode >= 300 && statusCode < 400) {
        return 'bg-yellow-100 text-yellow-800'
    } else if (statusCode >= 400 && statusCode < 500) {
        return 'bg-orange-100 text-orange-800'
    } else if (statusCode >= 500) {
        return 'bg-red-100 text-red-800'
    }
    return 'bg-gray-100 text-gray-800'
}

// Lifecycle
onMounted(async () => {
    await fetchModems()
    await fetchLogs()

    if (autoRefresh.value) {
        startAutoRefresh()
    }
})

onUnmounted(() => {
    stopAutoRefresh()
})
</script>
