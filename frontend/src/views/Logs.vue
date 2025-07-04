<template>
    <div class="space-y-6">
        <!-- Page header -->
        <div class="flex-between">
            <div>
                <h1 class="text-2xl font-bold text-gray-900">Logs</h1>
                <p class="text-gray-500">View and analyze system logs</p>
            </div>
            <div class="flex space-x-3">
                <button
                    @click="refreshLogs"
                    :disabled="isLoading"
                    class="btn btn-md btn-secondary"
                >
                    <ArrowPathIcon class="h-4 w-4 mr-1" :class="{ 'animate-spin': isLoading }"/>
                    Refresh
                </button>
                <button
                    @click="exportLogs"
                    class="btn btn-md btn-primary"
                >
                    <DocumentArrowDownIcon class="h-4 w-4 mr-1"/>
                    Export
                </button>
            </div>
        </div>

        <!-- Filters -->
        <div class="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
                <!-- Search -->
                <div class="lg:col-span-2">
                    <div class="relative">
                        <MagnifyingGlassIcon
                            class="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-gray-400"/>
                        <input
                            v-model="searchQuery"
                            type="text"
                            placeholder="Search logs..."
                            class="pl-10 pr-4 py-2 w-full border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                        />
                    </div>
                </div>

                <!-- Modem filter -->
                <div>
                    <select
                        v-model="selectedModem"
                        class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                    >
                        <option value="">All Modems</option>
                        <option v-for="modem in modems" :key="modem.id" :value="modem.id">
                            {{ modem.name }}
                        </option>
                    </select>
                </div>

                <!-- Status filter -->
                <div>
                    <select
                        v-model="selectedStatus"
                        class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                    >
                        <option value="">All Status</option>
                        <option value="200">Success (2xx)</option>
                        <option value="400">Client Error (4xx)</option>
                        <option value="500">Server Error (5xx)</option>
                    </select>
                </div>

                <!-- Time range -->
                <div>
                    <select
                        v-model="timeRange"
                        class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                    >
                        <option value="1h">Last hour</option>
                        <option value="24h">Last 24 hours</option>
                        <option value="7d">Last 7 days</option>
                        <option value="30d">Last 30 days</option>
                    </select>
                </div>
            </div>
        </div>

        <!-- Log level toggle -->
        <div class="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
            <div class="flex items-center justify-between">
                <h3 class="text-sm font-medium text-gray-900">Log Levels</h3>
                <div class="flex space-x-2">
                    <button
                        v-for="level in logLevels"
                        :key="level.name"
                        @click="toggleLogLevel(level.name)"
                        :class="[
              enabledLevels.includes(level.name) ? level.activeClass : level.inactiveClass,
              'px-3 py-1 rounded-md text-sm font-medium transition-colors'
            ]"
                    >
                        {{ level.name }}
                    </button>
                </div>
            </div>
        </div>

        <!-- Logs table -->
        <div class="bg-white rounded-lg shadow-sm border border-gray-200">
            <div class="p-6">
                <!-- Loading state -->
                <div v-if="isLoading" class="space-y-4">
                    <div v-for="i in 10" :key="i" class="loading-pulse h-16 rounded-lg"></div>
                </div>

                <!-- Empty state -->
                <div v-else-if="filteredLogs.length === 0" class="text-center py-12">
                    <DocumentTextIcon class="mx-auto h-12 w-12 text-gray-400"/>
                    <h3 class="mt-2 text-sm font-medium text-gray-900">No logs found</h3>
                    <p class="mt-1 text-sm text-gray-500">
                        Try adjusting your filters or check back later
                    </p>
                </div>

                <!-- Logs list -->
                <div v-else class="space-y-2">
                    <div
                        v-for="log in filteredLogs"
                        :key="log.id"
                        :class="[
              'p-4 rounded-lg border cursor-pointer transition-colors',
              getLogLevelClass(log.level),
              'hover:bg-gray-50'
            ]"
                        @click="selectedLog = log"
                    >
                        <div class="flex items-start justify-between">
                            <div class="flex-1 min-w-0">
                                <div class="flex items-center space-x-3">
                  <span :class="getLogLevelBadgeClass(log.level)" class="px-2 py-1 rounded-full text-xs font-medium">
                    {{ log.level }}
                  </span>
                                    <span class="text-sm font-medium text-gray-900">
                    {{ log.method }} {{ log.status_code }}
                  </span>
                                    <span class="text-sm text-gray-500">
                    {{ formatTime(log.created_at) }}
                  </span>
                                </div>
                                <div class="mt-1 flex items-center space-x-4">
                  <span class="text-sm text-gray-600">
                    {{ log.client_ip }}
                  </span>
                                    <span class="text-sm text-gray-600">
                    {{ log.modem_id || 'N/A' }}
                  </span>
                                    <span class="text-sm text-gray-600">
                    {{ log.response_time_ms }}ms
                  </span>
                                </div>
                                <div class="mt-1 text-sm text-gray-700 truncate">
                                    {{ log.target_url }}
                                </div>
                                <div v-if="log.error_message" class="mt-1 text-sm text-red-600">
                                    {{ log.error_message }}
                                </div>
                            </div>
                            <div class="flex-shrink-0 ml-4">
                                <ChevronRightIcon class="h-5 w-5 text-gray-400"/>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Pagination -->
                <div v-if="filteredLogs.length > 0" class="mt-6 flex items-center justify-between">
                    <div class="text-sm text-gray-700">
                        Showing {{ Math.min(pagination.offset + 1, totalLogs) }} to
                        {{ Math.min(pagination.offset + pagination.limit, totalLogs) }} of {{ totalLogs }} results
                    </div>
                    <div class="flex space-x-2">
                        <button
                            @click="previousPage"
                            :disabled="pagination.offset === 0"
                            class="btn btn-sm btn-secondary"
                        >
                            Previous
                        </button>
                        <button
                            @click="nextPage"
                            :disabled="pagination.offset + pagination.limit >= totalLogs"
                            class="btn btn-sm btn-secondary"
                        >
                            Next
                        </button>
                    </div>
                </div>
            </div>
        </div>

        <!-- Log detail modal -->
        <div v-if="selectedLog" class="fixed inset-0 bg-gray-500 bg-opacity-75 flex items-center justify-center z-50">
            <div class="bg-white rounded-lg max-w-4xl w-full mx-4 max-h-[80vh] overflow-y-auto">
                <div class="p-6">
                    <div class="flex items-center justify-between mb-6">
                        <h3 class="text-lg font-medium text-gray-900">Log Details</h3>
                        <button
                            @click="selectedLog = null"
                            class="text-gray-400 hover:text-gray-600"
                        >
                            <XMarkIcon class="h-6 w-6"/>
                        </button>
                    </div>

                    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <!-- Request details -->
                        <div>
                            <h4 class="text-sm font-medium text-gray-900 mb-3">Request Details</h4>
                            <div class="space-y-3">
                                <div class="flex justify-between">
                                    <span class="text-sm text-gray-500">Method</span>
                                    <span class="text-sm font-medium">{{ selectedLog.method }}</span>
                                </div>
                                <div class="flex justify-between">
                                    <span class="text-sm text-gray-500">Status Code</span>
                                    <span :class="getStatusCodeClass(selectedLog.status_code)"
                                          class="text-sm font-medium">
                    {{ selectedLog.status_code }}
                  </span>
                                </div>
                                <div class="flex justify-between">
                                    <span class="text-sm text-gray-500">Response Time</span>
                                    <span class="text-sm font-medium">{{ selectedLog.response_time_ms }}ms</span>
                                </div>
                                <div class="flex justify-between">
                                    <span class="text-sm text-gray-500">Client IP</span>
                                    <span class="text-sm font-mono">{{ selectedLog.client_ip }}</span>
                                </div>
                                <div class="flex justify-between">
                                    <span class="text-sm text-gray-500">External IP</span>
                                    <span class="text-sm font-mono">{{ selectedLog.external_ip || 'N/A' }}</span>
                                </div>
                                <div class="flex justify-between">
                                    <span class="text-sm text-gray-500">Modem ID</span>
                                    <span class="text-sm font-mono">{{ selectedLog.modem_id || 'N/A' }}</span>
                                </div>
                                <div class="flex justify-between">
                                    <span class="text-sm text-gray-500">Timestamp</span>
                                    <span class="text-sm">{{ formatFullTime(selectedLog.created_at) }}</span>
                                </div>
                            </div>
                        </div>

                        <!-- Request data -->
                        <div>
                            <h4 class="text-sm font-medium text-gray-900 mb-3">Request Data</h4>
                            <div class="space-y-3">
                                <div>
                                    <span class="text-sm text-gray-500 block mb-1">Target URL</span>
                                    <span class="text-sm font-mono bg-gray-50 p-2 rounded block break-all">
                    {{ selectedLog.target_url }}
                  </span>
                                </div>
                                <div>
                                    <span class="text-sm text-gray-500 block mb-1">User Agent</span>
                                    <span class="text-sm bg-gray-50 p-2 rounded block break-all">
                    {{ selectedLog.user_agent || 'N/A' }}
                  </span>
                                </div>
                                <div class="flex justify-between">
                                    <span class="text-sm text-gray-500">Request Size</span>
                                    <span class="text-sm">{{ formatBytes(selectedLog.request_size) }}</span>
                                </div>
                                <div class="flex justify-between">
                                    <span class="text-sm text-gray-500">Response Size</span>
                                    <span class="text-sm">{{ formatBytes(selectedLog.response_size) }}</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Error message -->
                    <div v-if="selectedLog.error_message" class="mt-6">
                        <h4 class="text-sm font-medium text-gray-900 mb-3">Error Details</h4>
                        <div class="bg-red-50 border border-red-200 rounded-lg p-4">
                            <p class="text-sm text-red-800">{{ selectedLog.error_message }}</p>
                        </div>
                    </div>

                    <!-- Actions -->
                    <div class="mt-6 flex justify-end space-x-3">
                        <button
                            @click="selectedLog = null"
                            class="btn btn-md btn-secondary"
                        >
                            Close
                        </button>
                        <button
                            @click="copyLogDetails"
                            class="btn btn-md btn-primary"
                        >
                            Copy Details
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup>
import {ref, computed, onMounted, onUnmounted, watch} from 'vue'
import {useToast} from 'vue-toastification'
import {format} from 'date-fns'
import api from '@/utils/api'

// Icons
import {
    ArrowPathIcon,
    DocumentArrowDownIcon,
    MagnifyingGlassIcon,
    DocumentTextIcon,
    ChevronRightIcon,
    XMarkIcon
} from '@heroicons/vue/24/outline'

const toast = useToast()

// State
const isLoading = ref(false)
const logs = ref([])
const modems = ref([])
const selectedLog = ref(null)
const searchQuery = ref('')
const selectedModem = ref('')
const selectedStatus = ref('')
const timeRange = ref('24h')
const enabledLevels = ref(['INFO', 'WARN', 'ERROR'])
const pagination = ref({
    offset: 0,
    limit: 50
})
const totalLogs = ref(0)
const refreshInterval = ref(null)

const logLevels = [
    {
        name: 'INFO',
        activeClass: 'bg-blue-100 text-blue-800',
        inactiveClass: 'bg-gray-100 text-gray-600'
    },
    {
        name: 'WARN',
        activeClass: 'bg-yellow-100 text-yellow-800',
        inactiveClass: 'bg-gray-100 text-gray-600'
    },
    {
        name: 'ERROR',
        activeClass: 'bg-red-100 text-red-800',
        inactiveClass: 'bg-gray-100 text-gray-600'
    }
]

// Computed
const filteredLogs = computed(() => {
    let filtered = logs.value

    if (searchQuery.value) {
        const query = searchQuery.value.toLowerCase()
        filtered = filtered.filter(log =>
            log.target_url.toLowerCase().includes(query) ||
            log.client_ip.includes(query) ||
            log.modem_id?.toLowerCase().includes(query) ||
            log.error_message?.toLowerCase().includes(query)
        )
    }

    if (selectedModem.value) {
        filtered = filtered.filter(log => log.modem_id === selectedModem.value)
    }

    if (selectedStatus.value) {
        const statusCode = parseInt(selectedStatus.value)
        filtered = filtered.filter(log => {
            const code = log.status_code
            if (statusCode === 200) return code >= 200 && code < 300
            if (statusCode === 400) return code >= 400 && code < 500
            if (statusCode === 500) return code >= 500
            return false
        })
    }

    return filtered
})

// Methods
const fetchLogs = async () => {
    try {
        isLoading.value = true
        const response = await api.get('/stats/logs', {
            params: {
                limit: pagination.value.limit,
                offset: pagination.value.offset,
                modem_id: selectedModem.value || undefined,
                status_code: selectedStatus.value || undefined
            }
        })

        logs.value = response.data.map(log => ({
            ...log,
            level: getLogLevel(log.status_code, log.error_message)
        }))

        totalLogs.value = response.data.length
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
        modems.value = response.data.map(modem => ({
            id: modem.modem_id,
            name: modem.modem_id
        }))
    } catch (error) {
        console.error('Failed to fetch modems:', error)
    }
}

const refreshLogs = () => {
    fetchLogs()
}

const exportLogs = async () => {
    try {
        const response = await api.get('/stats/export', {
            params: {
                format: 'csv',
                days: timeRange.value === '1h' ? 1 : timeRange.value === '24h' ? 1 : 7
            }
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
        toast.error('Failed to export logs')
    }
}

const toggleLogLevel = (level) => {
    const index = enabledLevels.value.indexOf(level)
    if (index > -1) {
        enabledLevels.value.splice(index, 1)
    } else {
        enabledLevels.value.push(level)
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

// Utility functions
const getLogLevel = (statusCode, errorMessage) => {
    if (errorMessage) return 'ERROR'
    if (statusCode >= 400) return 'WARN'
    return 'INFO'
}

const getLogLevelClass = (level) => {
    switch (level) {
        case 'ERROR':
            return 'border-red-200 bg-red-50'
        case 'WARN':
            return 'border-yellow-200 bg-yellow-50'
        default:
            return 'border-gray-200 bg-white'
    }
}

const getLogLevelBadgeClass = (level) => {
    switch (level) {
        case 'ERROR':
            return 'bg-red-100 text-red-800'
        case 'WARN':
            return 'bg-yellow-100 text-yellow-800'
        default:
            return 'bg-blue-100 text-blue-800'
    }
}

const getStatusCodeClass = (code) => {
    if (code >= 200 && code < 300) return 'text-green-600'
    if (code >= 400 && code < 500) return 'text-yellow-600'
    if (code >= 500) return 'text-red-600'
    return 'text-gray-600'
}

const formatTime = (timestamp) => {
    return format(new Date(timestamp), 'HH:mm:ss')
}

const formatFullTime = (timestamp) => {
    return format(new Date(timestamp), 'yyyy-MM-dd HH:mm:ss')
}

const formatBytes = (bytes) => {
    if (!bytes) return '0 B'
    if (bytes >= 1024 * 1024) {
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
    }
