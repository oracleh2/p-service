// frontend/src/stores/devices.js - ДОПОЛНЕННАЯ ВЕРСИЯ

import {defineStore} from 'pinia'
import {ref, computed} from 'vue'
import api from '@/utils/api'

export const useDeviceStore = defineStore('modems', () => {
    // State
    const modems = ref([])
    const isLoading = ref(false)
    const error = ref('')
    const lastUpdate = ref(null)

    // Getters
    const totalModems = computed(() => modems.value.length)
    const onlineModems = computed(() => modems.value.filter(m => m.status === 'online').length)
    const offlineModems = computed(() => modems.value.filter(m => m.status === 'offline').length)
    const busyModems = computed(() => modems.value.filter(m => m.status === 'busy').length)

    const modemsByType = computed(() => {
        const types = {}
        modems.value.forEach(modem => {
            const type = modem.modem_type || 'unknown'
            types[type] = (types[type] || 0) + 1
        })
        return types
    })

    const averageSuccessRate = computed(() => {
        if (modems.value.length === 0) return 0
        const totalRate = modems.value.reduce((sum, modem) => sum + (modem.success_rate || 0), 0)
        return totalRate / modems.value.length
    })

    const totalRequests = computed(() => {
        return modems.value.reduce((sum, modem) => sum + (modem.total_requests || 0), 0)
    })

    // Actions
    const fetchModems = async () => {
        try {
            isLoading.value = true
            error.value = ''

            const response = await api.get('/admin/devices')
            modems.value = response.data
            lastUpdate.value = new Date()

            return response.data
        } catch (err) {
            error.value = err.response?.data?.detail || 'Failed to fetch modems'
            console.error('Failed to fetch modems:', err)
            throw err
        } finally {
            isLoading.value = false
        }
    }

    // ДОБАВЛЕН: Алиас для совместимости с другими компонентами
    const getDevices = async () => {
        // Если модемы уже загружены и это было недавно, возвращаем кэшированные данные
        if (modems.value.length > 0 && lastUpdate.value) {
            const timeSinceUpdate = Date.now() - lastUpdate.value.getTime()
            if (timeSinceUpdate < 30000) { // 30 секунд
                return modems.value
            }
        }

        // Иначе загружаем заново
        return await fetchModems()
    }

    const getModemById = async (modemId) => {
        try {
            const response = await api.get(`/admin/devices/${modemId}`)
            return response.data
        } catch (err) {
            console.error('Failed to fetch modem details:', err)
            throw err
        }
    }

    const rotateModemIP = async (modemId) => {
        try {
            const response = await api.post(`/admin/devices/${modemId}/rotate`)

            // Update modem status in store
            const modemIndex = modems.value.findIndex(m => m.modem_id === modemId)
            if (modemIndex !== -1) {
                modems.value[modemIndex].last_rotation = new Date().toISOString()
            }

            return response.data
        } catch (err) {
            console.error('Failed to rotate modem IP:', err)
            throw err
        }
    }

    const rotateAllModems = async () => {
        try {
            const response = await api.post('/admin/devices/rotate-all')

            // Update all modem rotation timestamps
            const now = new Date().toISOString()
            modems.value.forEach(modem => {
                if (modem.status === 'online') {
                    modem.last_rotation = now
                }
            })

            return response.data
        } catch (err) {
            console.error('Failed to rotate all modems:', err)
            throw err
        }
    }

    const updateRotationInterval = async (modemId, interval) => {
        try {
            const response = await api.put(`/admin/devices/${modemId}/rotation-interval`, null, {
                params: {interval}
            })

            // Update modem rotation interval in store
            const modemIndex = modems.value.findIndex(m => m.modem_id === modemId)
            if (modemIndex !== -1) {
                modems.value[modemIndex].rotation_interval = interval
            }

            return response.data
        } catch (err) {
            console.error('Failed to update rotation interval:', err)
            throw err
        }
    }

    const toggleAutoRotation = async (modemId, enabled) => {
        try {
            const response = await api.put(`/admin/devices/${modemId}/auto-rotation`, null, {
                params: {enabled}
            })

            // Update modem auto rotation setting in store
            const modemIndex = modems.value.findIndex(m => m.modem_id === modemId)
            if (modemIndex !== -1) {
                modems.value[modemIndex].auto_rotation = enabled
            }

            return response.data
        } catch (err) {
            console.error('Failed to toggle auto rotation:', err)
            throw err
        }
    }

    const addModem = async (modemData) => {
        try {
            const response = await api.post('/admin/devices', modemData)

            // Add new modem to store
            modems.value.push(response.data)

            return response.data
        } catch (err) {
            console.error('Failed to add modem:', err)
            throw err
        }
    }

    const updateModem = async (modemId, modemData) => {
        try {
            const response = await api.put(`/admin/devices/${modemId}`, modemData)

            // Update modem in store
            const modemIndex = modems.value.findIndex(m => m.modem_id === modemId)
            if (modemIndex !== -1) {
                modems.value[modemIndex] = {...modems.value[modemIndex], ...response.data}
            }

            return response.data
        } catch (err) {
            console.error('Failed to update modem:', err)
            throw err
        }
    }

    const deleteModem = async (modemId) => {
        try {
            await api.delete(`/admin/devices/${modemId}`)

            // Remove modem from store
            const modemIndex = modems.value.findIndex(m => m.modem_id === modemId)
            if (modemIndex !== -1) {
                modems.value.splice(modemIndex, 1)
            }

            return true
        } catch (err) {
            console.error('Failed to delete modem:', err)
            throw err
        }
    }

    const getModemStats = async (modemId) => {
        try {
            const response = await api.get(`/admin/devices/${modemId}/stats`)
            return response.data
        } catch (err) {
            console.error('Failed to fetch modem stats:', err)
            throw err
        }
    }

    const testModem = async (modemId) => {
        try {
            const response = await api.post(`/proxy/test`, null, {
                params: {modem_id: modemId}
            })
            return response.data
        } catch (err) {
            console.error('Failed to test modem:', err)
            throw err
        }
    }

    const testModemBak = async (modemId) => {
        try {
            // ВРЕМЕННО используем простой тест вместо proxy/test
            const response = await api.post(`/admin/devices/${modemId}/test`)

            // Адаптируем ответ под ожидаемый формат
            const data = response.data

            return {
                success: data.overall_success || false,
                message: data.message || 'Test completed',
                response_time_ms: data.test_details?.direct_http_test?.response_time_ms || 0,
                external_ip: data.external_ip || 'Unknown',
                device_type: data.device_type || 'Unknown',
                test_details: data.test_details || {},
                timestamp: data.test_timestamp || Date.now()
            }
        } catch (err) {
            console.error('Failed to test modem:', err)
            throw err
        }
    }

    const getModemsByStatus = (status) => {
        return modems.value.filter(modem => modem.status === status)
    }

    const getModemsByType = (type) => {
        return modems.value.filter(modem => modem.modem_type === type)
    }

    const searchModems = (query) => {
        if (!query) return modems.value

        const lowerQuery = query.toLowerCase()
        return modems.value.filter(modem =>
            modem.modem_id.toLowerCase().includes(lowerQuery) ||
            modem.interface.toLowerCase().includes(lowerQuery) ||
            modem.modem_type.toLowerCase().includes(lowerQuery) ||
            (modem.external_ip && modem.external_ip.toLowerCase().includes(lowerQuery))
        )
    }

    const clearError = () => {
        error.value = ''
    }

    return {
        // State
        modems,
        isLoading,
        error,
        lastUpdate,

        // Getters
        totalModems,
        onlineModems,
        offlineModems,
        busyModems,
        modemsByType,
        averageSuccessRate,
        totalRequests,

        // Actions
        fetchModems,
        getDevices, // ДОБАВЛЕНО: алиас для совместимости
        getModemById,
        rotateModemIP,
        rotateAllModems,
        updateRotationInterval,
        toggleAutoRotation,
        addModem,
        updateModem,
        deleteModem,
        getModemStats,
        testModem,
        getModemsByStatus,
        getModemsByType,
        searchModems,
        clearError
    }
})
