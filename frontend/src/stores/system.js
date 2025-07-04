import {defineStore} from 'pinia'
import {ref, computed} from 'vue'
import api from '@/utils/api'

export const useSystemStore = defineStore('system', () => {
    // State
    const status = ref({
        proxy_server: 'unknown',
        total_modems: 0,
        online_modems: 0,
        offline_modems: 0
    })
    const isLoading = ref(false)
    const lastUpdate = ref(null)

    // Getters
    const systemStatus = computed(() => {
        const {online_modems, total_modems} = status.value

        if (total_modems === 0) {
            return {
                text: 'No modems configured',
                color: 'bg-gray-400'
            }
        }

        if (online_modems === 0) {
            return {
                text: 'All modems offline',
                color: 'bg-red-500'
            }
        }

        if (online_modems < total_modems) {
            return {
                text: 'Some modems offline',
                color: 'bg-yellow-500'
            }
        }

        return {
            text: 'All systems operational',
            color: 'bg-green-500'
        }
    })

    const totalModems = computed(() => status.value.total_modems || 0)
    const onlineModems = computed(() => status.value.online_modems || 0)
    const offlineModems = computed(() => status.value.offline_modems || 0)
    const uptimePercentage = computed(() => {
        const total = totalModems.value
        const online = onlineModems.value
        return total > 0 ? Math.round((online / total) * 100) : 0
    })

    // Actions
    const fetchSystemStatus = async () => {
        try {
            isLoading.value = true
            const response = await api.get('/proxy/health')

            status.value = {
                proxy_server: 'running',
                total_modems: response.data.total_modems || 0,
                online_modems: response.data.online_modems || 0,
                offline_modems: (response.data.total_modems || 0) - (response.data.online_modems || 0)
            }

            lastUpdate.value = new Date()
        } catch (error) {
            console.error('Failed to fetch system status:', error)
            status.value = {
                proxy_server: 'error',
                total_modems: 0,
                online_modems: 0,
                offline_modems: 0
            }
        } finally {
            isLoading.value = false
        }
    }

    const getHealthCheck = async () => {
        try {
            const response = await api.get('/admin/system/health')
            return response.data
        } catch (error) {
            console.error('Health check failed:', error)
            throw error
        }
    }

    const restartSystem = async () => {
        try {
            const response = await api.post('/admin/system/restart')
            return response.data
        } catch (error) {
            console.error('System restart failed:', error)
            throw error
        }
    }

    return {
        // State
        status,
        isLoading,
        lastUpdate,

        // Getters
        systemStatus,
        totalModems,
        onlineModems,
        offlineModems,
        uptimePercentage,

        // Actions
        fetchSystemStatus,
        getHealthCheck,
        restartSystem
    }
})
