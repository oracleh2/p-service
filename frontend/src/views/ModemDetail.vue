<template>
    <div class="space-y-6">
        <!-- Breadcrumb -->
        <nav class="flex" aria-label="Breadcrumb">
            <ol class="flex items-center space-x-4">
                <li>
                    <router-link to="/modems" class="text-gray-400 hover:text-gray-500">
                        Modems
                    </router-link>
                </li>
                <li>
                    <ChevronRightIcon class="h-5 w-5 text-gray-400"/>
                </li>
                <li>
                    <span class="text-gray-900 font-medium">{{ modemId }}</span>
                </li>
            </ol>
        </nav>

        <!-- Loading state -->
        <div v-if="isLoading" class="space-y-6">
            <div class="loading-pulse h-32 rounded-lg"></div>
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div class="loading-pulse h-64 rounded-lg"></div>
                <div class="loading-pulse h-64 rounded-lg"></div>
                <div class="loading-pulse h-64 rounded-lg"></div>
            </div>
        </div>

        <!-- Content -->
        <div v-else-if="modem" class="space-y-6">
            <!-- Header -->
            <div class="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                <div class="flex items-center justify-between">
                    <div class="flex items-center space-x-4">
                        <div :class="getStatusColor(modem.status)" class="w-4 h-4 rounded-full"></div>
                        <div>
                            <h1 class="text-2xl font-bold text-gray-900">{{ modem.modem_id }}</h1>
                            <p class="text-gray-500">{{ formatModemType(modem.modem_type) }} • {{ modem.interface }}</p>
                        </div>
                    </div>
                    <div class="flex space-x-3">
                        <button
                            @click="testModem"
                            :disabled="isTesting"
                            class="btn btn-md btn-secondary"
                        >
                            <PlayIcon class="h-4 w-4 mr-1" :class="{ 'animate-pulse': isTesting }"/>
                            Test
                        </button>
                        <button
                            @click="rotateIP"
                            :disabled="isRotating"
                            class="btn btn-md btn-primary"
                        >
                            <ArrowPathIcon class="h-4 w-4 mr-1" :class="{ 'animate-spin': isRotating }"/>
                            Rotate IP
                        </button>
                    </div>
                </div>
            </div>

            <!-- Stats grid -->
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <div class="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                    <div class="flex items-center">
                        <div class="p-2 bg-blue-100 rounded-lg">
                            <ChartBarIcon class="h-6 w-6 text-blue-600"/>
                        </div>
                        <div class="ml-4">
                            <p class="text-sm font-medium text-gray-500">Total Requests</p>
                            <p class="text-2xl font-bold text-gray-900">{{ formatNumber(modem.total_requests) }}</p>
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
                            <p class="text-2xl font-bold text-gray-900"
                               :class="getSuccessRateColor(modem.success_rate)">
                                {{ modem.success_rate.toFixed(1) }}%
                            </p>
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
                            <p class="text-2xl font-bold text-gray-900">{{ modem.avg_response_time_ms }}ms</p>
                        </div>
                    </div>
                </div>

                <div class="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                    <div class="flex items-center">
                        <div class="p-2 bg-orange-100 rounded-lg">
                            <GlobeAltIcon class="h-6 w-6 text-orange-600"/>
                        </div>
                        <div class="ml-4">
                            <p class="text-sm font-medium text-gray-500">Current IP</p>
                            <p class="text-lg font-mono text-gray-900">{{ modem.external_ip || 'N/A' }}</p>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Details and settings -->
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <!-- Modem details -->
                <div class="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                    <h2 class="text-lg font-medium text-gray-900 mb-4">Modem Details</h2>
                    <div class="space-y-3">
                        <div class="flex justify-between">
                            <span class="text-gray-500">Status</span>
                            <span :class="getStatusBadgeClass(modem.status)"
                                  class="px-2 py-1 rounded-full text-xs font-medium">
                {{ modem.status }}
              </span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-500">Type</span>
                            <span class="text-gray-900">{{ formatModemType(modem.modem_type) }}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-500">Interface</span>
                            <span class="font-mono text-gray-900">{{ modem.interface }}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-500">External IP</span>
                            <span class="font-mono text-gray-900">{{ modem.external_ip || 'N/A' }}</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-500">Last Rotation</span>
                            <span class="text-gray-900">{{ formatTime(modem.last_rotation) }}</span>
                        </div>
                    </div>
                </div>

                <!-- Rotation settings -->
                <div class="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                    <h2 class="text-lg font-medium text-gray-900 mb-4">Rotation Settings</h2>
                    <div class="space-y-4">
                        <div class="flex items-center justify-between">
                            <span class="text-gray-700">Auto Rotation</span>
                            <button
                                @click="toggleAutoRotation"
                                :class="modem.auto_rotation ? 'bg-green-600' : 'bg-gray-200'"
                                class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2"
                            >
                <span
                    :class="modem.auto_rotation ? 'translate-x-5' : 'translate-x-0'"
                    class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out"
                />
                            </button>
                        </div>

                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-2">
                                Rotation Interval (seconds)
                            </label>
                            <div class="flex space-x-2">
                                <input
                                    v-model="rotationInterval"
                                    type="number"
                                    min="60"
                                    max="3600"
                                    class="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                                />
                                <button
                                    @click="updateInterval"
                                    class="btn btn-md btn-primary"
                                >
                                    Update
                                </button>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Recent activity -->
                <div class="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                    <h2 class="text-lg font-medium text-gray-900 mb-4">Recent Activity</h2>
                    <div class="space-y-3">
                        <div class="text-sm text-gray-600">
                            Last rotation: {{ formatTime(modem.last_rotation) }}
                        </div>
                        <div class="text-sm text-gray-600">
                            Requests today: {{ formatNumber(modem.requests_24h || 0) }}
                        </div>
                        <div class="text-sm text-gray-600">
                            Success rate: {{ modem.success_rate.toFixed(1) }}%
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Error state -->
        <div v-else class="text-center py-12">
            <ExclamationTriangleIcon class="mx-auto h-12 w-12 text-red-400"/>
            <h3 class="mt-2 text-sm font-medium text-gray-900">Modem not found</h3>
            <p class="mt-1 text-sm text-gray-500">
                The modem you're looking for doesn't exist or has been removed.
            </p>
            <div class="mt-6">
                <router-link to="/modems" class="btn btn-md btn-primary">
                    Back to Modems
                </router-link>
            </div>
        </div>

        <!-- Модальное окно выбора метода ротации -->
        <RotationMethodModal
            :is-visible="showRotationMethodModal"
            :device-info="deviceInfo"
            @close="closeRotationModal"
            @rotation-success="handleRotationSuccess"
        />
    </div>
</template>

<script setup>
import {ref, onMounted, computed} from 'vue'
import {useRoute} from 'vue-router'
import {useToast} from 'vue-toastification'
import {format} from 'date-fns'
import {useDeviceStore} from '../stores/devices'
import RotationMethodModal from '@/components/RotationMethodModal.vue'


// Icons
import {
    ChevronRightIcon,
    PlayIcon,
    ArrowPathIcon,
    ChartBarIcon,
    CheckCircleIcon,
    ClockIcon,
    GlobeAltIcon,
    ExclamationTriangleIcon
} from '@heroicons/vue/24/outline'

const route = useRoute()
const toast = useToast()
const modemsStore = useDeviceStore()

// State
const isLoading = ref(false)
const isRotating = ref(false)
const isTesting = ref(false)
const modem = ref(null)
const rotationInterval = ref(600)
const showRotationMethodModal = ref(false)


// Computed
const modemId = computed(() => route.params.id)

// Methods
const fetchModemDetails = async () => {
    try {
        isLoading.value = true
        const modemData = await modemsStore.getModemById(modemId.value)
        modem.value = modemData
        rotationInterval.value = modemData.rotation_interval || 600
    } catch (error) {
        console.error('Failed to fetch modem details:', error)
        toast.error('Failed to load modem details')
    } finally {
        isLoading.value = false
    }
}

const rotateIP = async () => {
    if (!modem.value) return

    // Подготавливаем данные для модального окна
    const deviceInfo = {
        modem_id: modem.value.modem_id,
        device_id: modem.value.modem_id,
        modem_type: modem.value.modem_type,
        device_type: modem.value.modem_type,
        interface: modem.value.interface,
        status: modem.value.status,
        external_ip: modem.value.external_ip,
        name: modem.value.device_info || modem.value.modem_id
    }

    // Открываем модальное окно вместо прямой ротации
    showRotationMethodModal.value = true
}

const testModem = async () => {
    try {
        isTesting.value = true
        const result = await modemsStore.testModem(modemId.value)

        if (result.success) {
            toast.success('Modem test successful')
        } else {
            toast.error('Modem test failed')
        }
    } catch (error) {
        toast.error('Failed to test modem')
    } finally {
        isTesting.value = false
    }
}

const toggleAutoRotation = async () => {
    try {
        const newState = !modem.value.auto_rotation
        await modemsStore.toggleAutoRotation(modemId.value, newState)
        modem.value.auto_rotation = newState
        toast.success(`Auto rotation ${newState ? 'enabled' : 'disabled'}`)
    } catch (error) {
        toast.error('Failed to toggle auto rotation')
    }
}

const updateInterval = async () => {
    try {
        await modemsStore.updateRotationInterval(modemId.value, rotationInterval.value)
        modem.value.rotation_interval = rotationInterval.value
        toast.success('Rotation interval updated')
    } catch (error) {
        toast.error('Failed to update rotation interval')
    }
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

const closeRotationModal = () => {
    showRotationMethodModal.value = false
}

const handleRotationSuccess = (result) => {
    toast.success(`IP ротация завершена! Новый IP: ${result.new_ip || 'получается...'}`)

    // Обновляем данные устройства
    if (modem.value) {
        modem.value.external_ip = result.new_ip
        modem.value.last_rotation = Date.now()
    }

    closeRotationModal()

    // Перезагружаем детали устройства
    setTimeout(() => {
        fetchModemDetails()
    }, 2000)
}

const deviceInfo = computed(() => {
    if (!modem.value) return {}

    return {
        modem_id: modem.value.modem_id,
        device_id: modem.value.modem_id,
        modem_type: modem.value.modem_type,
        device_type: modem.value.modem_type,
        interface: modem.value.interface,
        status: modem.value.status,
        external_ip: modem.value.external_ip,
        name: modem.value.device_info || modem.value.modem_id
    }
})

// Lifecycle
onMounted(() => {
    fetchModemDetails()
})
</script>
