<template>
    <div class="space-y-6">
        <!-- Page header -->
        <div class="flex-between">
            <div>
                <h1 class="text-2xl font-bold text-gray-900">Modems</h1>
                <p class="text-gray-500">Manage your mobile proxy modems</p>
            </div>
            <div class="flex space-x-3">
                <button
                    @click="refreshModems"
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
                    Rotate All
                </button>
            </div>
        </div>

        <!-- Filters and search -->
        <div class="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
            <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between space-y-4 lg:space-y-0">
                <div class="flex flex-col sm:flex-row sm:items-center space-y-2 sm:space-y-0 sm:space-x-4">
                    <!-- Search -->
                    <div class="relative">
                        <MagnifyingGlassIcon
                            class="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-gray-400"/>
                        <input
                            v-model="searchQuery"
                            type="text"
                            placeholder="Search modems..."
                            class="pl-10 pr-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                        />
                    </div>

                    <!-- Status filter -->
                    <select
                        v-model="statusFilter"
                        class="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                    >
                        <option value="">All Status</option>
                        <option value="online">Online</option>
                        <option value="offline">Offline</option>
                        <option value="busy">Busy</option>
                    </select>

                    <!-- Type filter -->
                    <select
                        v-model="typeFilter"
                        class="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                    >
                        <option value="">All Types</option>
                        <option value="android">Android</option>
                        <option value="usb_modem">USB Modem</option>
                        <option value="raspberry_pi">Raspberry Pi</option>
                    </select>
                </div>

                <!-- View toggle -->
                <div class="flex space-x-2">
                    <button
                        @click="viewMode = 'grid'"
                        :class="viewMode === 'grid' ? 'btn-primary' : 'btn-secondary'"
                        class="btn btn-sm"
                    >
                        <Squares2X2Icon class="h-4 w-4"/>
                    </button>
                    <button
                        @click="viewMode = 'list'"
                        :class="viewMode === 'list' ? 'btn-primary' : 'btn-secondary'"
                        class="btn btn-sm"
                    >
                        <ListBulletIcon class="h-4 w-4"/>
                    </button>
                </div>
            </div>
        </div>

        <!-- Stats overview -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div class="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
                <div class="flex items-center">
                    <div class="p-2 bg-blue-100 rounded-lg">
                        <ServerIcon class="h-6 w-6 text-blue-600"/>
                    </div>
                    <div class="ml-4">
                        <p class="text-sm font-medium text-gray-500">Total</p>
                        <p class="text-2xl font-bold text-gray-900">{{ totalModems }}</p>
                    </div>
                </div>
            </div>

            <div class="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
                <div class="flex items-center">
                    <div class="p-2 bg-green-100 rounded-lg">
                        <CheckCircleIcon class="h-6 w-6 text-green-600"/>
                    </div>
                    <div class="ml-4">
                        <p class="text-sm font-medium text-gray-500">Online</p>
                        <p class="text-2xl font-bold text-gray-900">{{ onlineModems }}</p>
                    </div>
                </div>
            </div>

            <div class="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
                <div class="flex items-center">
                    <div class="p-2 bg-red-100 rounded-lg">
                        <XCircleIcon class="h-6 w-6 text-red-600"/>
                    </div>
                    <div class="ml-4">
                        <p class="text-sm font-medium text-gray-500">Offline</p>
                        <p class="text-2xl font-bold text-gray-900">{{ offlineModems }}</p>
                    </div>
                </div>
            </div>

            <div class="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
                <div class="flex items-center">
                    <div class="p-2 bg-purple-100 rounded-lg">
                        <GlobeAltIcon class="h-6 w-6 text-purple-600"/>
                    </div>
                    <div class="ml-4">
                        <p class="text-sm font-medium text-gray-500">Unique IPs</p>
                        <p class="text-2xl font-bold text-gray-900">{{ uniqueIPs }}</p>
                    </div>
                </div>
            </div>
        </div>

        <!-- Modems list/grid -->
        <div class="bg-white rounded-lg shadow-sm border border-gray-200">
            <div class="p-6">
                <!-- Loading state -->
                <div v-if="isLoading" class="space-y-4">
                    <div v-for="i in 6" :key="i" class="loading-pulse h-20 rounded-lg"></div>
                </div>

                <!-- Empty state -->
                <div v-else-if="filteredModems.length === 0" class="text-center py-12">
                    <ServerIcon class="mx-auto h-12 w-12 text-gray-400"/>
                    <h3 class="mt-2 text-sm font-medium text-gray-900">No modems found</h3>
                    <p class="mt-1 text-sm text-gray-500">
                        {{
                            searchQuery || statusFilter || typeFilter ? 'Try adjusting your filters' : 'No modems have been configured yet'
                        }}
                    </p>
                </div>

                <!-- Grid view -->
                <div v-else-if="viewMode === 'grid'"
                     class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 3xl:grid-cols-6 gap-6">
                    <div
                        v-for="modem in filteredModems"
                        :key="modem.modem_id"
                        class="bg-white border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow cursor-pointer"
                        @click="viewModemDetails(modem.modem_id)"
                    >
                        <div class="flex items-center justify-between mb-3">
                            <div class="flex items-center space-x-2">
                                <div :class="getStatusColor(modem.status)" class="w-3 h-3 rounded-full"></div>
                                <span class="text-sm font-medium text-gray-900">{{ modem.modem_id }}</span>
                            </div>
                            <div class="flex space-x-1">
                                <button
                                    @click.stop="rotateModem(modem.modem_id)"
                                    :disabled="rotatingModems.includes(modem.modem_id)"
                                    class="p-1 text-gray-400 hover:text-gray-600"
                                    :title="'Rotate IP'"
                                >
                                    <ArrowPathIcon class="h-4 w-4"
                                                   :class="{ 'animate-spin': rotatingModems.includes(modem.modem_id) }"/>
                                </button>
                                <button
                                    @click.stop="toggleAutoRotation(modem.modem_id, !modem.auto_rotation)"
                                    class="p-1 text-gray-400 hover:text-gray-600"
                                    :title="modem.auto_rotation ? 'Disable auto rotation' : 'Enable auto rotation'"
                                >
                                    <ClockIcon class="h-4 w-4" :class="{ 'text-green-600': modem.auto_rotation }"/>
                                </button>
                            </div>
                        </div>

                        <div class="space-y-2">
                            <div class="flex items-center justify-between">
                                <span class="text-xs text-gray-500">Type</span>
                                <span class="text-xs font-medium">{{ formatModemType(modem.modem_type) }}</span>
                            </div>
                            <div class="flex items-center justify-between">
                                <span class="text-xs text-gray-500">External IP</span>
                                <span class="text-xs font-mono">{{ modem.external_ip || 'N/A' }}</span>
                            </div>
                            <div class="flex items-center justify-between">
                                <span class="text-xs text-gray-500">Requests</span>
                                <span class="text-xs font-medium">{{ formatNumber(modem.total_requests) }}</span>
                            </div>
                            <div class="flex items-center justify-between">
                                <span class="text-xs text-gray-500">Success Rate</span>
                                <span class="text-xs font-medium" :class="getSuccessRateColor(modem.success_rate)">
                  {{ modem.success_rate.toFixed(1) }}%
                </span>
                            </div>
                            <div class="flex items-center justify-between">
                                <span class="text-xs text-gray-500">Last Rotation</span>
                                <span class="text-xs">{{ formatTime(modem.last_rotation) }}</span>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- List view -->
                <div v-else class="overflow-x-auto">
                    <table class="min-w-full divide-y divide-gray-200">
                        <thead class="bg-gray-50">
                        <tr>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Modem
                            </th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Status
                            </th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Type
                            </th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                External IP
                            </th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Requests
                            </th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Success Rate
                            </th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Last Rotation
                            </th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Actions
                            </th>
                        </tr>
                        </thead>
                        <tbody class="bg-white divide-y divide-gray-200">
                        <tr
                            v-for="modem in filteredModems"
                            :key="modem.modem_id"
                            class="hover:bg-gray-50 cursor-pointer"
                            @click="viewModemDetails(modem.modem_id)"
                        >
                            <td class="px-6 py-4 whitespace-nowrap">
                                <div class="flex items-center">
                                    <div :class="getStatusColor(modem.status)" class="w-3 h-3 rounded-full mr-3"></div>
                                    <div>
                                        <div class="text-sm font-medium text-gray-900">{{ modem.modem_id }}</div>
                                        <div class="text-sm text-gray-500">{{ modem.interface }}</div>
                                    </div>
                                </div>
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap">
                  <span :class="getStatusBadgeClass(modem.status)"
                        class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium">
                    {{ modem.status }}
                  </span>
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                {{ formatModemType(modem.modem_type) }}
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-900">
                                {{ modem.external_ip || 'N/A' }}
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                {{ formatNumber(modem.total_requests) }}
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm font-medium"
                                :class="getSuccessRateColor(modem.success_rate)">
                                {{ modem.success_rate.toFixed(1) }}%
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                {{ formatTime(modem.last_rotation) }}
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-sm font-medium">
                                <div class="flex space-x-2">
                                    <button
                                        @click.stop="rotateModem(modem.modem_id)"
                                        :disabled="rotatingModems.includes(modem.modem_id)"
                                        class="text-primary-600 hover:text-primary-900"
                                        :title="'Rotate IP'"
                                    >
                                        <ArrowPathIcon class="h-4 w-4"
                                                       :class="{ 'animate-spin': rotatingModems.includes(modem.modem_id) }"/>
                                    </button>
                                    <button
                                        @click.stop="toggleAutoRotation(modem.modem_id, !modem.auto_rotation)"
                                        class="text-gray-600 hover:text-gray-900"
                                        :title="modem.auto_rotation ? 'Disable auto rotation' : 'Enable auto rotation'"
                                    >
                                        <ClockIcon class="h-4 w-4" :class="{ 'text-green-600': modem.auto_rotation }"/>
                                    </button>
                                </div>
                            </td>
                        </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- Rotation interval modal -->
        <div v-if="showRotationModal"
             class="fixed inset-0 bg-gray-500 bg-opacity-75 flex items-center justify-center z-50">
            <div class="bg-white rounded-lg p-6 max-w-md w-full mx-4">
                <h3 class="text-lg font-medium text-gray-900 mb-4">Update Rotation Interval</h3>
                <div class="space-y-4">
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-2">
                            Rotation Interval (seconds)
                        </label>
                        <input
                            v-model="rotationInterval"
                            type="number"
                            min="60"
                            max="3600"
                            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                            placeholder="600"
                        />
                        <p class="text-sm text-gray-500 mt-1">
                            Minimum 60 seconds, maximum 3600 seconds (1 hour)
                        </p>
                    </div>
                    <div class="flex justify-end space-x-3">
                        <button
                            @click="showRotationModal = false"
                            class="btn btn-md btn-secondary"
                        >
                            Cancel
                        </button>
                        <button
                            @click="updateRotationInterval"
                            class="btn btn-md btn-primary"
                        >
                            Update
                        </button>
                    </div>
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

// Icons
import {
    ServerIcon,
    CheckCircleIcon,
    XCircleIcon,
    GlobeAltIcon,
    ArrowPathIcon,
    MagnifyingGlassIcon,
    Squares2X2Icon,
    ListBulletIcon,
    ClockIcon
} from '@heroicons/vue/24/outline'

const router = useRouter()
const toast = useToast()

// State
const isLoading = ref(false)
const isRotating = ref(false)
const rotatingModems = ref([])
const viewMode = ref('grid')
const searchQuery = ref('')
const statusFilter = ref('')
const typeFilter = ref('')
const showRotationModal = ref(false)
const rotationInterval = ref(600)
const selectedModemId = ref('')

// Data
const modems = ref([])
const refreshInterval = ref(null)

// Computed
const filteredModems = computed(() => {
    let filtered = modems.value

    if (searchQuery.value) {
        filtered = filtered.filter(modem =>
            modem.modem_id.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
            modem.interface.toLowerCase().includes(searchQuery.value.toLowerCase())
        )
    }

    if (statusFilter.value) {
        filtered = filtered.filter(modem => modem.status === statusFilter.value)
    }

    if (typeFilter.value) {
        filtered = filtered.filter(modem => modem.modem_type === typeFilter.value)
    }

    return filtered
})

const totalModems = computed(() => modems.value.length)
const onlineModems = computed(() => modems.value.filter(m => m.status === 'online').length)
const offlineModems = computed(() => modems.value.filter(m => m.status === 'offline').length)
const uniqueIPs = computed(() => {
    const ips = new Set(modems.value.map(m => m.external_ip).filter(ip => ip))
    return ips.size
})

// Methods
const fetchModems = async () => {
    try {
        isLoading.value = true
        const response = await api.get('/admin/devices')
        modems.value = response.data
    } catch (error) {
        console.error('Failed to fetch modems:', error)
        toast.error('Failed to fetch modems')
    } finally {
        isLoading.value = false
    }
}

const refreshModems = () => {
    fetchModems()
}

const rotateAllModems = async () => {
    try {
        isRotating.value = true
        const response = await api.post('/admin/devices/rotate-all')
        toast.success(response.data.message)

        // Refresh modems after rotation
        setTimeout(() => {
            fetchModems()
        }, 2000)
    } catch (error) {
        toast.error('Failed to rotate all modems')
    } finally {
        isRotating.value = false
    }
}

const rotateModem = async (modemId) => {
    try {
        rotatingModems.value.push(modemId)
        await api.post(`/admin/devices/${modemId}/rotate`)
        toast.success('IP rotation initiated')

        // Refresh modems after rotation
        setTimeout(() => {
            fetchModems()
        }, 2000)
    } catch (error) {
        toast.error('Failed to rotate modem IP')
    } finally {
        rotatingModems.value = rotatingModems.value.filter(id => id !== modemId)
    }
}

const toggleAutoRotation = async (modemId, enabled) => {
    try {
        await api.put(`/admin/devices/${modemId}/auto-rotation`, null, {
            params: {enabled}
        })
        toast.success(`Auto rotation ${enabled ? 'enabled' : 'disabled'}`)
        fetchModems()
    } catch (error) {
        toast.error('Failed to toggle auto rotation')
    }
}

const updateRotationInterval = async () => {
    try {
        await api.put(`/admin/devices/${selectedModemId.value}/rotation-interval`, null, {
            params: {interval: rotationInterval.value}
        })
        toast.success('Rotation interval updated')
        showRotationModal.value = false
        fetchModems()
    } catch (error) {
        toast.error('Failed to update rotation interval')
    }
}

const viewModemDetails = (modemId) => {
    router.push(`/modems/${modemId}`)
}

// Utility functions
const formatNumber = (num) => {
    // Проверяем на undefined/null и возвращаем 0 по умолчанию
    const number = num || 0;

    if (number >= 1000000) {
        return (number / 1000000).toFixed(1) + 'M'
    } else if (number >= 1000) {
        return (number / 1000).toFixed(1) + 'K'
    }
    return number.toString()
}

const formatTime = (timestamp) => {
    if (!timestamp) return 'Never'
    return format(new Date(timestamp), 'MMM d, HH:mm')
}

const formatModemType = (type) => {
    switch (type) {
        case 'android':
            return 'Android'
        case 'usb_modem':
            return 'USB Modem'
        case 'raspberry_pi':
            return 'Raspberry Pi'
        default:
            return type
    }
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

const getStatusBadgeClass = (status) => {
    switch (status) {
        case 'online':
            return 'bg-green-100 text-green-800'
        case 'offline':
            return 'bg-red-100 text-red-800'
        case 'busy':
            return 'bg-yellow-100 text-yellow-800'
        default:
            return 'bg-gray-100 text-gray-800'
    }
}

const getSuccessRateColor = (rate) => {
    if (rate >= 90) return 'text-green-600'
    if (rate >= 75) return 'text-yellow-600'
    return 'text-red-600'
}

// Lifecycle
onMounted(() => {
    fetchModems()

    // Set up auto-refresh
    refreshInterval.value = setInterval(() => {
        fetchModems()
    }, 30000) // Refresh every 30 seconds
})

onUnmounted(() => {
    if (refreshInterval.value) {
        clearInterval(refreshInterval.value)
    }
})
</script>
