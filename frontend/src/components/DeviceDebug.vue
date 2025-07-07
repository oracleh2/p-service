<!-- frontend/src/components/DeviceDebug.vue -->
<template>
  <div class="device-debug">
    <div class="header">
      <h2>🔧 Отладка устройств</h2>
      <p class="subtitle">Диагностика, обнаружение и синхронизация устройств с базой данных</p>
    </div>

    <!-- Быстрые действия -->
    <div class="quick-actions">
      <h3>Быстрые действия</h3>
      <div class="action-buttons">
        <button @click="discoverDevices" class="btn-primary" :disabled="loading">
          🔍 Обнаружить устройства
        </button>
        <button @click="syncDevicesToDB" class="btn-success" :disabled="loading">
          💾 Синхронизировать с БД
        </button>
        <button @click="getDevicesFromDB" class="btn-info" :disabled="loading">
          📋 Показать устройства из БД
        </button>
        <button @click="runFullDiagnostic" class="btn-warning" :disabled="loading">
          🩺 Полная диагностика
        </button>
      </div>
    </div>

    <!-- Статистика -->
    <div class="stats-section" v-if="stats">
      <h3>Статистика</h3>
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-value">{{ stats.discovered_devices }}</div>
          <div class="stat-label">Обнаружено устройств</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ stats.database_devices }}</div>
          <div class="stat-label">Устройств в БД</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ stats.online_devices }}</div>
          <div class="stat-label">Онлайн устройств</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ stats.with_proxy }}</div>
          <div class="stat-label">С настроенным прокси</div>
        </div>
      </div>
    </div>

    <!-- Детальное тестирование -->
    <div class="detailed-testing">
      <h3>Детальное тестирование</h3>
      <div class="test-buttons">
        <button @click="testAPIEndpoints" class="btn-secondary" :disabled="loading">
          📡 Тест API endpoints
        </button>
        <button @click="testDeviceManager" class="btn-secondary" :disabled="loading">
          🔧 Тест Device Manager
        </button>
        <button @click="testAuthentication" class="btn-secondary" :disabled="loading">
          🔑 Тест авторизации
        </button>
        <button @click="testDatabaseConnection" class="btn-secondary" :disabled="loading">
          🗄️ Тест подключения к БД
        </button>
      </div>
    </div>

    <!-- Результаты -->
    <div class="results-section" v-if="results">
      <h3>Результаты</h3>

      <!-- Вкладки результатов -->
      <div class="tabs">
        <button
          v-for="(tab, key) in availableTabs"
          :key="key"
          @click="activeTab = key"
          :class="['tab-button', { active: activeTab === key }]"
        >
          {{ tab.label }}
        </button>
      </div>

      <!-- Содержимое вкладок -->
      <div class="tab-content">
        <div v-if="activeTab === 'summary'" class="result-summary">
          <div class="summary-cards">
            <div class="summary-card"
                 v-for="(result, key) in results"
                 :key="key"
                 :class="getResultClass(result)">
              <h4>{{ getResultTitle(key) }}</h4>
              <div class="result-status">
                {{ getResultStatus(result) }}
              </div>
              <div class="result-details" v-if="getResultDetails(result)">
                {{ getResultDetails(result) }}
              </div>
            </div>
          </div>
        </div>

        <div v-else class="result-details-view">
          <pre>{{ JSON.stringify(results[activeTab], null, 2) }}</pre>
        </div>
      </div>
    </div>

    <!-- Список устройств -->
    <div class="devices-section" v-if="devices && devices.length > 0">
      <h3>Обнаруженные устройства</h3>
      <div class="devices-table">
        <table>
          <thead>
            <tr>
              <th>ID устройства</th>
              <th>Тип</th>
              <th>Статус</th>
              <th>Интерфейс</th>
              <th>Внешний IP</th>
              <th>Оператор</th>
              <th>В БД</th>
              <th>Прокси</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="device in devices" :key="device.id || device.modem_id">
              <td class="device-id">{{ device.name || device.modem_id || device.id }}</td>
              <td>
                <span :class="['device-type', `type-${device.device_type || device.modem_type}`]">
                  {{ device.device_type || device.modem_type }}
                </span>
              </td>
              <td>
                <span :class="['status-badge', `status-${device.status}`]">
                  {{ device.status }}
                </span>
              </td>
              <td class="interface">{{ device.interface || device.usb_interface || 'N/A' }}</td>
              <td class="external-ip">{{ device.current_external_ip || device.external_ip || 'N/A' }}</td>
              <td>{{ device.operator || 'Unknown' }}</td>
              <td>
                <span :class="['db-status', device.in_database ? 'in-db' : 'not-in-db']">
                  {{ device.in_database ? '✅' : '❌' }}
                </span>
              </td>
              <td>
                <span :class="['proxy-status', device.proxy_enabled ? 'has-proxy' : 'no-proxy']">
                  {{ device.proxy_enabled ? '🔗' : '-' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Загрузка -->
    <div v-if="loading" class="loading-overlay">
      <div class="loading-spinner"></div>
      <p>{{ loadingMessage }}</p>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, computed } from 'vue'
import { useDeviceStore } from '../stores/devices'
import { useAuthStore } from '../stores/auth'
import api from '../utils/api'

export default {
  name: 'DeviceDebug',
  setup() {
    const deviceStore = useDeviceStore()
    const authStore = useAuthStore()

    const loading = ref(false)
    const loadingMessage = ref('')
    const results = ref(null)
    const devices = ref([])
    const stats = ref(null)
    const activeTab = ref('summary')

    const availableTabs = computed(() => {
      const tabs = { summary: { label: 'Сводка' } }
      if (results.value) {
        Object.keys(results.value).forEach(key => {
          tabs[key] = { label: getResultTitle(key) }
        })
      }
      return tabs
    })

    // Основные действия
    const discoverDevices = async () => {
      try {
        loading.value = true
        loadingMessage.value = 'Обнаружение устройств...'

        const response = await api.post('/admin/devices/discover')

        updateStats({
          discovered_devices: response.data.devices_found,
          database_devices: 0
        })

        results.value = {
          ...results.value,
          discovery: {
            success: true,
            message: response.data.message,
            devices_found: response.data.devices_found,
            devices: response.data.devices
          }
        }

        devices.value = response.data.devices || []

      } catch (error) {
        console.error('Discovery failed:', error)
        results.value = {
          ...results.value,
          discovery: {
            success: false,
            error: error.response?.data?.detail || error.message
          }
        }
      } finally {
        loading.value = false
      }
    }

    const syncDevicesToDB = async () => {
      try {
        loading.value = true
        loadingMessage.value = 'Синхронизация с базой данных...'

        const response = await api.post('/admin/devices/sync-to-db')

        updateStats({
          discovered_devices: response.data.discovered_devices,
          database_devices: response.data.database_devices
        })

        results.value = {
          ...results.value,
          sync: {
            success: true,
            message: response.data.message,
            discovered_devices: response.data.discovered_devices,
            database_devices: response.data.database_devices,
            devices: response.data.devices
          }
        }

        devices.value = response.data.devices || []

      } catch (error) {
        console.error('Sync failed:', error)
        results.value = {
          ...results.value,
          sync: {
            success: false,
            error: error.response?.data?.detail || error.message
          }
        }
      } finally {
        loading.value = false
      }
    }

    const getDevicesFromDB = async () => {
      try {
        loading.value = true
        loadingMessage.value = 'Получение устройств из БД...'

        const response = await api.get('/admin/devices/from-db')

        updateStats({
          database_devices: response.data.count
        })

        results.value = {
          ...results.value,
          database: {
            success: true,
            message: response.data.message,
            count: response.data.count,
            devices: response.data.devices
          }
        }

        // Помечаем устройства как находящиеся в БД
        devices.value = response.data.devices.map(device => ({
          ...device,
          in_database: true
        }))

      } catch (error) {
        console.error('Get from DB failed:', error)
        results.value = {
          ...results.value,
          database: {
            success: false,
            error: error.response?.data?.detail || error.message
          }
        }
      } finally {
        loading.value = false
      }
    }

    const runFullDiagnostic = async () => {
      try {
        loading.value = true
        loadingMessage.value = 'Запуск полной диагностики...'

        // Последовательно запускаем все тесты
        await testAuthentication()
        await testAPIEndpoints()
        await testDeviceManager()
        await discoverDevices()
        await syncDevicesToDB()
        await testDatabaseConnection()

        loadingMessage.value = 'Диагностика завершена'

      } catch (error) {
        console.error('Full diagnostic failed:', error)
      } finally {
        loading.value = false
      }
    }

    // Детальные тесты
    const testAuthentication = async () => {
      try {
        const authResponse = await api.get('/auth/me')

        results.value = {
          ...results.value,
          auth: {
            success: true,
            user: authResponse.data,
            isAdmin: authStore.isAdmin,
            token_present: !!authStore.token
          }
        }
      } catch (error) {
        results.value = {
          ...results.value,
          auth: {
            success: false,
            error: error.response?.data?.detail || error.message
          }
        }
      }
    }

    const testAPIEndpoints = async () => {
      const endpoints = [
        { path: '/admin/devices', method: 'GET', name: 'Список устройств' },
        { path: '/admin/devices/debug', method: 'GET', name: 'Отладка устройств' },
        { path: '/admin/dedicated-proxy/list', method: 'GET', name: 'Список прокси' }
      ]

      const endpointResults = []

      for (const endpoint of endpoints) {
        try {
          const response = await api.get(endpoint.path)
          endpointResults.push({
            ...endpoint,
            success: true,
            status: response.status,
            data_length: Array.isArray(response.data) ? response.data.length :
                        typeof response.data === 'object' ? Object.keys(response.data).length : 0
          })
        } catch (error) {
          endpointResults.push({
            ...endpoint,
            success: false,
            status: error.response?.status || 'network_error',
            error: error.response?.data?.detail || error.message
          })
        }
      }

      results.value = {
        ...results.value,
        api_endpoints: {
          success: endpointResults.every(r => r.success),
          endpoints: endpointResults
        }
      }
    }

    const testDeviceManager = async () => {
      try {
        const response = await api.get('/admin/devices/test-discovery')

        results.value = {
          ...results.value,
          device_manager: {
            success: true,
            adb_devices: response.data.adb_devices,
            usb_interfaces: response.data.usb_interfaces,
            android_devices: response.data.android_devices
          }
        }
      } catch (error) {
        results.value = {
          ...results.value,
          device_manager: {
            success: false,
            error: error.response?.data?.detail || error.message
          }
        }
      }
    }

    const testDatabaseConnection = async () => {
      try {
        // Тестируем подключение к БД через получение конфигурации
        const response = await api.get('/admin/system/config')

        results.value = {
          ...results.value,
          database: {
            ...results.value?.database,
            connection_test: {
              success: true,
              config_entries: response.data.length
            }
          }
        }
      } catch (error) {
        results.value = {
          ...results.value,
          database: {
            ...results.value?.database,
            connection_test: {
              success: false,
              error: error.response?.data?.detail || error.message
            }
          }
        }
      }
    }

    // Утилиты
    const updateStats = (newStats) => {
      stats.value = {
        ...stats.value,
        ...newStats,
        online_devices: devices.value.filter(d => d.status === 'online').length,
        with_proxy: devices.value.filter(d => d.proxy_enabled).length
      }
    }

    const getResultTitle = (key) => {
      const titles = {
        discovery: 'Обнаружение',
        sync: 'Синхронизация',
        database: 'База данных',
        auth: 'Авторизация',
        api_endpoints: 'API endpoints',
        device_manager: 'Device Manager'
      }
      return titles[key] || key
    }

    const getResultStatus = (result) => {
      if (result.success) return '✅ Успешно'
      return '❌ Ошибка'
    }

    const getResultDetails = (result) => {
      if (result.success) {
        if (result.devices_found) return `Найдено устройств: ${result.devices_found}`
        if (result.message) return result.message
      } else {
        return result.error
      }
      return ''
    }

    const getResultClass = (result) => {
      return result.success ? 'success' : 'error'
    }

    // Инициализация
    onMounted(() => {
      // Автоматически запускаем базовую диагностику
      testAuthentication()
    })

    return {
      loading,
      loadingMessage,
      results,
      devices,
      stats,
      activeTab,
      availableTabs,
      discoverDevices,
      syncDevicesToDB,
      getDevicesFromDB,
      runFullDiagnostic,
      testAuthentication,
      testAPIEndpoints,
      testDeviceManager,
      testDatabaseConnection,
      getResultTitle,
      getResultStatus,
      getResultDetails,
      getResultClass
    }
  }
}
</script>

<style scoped>
.device-debug {
  max-width: 1400px;
  margin: 0 auto;
  padding: 20px;
}

.header {
  margin-bottom: 30px;
}

.header h2 {
  font-size: 28px;
  font-weight: 600;
  color: #333;
  margin-bottom: 8px;
}

.subtitle {
  color: #6b7280;
  font-size: 16px;
}

.quick-actions, .detailed-testing {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
}

.quick-actions h3, .detailed-testing h3 {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 15px;
  color: #333;
}

.action-buttons, .test-buttons {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.btn-primary, .btn-secondary, .btn-success, .btn-info, .btn-warning {
  padding: 12px 20px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s;
}

.btn-primary { background: #3b82f6; color: white; }
.btn-secondary { background: #6b7280; color: white; }
.btn-success { background: #10b981; color: white; }
.btn-info { background: #06b6d4; color: white; }
.btn-warning { background: #f59e0b; color: white; }

.btn-primary:hover { background: #2563eb; }
.btn-secondary:hover { background: #4b5563; }
.btn-success:hover { background: #059669; }
.btn-info:hover { background: #0891b2; }
.btn-warning:hover { background: #d97706; }

.btn-primary:disabled, .btn-secondary:disabled, .btn-success:disabled,
.btn-info:disabled, .btn-warning:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.stats-section {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
}

.stats-section h3 {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 15px;
  color: #333;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 15px;
}

.stat-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 15px;
  text-align: center;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 5px;
}

.stat-label {
  font-size: 12px;
  color: #64748b;
  text-transform: uppercase;
  font-weight: 500;
}

.results-section, .devices-section {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
}

.results-section h3, .devices-section h3 {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 15px;
  color: #333;
}

.tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
  border-bottom: 1px solid #e5e7eb;
}

.tab-button {
  padding: 8px 16px;
  border: none;
  background: none;
  cursor: pointer;
  font-size: 14px;
  color: #6b7280;
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
}

.tab-button.active {
  color: #3b82f6;
  border-bottom-color: #3b82f6;
}

.tab-button:hover {
  color: #3b82f6;
}

.tab-content {
  min-height: 200px;
}

.summary-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 15px;
}

.summary-card {
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 15px;
}

.summary-card.success {
  border-color: #10b981;
  background: #f0fdf4;
}

.summary-card.error {
  border-color: #ef4444;
  background: #fef2f2;
}

.summary-card h4 {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 8px;
}

.result-status {
  font-weight: 500;
  margin-bottom: 5px;
}

.result-details {
  font-size: 12px;
  color: #6b7280;
}

.result-details-view pre {
  background: #f8fafc;
  padding: 15px;
  border-radius: 4px;
  overflow-x: auto;
  font-size: 12px;
}

.devices-table {
  overflow-x: auto;
}

.devices-table table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.devices-table th,
.devices-table td {
  padding: 8px 12px;
  border: 1px solid #e5e7eb;
  text-align: left;
}

.devices-table th {
  background: #f8fafc;
  font-weight: 600;
  color: #374151;
}

.device-id {
  font-family: monospace;
  font-size: 12px;
}

.device-type {
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
}

.type-android { background: #dcfce7; color: #166534; }
.type-usb_modem { background: #dbeafe; color: #1e40af; }
.type-raspberry_pi { background: #fef3c7; color: #92400e; }

.status-badge {
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
}

.status-online { background: #dcfce7; color: #166534; }
.status-offline { background: #fee2e2; color: #991b1b; }
.status-busy { background: #fef3c7; color: #92400e; }

.interface, .external-ip {
  font-family: monospace;
  font-size: 12px;
}

.db-status.in-db { color: #10b981; }
.db-status.not-in-db { color: #ef4444; }

.proxy-status.has-proxy { color: #3b82f6; }
.proxy-status.no-proxy { color: #6b7280; }

.loading-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  z-index: 1000;
  color: white;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 4px solid rgba(255, 255, 255, 0.3);
  border-top: 4px solid white;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 15px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
</style>
