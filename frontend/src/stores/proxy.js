import {defineStore} from 'pinia'
import {ref, computed} from 'vue'
import api from '@/utils/api'

export const useProxyStore = defineStore('proxy', () => {
    // ... существующие состояния и методы ...

    // Методы для работы с индивидуальными прокси

    /**
     * Получение списка всех индивидуальных прокси
     */
    const getDedicatedProxies = async () => {
        try {
            const response = await api.get('/admin/dedicated-proxy/list')
            return response.data
        } catch (error) {
            console.error('Error fetching dedicated proxies:', error)
            throw error
        }
    }

    /**
     * Создание индивидуального прокси для устройства
     */
    const createDedicatedProxy = async (proxyData) => {
        try {
            const response = await api.post('/admin/dedicated-proxy/create', proxyData)
            return response.data
        } catch (error) {
            console.error('Error creating dedicated proxy:', error)
            throw error
        }
    }

    /**
     * Удаление индивидуального прокси
     */
    const removeDedicatedProxy = async (deviceId) => {
        try {
            const response = await api.delete(`/admin/dedicated-proxy/${deviceId}`)
            return response.data
        } catch (error) {
            console.error('Error removing dedicated proxy:', error)
            throw error
        }
    }

    /**
     * Получение информации об индивидуальном прокси устройства
     */
    const getDedicatedProxyInfo = async (deviceId) => {
        try {
            const response = await api.get(`/admin/dedicated-proxy/${deviceId}`)
            return response.data
        } catch (error) {
            console.error('Error fetching dedicated proxy info:', error)
            throw error
        }
    }

    /**
     * Перегенерация учетных данных прокси
     */
    const regenerateProxyCredentials = async (deviceId) => {
        try {
            const response = await api.post(`/admin/dedicated-proxy/${deviceId}/regenerate-credentials`)
            return response.data
        } catch (error) {
            console.error('Error regenerating proxy credentials:', error)
            throw error
        }
    }

    /**
     * Получение примеров использования прокси
     */
    const getUsageExamples = async (deviceId) => {
        try {
            const response = await api.get(`/admin/dedicated-proxy/usage/${deviceId}/examples`)
            return response.data
        } catch (error) {
            console.error('Error fetching usage examples:', error)
            throw error
        }
    }

    /**
     * Проверка доступности порта
     */
    const checkPortAvailability = async (port) => {
        try {
            const response = await api.get(`/admin/dedicated-proxy/check-port/${port}`)
            return response.data.available
        } catch (error) {
            console.error('Error checking port availability:', error)
            return false
        }
    }

    /**
     * Получение статистики использования индивидуальных прокси
     */
    const getDedicatedProxyStats = async (deviceId, timeRange = '24h') => {
        try {
            const response = await api.get(`/admin/dedicated-proxy/${deviceId}/stats`, {
                params: {timeRange}
            })
            return response.data
        } catch (error) {
            console.error('Error fetching dedicated proxy stats:', error)
            throw error
        }
    }

    const updateDedicatedProxy = async (deviceId, updateData) => {
        const response = await api.put(`/admin/dedicated-proxy/${deviceId}/update`, updateData)
        return response.data
    }

    return {
        // ... существующие методы ...

        // Новые методы для индивидуальных прокси
        getDedicatedProxies,
        createDedicatedProxy,
        removeDedicatedProxy,
        getDedicatedProxyInfo,
        regenerateProxyCredentials,
        getUsageExamples,
        checkPortAvailability,
        getDedicatedProxyStats,
        updateDedicatedProxy
    }
})
