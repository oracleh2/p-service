// frontend/src/stores/system.js
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/utils/api'

export const useSystemStore = defineStore('system', () => {
  // State
  const systemHealth = ref({
    database: 'unknown',
    redis: 'unknown',
    proxy_server: 'unknown',
    modem_manager: 'unknown'
  })

  const systemMetrics = ref({
    total_modems: 0,
    online_modems: 0,
    offline_modems: 0,
    total_requests: 0,
    success_rate: 0,
    avg_response_time: 0
  })

  const isLoading = ref(false)
  const lastUpdated = ref(null)

  // Computed
  const systemStatus = computed(() => {
    const allUp = Object.values(systemHealth.value).every(status =>
      status === 'up' || status === 'running'
    )

    if (allUp) {
      return {
        text: 'All Systems Operational',
        color: 'bg-green-400'
      }
    }

    const someDown = Object.values(systemHealth.value).some(status =>
      status === 'down' || status === 'stopped'
    )

    if (someDown) {
      return {
        text: 'System Issues Detected',
        color: 'bg-red-400'
      }
    }

    return {
      text: 'System Status Unknown',
      color: 'bg-yellow-400'
    }
  })

  const totalModems = computed(() => systemMetrics.value.total_modems)
  const onlineModems = computed(() => systemMetrics.value.online_modems)
  const offlineModems = computed(() => systemMetrics.value.offline_modems)
  const successRate = computed(() => systemMetrics.value.success_rate)

  // Actions
  const fetchSystemStatus = async () => {
    try {
      isLoading.value = true

      const response = await api.get('/admin/system/health')
      systemHealth.value = response.data.components || systemHealth.value
      lastUpdated.value = new Date()

    } catch (error) {
      console.error('Failed to fetch system status:', error)
      // Don't throw error to prevent breaking the UI
    } finally {
      isLoading.value = false
    }
  }

  const fetchSystemMetrics = async () => {
    try {
      const response = await api.get('/stats/overview')
      systemMetrics.value = {
        total_modems: response.data.total_modems || 0,
        online_modems: response.data.online_modems || 0,
        offline_modems: response.data.offline_modems || 0,
        total_requests: response.data.total_requests || 0,
        success_rate: response.data.success_rate || 0,
        avg_response_time: response.data.avg_response_time || 0
      }
    } catch (error) {
      console.error('Failed to fetch system metrics:', error)
    }
  }

  const refreshAll = async () => {
    await Promise.all([
      fetchSystemStatus(),
      fetchSystemMetrics()
    ])
  }

  return {
    // State
    systemHealth,
    systemMetrics,
    isLoading,
    lastUpdated,

    // Computed
    systemStatus,
    totalModems,
    onlineModems,
    offlineModems,
    successRate,

    // Actions
    fetchSystemStatus,
    fetchSystemMetrics,
    refreshAll
  }
})
