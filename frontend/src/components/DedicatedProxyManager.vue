<!-- frontend/src/components/DedicatedProxyManager.vue - ПОЛНАЯ ИСПРАВЛЕННАЯ ВЕРСИЯ -->
<template>
  <div class="dedicated-proxy-manager">
    <div class="header">
      <h2>Индивидуальные прокси устройств</h2>
      <button @click="showCreateModal = true" class="btn-primary">
        Создать прокси
      </button>
    </div>

    <!-- Временная диагностика устройств -->
    <div v-if="showDebug" class="debug-panel">
      <h3>🔍 Диагностика устройств</h3>

      <div class="debug-buttons">
        <button @click="debugDevices" class="btn-warning">Диагностировать устройства</button>
        <button @click="testAPI" class="btn-secondary">Тест API</button>
        <button @click="simpleTest" class="btn-primary">Простой тест</button>
        <button @click="syncDevicesToDB" class="btn-info">Синхронизировать устройства с БД</button>
        <button @click="forceRefresh" class="btn-success">Принудительное обновление</button>
        <button @click="showDebug = false" class="btn-danger">Скрыть диагностику</button>
      </div>

      <div v-if="debugResults" class="debug-output">
        <h4>Результаты диагностики:</h4>
        <pre>{{ JSON.stringify(debugResults, null, 2) }}</pre>
      </div>
    </div>

    <div v-if="!showDebug" class="debug-toggle">
      <button @click="showDebug = true" class="btn-secondary">Показать диагностику</button>
    </div>

    <!-- Список прокси -->
    <div class="proxy-list">
      <div v-if="loading" class="loading">
        Загрузка...
      </div>

      <div v-else-if="proxies.length === 0" class="empty-state">
        <p>Индивидуальные прокси не настроены</p>
        <button @click="showCreateModal = true" class="btn-secondary">
          Создать первый прокси
        </button>
      </div>

      <div v-else class="proxy-cards">
        <div v-for="proxy in proxies" :key="proxy.device_id" class="proxy-card">
          <div class="proxy-card-header">
            <h3>{{ proxy.device_name || proxy.device_id }}</h3>
            <div class="status-badges">
              <span :class="['badge', proxy.status === 'running' ? 'badge-success' : 'badge-error']">
                {{ proxy.status }}
              </span>
              <span :class="['badge', getDeviceStatusClass(proxy.device_status)]">
                {{ proxy.device_status }}
              </span>
            </div>
          </div>

          <div class="proxy-info">
            <div class="info-row">
              <strong>Порт:</strong> {{ proxy.port }}
            </div>
            <div class="info-row">
              <strong>URL:</strong>
              <code>{{ proxy.proxy_url }}</code>
              <button @click="copyToClipboard(proxy.proxy_url)" class="btn-copy">
                📋
              </button>
            </div>
            <div class="info-row">
              <strong>Логин:</strong>
              <code>{{ proxy.username }}</code>
              <button @click="copyToClipboard(proxy.username)" class="btn-copy">
                📋
              </button>
            </div>
            <div class="info-row">
              <strong>Пароль:</strong>
              <code>{{ showPasswords[proxy.device_id] ? proxy.password : '••••••••' }}</code>
              <button @click="togglePassword(proxy.device_id)" class="btn-copy">
                {{ showPasswords[proxy.device_id] ? '🙈' : '👁️' }}
              </button>
              <button @click="copyToClipboard(proxy.password)" class="btn-copy">
                📋
              </button>
            </div>
          </div>

          <div class="proxy-actions">
            <button @click="showUsageExamples(proxy)" class="btn-secondary">
              Примеры использования
            </button>
            <button @click="regenerateCredentials(proxy.device_id)" class="btn-warning">
              Сменить пароль
            </button>
            <button @click="removeProxy(proxy.device_id)" class="btn-danger">
              Удалить
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Модальное окно создания прокси -->
    <div v-if="showCreateModal" class="modal-overlay" @click="closeCreateModal">
      <div class="modal" @click.stop>
        <div class="modal-header">
          <h3>Создать индивидуальный прокси</h3>
          <button @click="closeCreateModal" class="modal-close">×</button>
        </div>

        <form @submit.prevent="createProxy" class="modal-body">
          <div class="form-group">
            <label>Устройство:</label>
            <select v-model="newProxy.device_id" required>
              <option value="">Выберите устройство</option>
              <option v-for="device in availableDevices" :key="device.modem_id || device.id" :value="device.modem_id || device.id">
                {{ device.device_info || device.name || device.modem_id || device.id }} ({{ device.status }})
              </option>
            </select>

            <!-- Отладочная информация -->
            <div class="debug-devices" v-if="showDebug">
              <p><strong>Всего доступных устройств:</strong> {{ availableDevices.length }}</p>
              <p><strong>Устройства:</strong></p>
              <ul>
                <li v-for="device in availableDevices" :key="device.modem_id || device.id">
                  ID: {{ device.modem_id || device.id }}, Название: {{ device.device_info || device.name }}, Статус: {{ device.status }}
                </li>
              </ul>
              <p v-if="availableDevices.length === 0" class="form-help error">
                ❌ Нет доступных устройств для создания прокси
              </p>
            </div>
          </div>

          <div class="form-group">
            <label>Порт (опционально):</label>
            <input
              v-model.number="newProxy.port"
              type="number"
              min="6001"
              max="7000"
              placeholder="Автоматически"
            >
          </div>

          <div class="form-group">
            <label>Логин (опционально):</label>
            <input
              v-model="newProxy.username"
              type="text"
              placeholder="Автоматически"
            >
          </div>

          <div class="form-group">
            <label>Пароль (опционально):</label>
            <input
              v-model="newProxy.password"
              type="text"
              placeholder="Автоматически"
            >
          </div>

          <div class="modal-actions">
            <button type="button" @click="closeCreateModal" class="btn-secondary">
              Отмена
            </button>
            <button type="submit" class="btn-primary" :disabled="!newProxy.device_id">
              Создать
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Модальное окно примеров использования -->
    <div v-if="showUsageModal" class="modal-overlay" @click="closeUsageModal">
      <div class="modal modal-large" @click.stop>
        <div class="modal-header">
          <h3>Примеры использования прокси</h3>
          <button @click="closeUsageModal" class="modal-close">×</button>
        </div>

        <div class="modal-body">
          <div v-if="usageExamples" class="usage-examples">
            <div class="example-section">
              <h4>cURL</h4>
              <pre><code>{{ usageExamples.curl.example }}</code></pre>
              <button @click="copyToClipboard(usageExamples.curl.example)" class="btn-copy">
                Копировать
              </button>
            </div>

            <div class="example-section">
              <h4>Python requests</h4>
              <pre><code>{{ usageExamples.python_requests.example }}</code></pre>
              <button @click="copyToClipboard(usageExamples.python_requests.example)" class="btn-copy">
                Копировать
              </button>
            </div>

            <div class="example-section">
              <h4>Настройки браузера</h4>
              <div class="browser-config">
                <div><strong>Тип:</strong> HTTP</div>
                <div><strong>Хост:</strong> {{ usageExamples.proxy_info.host }}</div>
                <div><strong>Порт:</strong> {{ usageExamples.proxy_info.port }}</div>
                <div><strong>Логин:</strong> {{ usageExamples.proxy_info.username }}</div>
                <div><strong>Пароль:</strong> {{ usageExamples.proxy_info.password }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, reactive } from 'vue'
import { useProxyStore } from '../stores/proxy'
import { useDeviceStore } from '../stores/devices'
import { useAuthStore } from '../stores/auth'
import api from '../utils/api'

export default {
  name: 'DedicatedProxyManager',
  setup() {
    const proxyStore = useProxyStore()
    const deviceStore = useDeviceStore()

    const loading = ref(false)
    const proxies = ref([])
    const availableDevices = ref([])
    const showCreateModal = ref(false)
    const showUsageModal = ref(false)
    const usageExamples = ref(null)
    const showPasswords = reactive({})
    const showDebug = ref(true) // Показываем диагностику по умолчанию
    const debugResults = ref(null)

    const newProxy = reactive({
      device_id: '',
      port: null,
      username: '',
      password: ''
    })

    // Загрузка данных
    const loadProxies = async () => {
      loading.value = true
      try {
        const response = await proxyStore.getDedicatedProxies()
        proxies.value = response.proxies
      } catch (error) {
        console.error('Error loading proxies:', error)
      } finally {
        loading.value = false
      }
    }

    const loadAvailableDevices = async () => {
      try {
        console.log('🔍 Loading available devices...')

        // ИСПРАВЛЕНО: используем fetchModems вместо getDevices
        const devices = await deviceStore.fetchModems()
        console.log('✅ Loaded devices:', devices)

        // Убеждаемся что получили массив
        const devicesArray = Array.isArray(devices) ? devices : []
        console.log('📦 Devices array:', devicesArray)

        // Фильтрация устройств без прокси
        const proxyDeviceIds = new Set(proxies.value.map(p => p.device_id))
        console.log('📋 Existing proxy device IDs:', proxyDeviceIds)

        // ИСПРАВЛЕНО: используем modem_id или id для сравнения
        availableDevices.value = devicesArray.filter(d => {
          const deviceId = d.modem_id || d.id
          const hasProxy = proxyDeviceIds.has(deviceId)
          console.log(`📱 Device ${deviceId}: hasProxy = ${hasProxy}`)
          return !hasProxy
        })

        console.log('✅ Available devices after filter:', availableDevices.value)
        console.log('📊 Total available devices count:', availableDevices.value.length)

        // Дополнительная проверка структуры устройств
        if (availableDevices.value.length > 0) {
          console.log('🔍 First device structure:', availableDevices.value[0])
        }

      } catch (error) {
        console.error('❌ Error loading devices:', error)

        // Предпринимаем попытку получить устройства напрямую из store
        try {
          console.log('🔄 Trying to fetch from store directly...')
          await deviceStore.fetchModems()
          const devices = deviceStore.modems || []
          console.log('🏪 Store devices:', devices)

          const devicesArray = Array.isArray(devices) ? devices : []
          const proxyDeviceIds = new Set(proxies.value.map(p => p.device_id))

          availableDevices.value = devicesArray.filter(d => {
            const deviceId = d.modem_id || d.id
            return !proxyDeviceIds.has(deviceId)
          })

          console.log('✅ Final available devices:', availableDevices.value)
        } catch (secondError) {
          console.error('❌ Second attempt failed:', secondError)
          availableDevices.value = []
        }
      }
    }

    // Диагностические функции
    const debugDevices = async () => {
      try {
        console.log('🔍 Starting comprehensive device debug...')

        const results = {
          timestamp: new Date().toISOString(),
          api_test: null,
          store_state: null,
          device_manager_debug: null,
          auth_test: null,
          errors: []
        }

        // 0. Детальный тест авторизации
        try {
          console.log('🔑 Testing authentication in detail...')

          // Проверяем локальное хранилище
          const localToken = localStorage.getItem('token')
          const localUser = localStorage.getItem('user')

          console.log('💾 Local storage:', {
            hasToken: !!localToken,
            tokenLength: localToken?.length || 0,
            hasUser: !!localUser,
            user: localUser ? JSON.parse(localUser) : null
          })

          // Проверяем store
          const authStore = useAuthStore()
          console.log('🏪 Auth store:', {
            isAuthenticated: authStore.isAuthenticated,
            isAdmin: authStore.isAdmin,
            user: authStore.user,
            token: authStore.token ? `${authStore.token.substring(0, 20)}...` : null
          })

          // Проверяем API запрос
          const authResponse = await api.get('/auth/me')
          results.auth_test = {
            status: 200,
            authenticated: true,
            user: authResponse.data,
            local_storage: {
              hasToken: !!localToken,
              hasUser: !!localUser,
              storedUser: localUser ? JSON.parse(localUser) : null
            },
            store_state: {
              isAuthenticated: authStore.isAuthenticated,
              isAdmin: authStore.isAdmin,
              user: authStore.user
            }
          }
          console.log('✅ Auth test passed:', results.auth_test)
        } catch (error) {
          console.error('❌ Auth test failed:', error)
          results.auth_test = {
            status: error.response?.status || 'unknown',
            authenticated: false,
            error: error.response?.data || error.message,
            local_storage: {
              hasToken: !!localStorage.getItem('token'),
              hasUser: !!localStorage.getItem('user')
            }
          }
          results.errors.push(`Auth test: ${error.message}`)
        }

        // 1. Тест API устройств
        try {
          console.log('📡 Testing /admin/devices API...')
          const response = await api.get('/admin/devices')
          results.api_test = {
            status: 200,
            ok: true,
            data: response.data,
            device_count: Array.isArray(response.data) ? response.data.length : 0
          }
          console.log('✅ API response:', results.api_test)
        } catch (error) {
          console.error('❌ API test failed:', error)
          results.api_test = {
            status: error.response?.status || 'unknown',
            ok: false,
            error: error.response?.data || error.message
          }
          results.errors.push(`API test: ${error.message}`)

          // Попробуем альтернативный путь
          try {
            console.log('📡 Trying alternative API path /api/v1/admin/devices...')
            const altResponse = await api.get('/api/v1/admin/devices')
            results.api_test.alternative = {
              status: 200,
              data: altResponse.data,
              path: '/api/v1/admin/devices'
            }
          } catch (altError) {
            results.api_test.alternative = {
              status: altError.response?.status || 'unknown',
              error: altError.message,
              path: '/api/v1/admin/devices'
            }
          }
        }

        // 2. Состояние store
        try {
          results.store_state = {
            modems: deviceStore.modems,
            isLoading: deviceStore.isLoading,
            error: deviceStore.error,
            lastUpdate: deviceStore.lastUpdate
          }
          console.log('🏪 Store state:', results.store_state)
        } catch (error) {
          console.error('❌ Store state check failed:', error)
          results.errors.push(`Store state: ${error.message}`)
        }

        // 3. Тест device manager debug endpoint (опционально - игнорируем 404)
        try {
          console.log('🔧 Testing device manager debug...')
          const debugResponse = await api.get('/admin/devices/debug')
          results.device_manager_debug = {
            status: 200,
            data: debugResponse.data
          }
          console.log('🔧 Device manager debug:', results.device_manager_debug)
        } catch (error) {
          console.log('❌ Device manager debug failed (expected - endpoint may not exist):', error.response?.status || error.message)
          results.device_manager_debug = {
            status: error.response?.status || 'unknown',
            error: error.response?.data || error.message,
            note: 'This endpoint may not be available - this is normal'
          }
        }

        debugResults.value = results
        console.log('📋 Complete debug results:', results)

      } catch (error) {
        console.error('❌ Debug function failed:', error)
        debugResults.value = { error: error.message }
      }
    }

    const testAPI = async () => {
      try {
        console.log('🧪 Testing API endpoints...')

        const testResults = {
          timestamp: new Date().toISOString(),
          tests: []
        }

        // Тест различных endpoint'ов
        const endpointsToTest = [
          { path: '/admin/devices', method: 'GET', description: 'Admin devices (legacy)' },
          { path: '/api/v1/admin/devices', method: 'GET', description: 'Admin devices (new API)' },
          { path: '/admin/devices/debug', method: 'GET', description: 'Debug endpoint' },
          { path: '/auth/me', method: 'GET', description: 'Current user info' },
          { path: '/admin/devices/discover', method: 'POST', description: 'Device discovery' }
        ]

        for (const endpoint of endpointsToTest) {
          try {
            console.log(`🔍 Testing ${endpoint.method} ${endpoint.path}...`)

            let response
            if (endpoint.method === 'GET') {
              response = await api.get(endpoint.path)
            } else if (endpoint.method === 'POST') {
              response = await api.post(endpoint.path)
            }

            testResults.tests.push({
              path: endpoint.path,
              method: endpoint.method,
              description: endpoint.description,
              status: response.status,
              success: true,
              dataLength: Array.isArray(response.data) ? response.data.length :
                         typeof response.data === 'object' ? Object.keys(response.data).length :
                         response.data ? response.data.toString().length : 0
            })

            console.log(`✅ ${endpoint.path}: ${response.status}`)

          } catch (error) {
            console.log(`❌ ${endpoint.path}: ${error.response?.status || 'Network Error'}`)

            testResults.tests.push({
              path: endpoint.path,
              method: endpoint.method,
              description: endpoint.description,
              status: error.response?.status || 'unknown',
              success: false,
              error: error.response?.data?.detail || error.message
            })
          }

          // Небольшая пауза между запросами
          await new Promise(resolve => setTimeout(resolve, 100))
        }

        // Тест через device store
        try {
          console.log('🏪 Testing device store...')
          const storeData = await deviceStore.fetchModems()
          testResults.store_test = {
            success: true,
            devices_count: Array.isArray(storeData) ? storeData.length : 0,
            first_device: Array.isArray(storeData) && storeData.length > 0 ? storeData[0] : null
          }
        } catch (error) {
          testResults.store_test = {
            success: false,
            error: error.message
          }
        }

        debugResults.value = testResults
        console.log('📋 API test results:', testResults)

      } catch (error) {
        console.error('❌ API test failed:', error)
        debugResults.value = {
          api_test_error: error.message,
          timestamp: new Date().toISOString()
        }
      }
    }

    const forceRefresh = async () => {
      console.log('🔄 Force refresh...')
      try {
        // Очищаем все состояния
        availableDevices.value = []
        proxies.value = []

        // Принудительно загружаем данные
        await loadProxies()
        await loadAvailableDevices()

        console.log('✅ Force refresh completed')
        debugResults.value = {
          force_refresh: {
            success: true,
            proxies_count: proxies.value.length,
            available_devices_count: availableDevices.value.length
          }
        }
      } catch (error) {
        console.error('❌ Force refresh failed:', error)
        debugResults.value = {
          force_refresh: {
            success: false,
            error: error.message
          }
        }
      }
    }

    const syncDevicesToDB = async () => {
      console.log('🔄 Syncing devices to database...')
      try {
        const response = await api.post('/admin/devices/sync-to-db')
        console.log('✅ Sync completed:', response.data)

        debugResults.value = {
          sync_result: {
            success: true,
            discovered_devices: response.data.discovered_devices,
            database_devices: response.data.database_devices,
            message: response.data.message,
            devices: response.data.devices
          }
        }

        // Обновляем список доступных устройств
        await loadAvailableDevices()

        alert(`Устройства синхронизированы!\nОбнаружено: ${response.data.discovered_devices}\nВ БД: ${response.data.database_devices}`)

      } catch (error) {
        console.error('❌ Sync failed:', error)
        debugResults.value = {
          sync_result: {
            success: false,
            error: error.response?.data?.detail || error.message
          }
        }
        alert(`Ошибка синхронизации: ${error.response?.data?.detail || error.message}`)
      }
    }

    // Создание прокси
    const createProxy = async () => {
      try {
        console.log('🎯 Creating dedicated proxy with data:', newProxy)

        const proxyData = {
          device_id: newProxy.device_id,
          ...(newProxy.port && { port: newProxy.port }),
          ...(newProxy.username && { username: newProxy.username }),
          ...(newProxy.password && { password: newProxy.password })
        }

        console.log('📡 Sending request to API:', proxyData)

        const result = await proxyStore.createDedicatedProxy(proxyData)
        console.log('✅ Proxy created successfully:', result)

        await loadProxies()
        await loadAvailableDevices()
        closeCreateModal()

        // Показываем успешное уведомление
        alert(`Прокси успешно создан!\nПорт: ${result.port}\nЛогин: ${result.username}`)

      } catch (error) {
        console.error('❌ Error creating proxy:', error)

        // Детальная диагностика ошибки
        let errorMessage = 'Неизвестная ошибка'

        if (error.response) {
          console.error('📊 Response status:', error.response.status)
          console.error('📊 Response data:', error.response.data)
          console.error('📊 Response headers:', error.response.headers)

          if (error.response.status === 500) {
            errorMessage = `Ошибка сервера (500): ${error.response.data?.detail || 'Внутренняя ошибка сервера'}`
          } else if (error.response.status === 409) {
            errorMessage = 'У этого устройства уже есть индивидуальный прокси'
          } else if (error.response.status === 404) {
            errorMessage = 'Устройство не найдено'
          } else {
            errorMessage = error.response.data?.detail || `HTTP ${error.response.status}`
          }
        } else if (error.request) {
          errorMessage = 'Ошибка сети - сервер не отвечает'
        } else {
          errorMessage = error.message || 'Неизвестная ошибка'
        }

        alert(`Ошибка создания прокси: ${errorMessage}`)

        // Проверяем, создался ли прокси несмотря на ошибку
        console.log('🔄 Checking if proxy was created despite error...')
        setTimeout(async () => {
          try {
            await loadProxies()
            console.log('📋 Proxies reloaded after error')
          } catch (reloadError) {
            console.error('❌ Failed to reload proxies:', reloadError)
          }
        }, 2000)
      }
    }

    // Удаление прокси
    const removeProxy = async (deviceId) => {
      if (!confirm('Удалить индивидуальный прокси для этого устройства?')) {
        return
      }

      try {
        await proxyStore.removeDedicatedProxy(deviceId)
        await loadProxies()
        await loadAvailableDevices()
      } catch (error) {
        console.error('Error removing proxy:', error)
        alert('Ошибка удаления прокси: ' + error.message)
      }
    }

    // Смена учетных данных
    const regenerateCredentials = async (deviceId) => {
      if (!confirm('Сгенерировать новые учетные данные? Старые перестанут работать.')) {
        return
      }

      try {
        await proxyStore.regenerateProxyCredentials(deviceId)
        await loadProxies()
      } catch (error) {
        console.error('Error regenerating credentials:', error)
        alert('Ошибка смены учетных данных: ' + error.message)
      }
    }

    // Показ примеров использования
    const showUsageExamples = async (proxy) => {
      try {
        const examples = await proxyStore.getUsageExamples(proxy.device_id)
        usageExamples.value = examples
        showUsageModal.value = true
      } catch (error) {
        console.error('Error loading usage examples:', error)
        alert('Ошибка загрузки примеров: ' + error.message)
      }
    }

    // Утилиты
    const copyToClipboard = async (text) => {
      try {
        await navigator.clipboard.writeText(text)
        alert('Скопировано в буфер обмена!')
      } catch (error) {
        console.error('Error copying to clipboard:', error)
      }
    }

    const togglePassword = (deviceId) => {
      showPasswords[deviceId] = !showPasswords[deviceId]
    }

    const getDeviceStatusClass = (status) => {
      switch (status) {
        case 'online': return 'badge-success'
        case 'offline': return 'badge-error'
        case 'busy': return 'badge-warning'
        default: return 'badge-gray'
      }
    }

    const closeCreateModal = () => {
      showCreateModal.value = false
      Object.assign(newProxy, {
        device_id: '',
        port: null,
        username: '',
        password: ''
      })
    }

    const simpleTest = async () => {
      console.log('🧪 Simple device test...')

      try {
        // Используем api utility с авторизацией
        const response = await api.get('/admin/devices')
        console.log('📡 API response:', response.data)

        const devices = response.data
        if (Array.isArray(devices) && devices.length > 0) {
          // Обновляем доступные устройства напрямую
          const proxyDeviceIds = new Set(proxies.value.map(p => p.device_id))
          availableDevices.value = devices.filter(d => {
            const deviceId = d.modem_id || d.id
            return !proxyDeviceIds.has(deviceId)
          })

          console.log('🎯 Updated available devices:', availableDevices.value)

          debugResults.value = {
            simple_test: {
              success: true,
              total_devices: devices.length,
              available_devices: availableDevices.value.length,
              devices: devices,
              available: availableDevices.value
            }
          }
        } else {
          console.log('❌ No devices found')
          debugResults.value = {
            simple_test: {
              success: false,
              message: 'No devices found in API response',
              response: devices
            }
          }
        }

      } catch (error) {
        console.error('❌ Simple test failed:', error)
        debugResults.value = {
          simple_test: {
            success: false,
            error: error.message,
            details: error
          }
        }
      }
    }

    const closeUsageModal = () => {
      showUsageModal.value = false
      usageExamples.value = null
    }

    // Инициализация
    onMounted(async () => {
      await loadProxies()
      await loadAvailableDevices()
    })

    return {
      loading,
      proxies,
      availableDevices,
      showCreateModal,
      showUsageModal,
      usageExamples,
      showPasswords,
      newProxy,
      showDebug,
      debugResults,
      loadProxies,
      createProxy,
      removeProxy,
      regenerateCredentials,
      showUsageExamples,
      copyToClipboard,
      togglePassword,
      getDeviceStatusClass,
      closeCreateModal,
      closeUsageModal,

  }
}
</script>

<style scoped>
.dedicated-proxy-manager {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 30px;
}

.header h2 {
  font-size: 24px;
  font-weight: 600;
  color: #333;
}

.proxy-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: 20px;
}

.proxy-card {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.proxy-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.proxy-card-header h3 {
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.status-badges {
  display: flex;
  gap: 8px;
}

.badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  text-transform: uppercase;
}

.badge-success { background: #d1fae5; color: #065f46; }
.badge-warning { background: #fef3c7; color: #92400e; }
.badge-error { background: #fee2e2; color: #991b1b; }
.badge-gray { background: #f3f4f6; color: #6b7280; }

.proxy-info {
  margin-bottom: 20px;
}

.info-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.info-row code {
  background: #f3f4f6;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: monospace;
  font-size: 14px;
}

.btn-copy {
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 4px;
  font-size: 12px;
}

.btn-copy:hover {
  background: #f3f4f6;
}

.proxy-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.btn-primary, .btn-secondary, .btn-warning, .btn-danger, .btn-success, .btn-info {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
}

.btn-primary { background: #3b82f6; color: white; }
.btn-secondary { background: #6b7280; color: white; }
.btn-warning { background: #f59e0b; color: white; }
.btn-danger { background: #ef4444; color: white; }
.btn-success { background: #10b981; color: white; }
.btn-info { background: #06b6d4; color: white; }

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.modal {
  background: white;
  border-radius: 8px;
  max-width: 500px;
  width: 90%;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-large {
  max-width: 800px;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid #e5e7eb;
}

.modal-close {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
}

.modal-body {
  padding: 20px;
}

.form-group {
  margin-bottom: 20px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
}

.form-group input, .form-group select {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  font-size: 14px;
}

.form-help {
  margin-top: 4px;
  font-size: 12px;
  color: #6b7280;
  font-style: italic;
}

.form-help.error {
  color: #dc2626;
  font-weight: 500;
}

.modal-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  margin-top: 20px;
}

.usage-examples {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.example-section h4 {
  margin-bottom: 12px;
  font-size: 16px;
  font-weight: 600;
}

.example-section pre {
  background: #f8fafc;
  padding: 16px;
  border-radius: 4px;
  overflow-x: auto;
  margin-bottom: 8px;
}

.browser-config {
  background: #f8fafc;
  padding: 16px;
  border-radius: 4px;
}

.browser-config div {
  margin-bottom: 8px;
}

.loading, .empty-state {
  text-align: center;
  padding: 40px;
  color: #6b7280;
}

.debug-panel {
  background: #fef3c7;
  border: 2px solid #f59e0b;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 30px;
}

.debug-buttons {
  margin-bottom: 15px;
}

.debug-buttons button {
  margin-right: 10px;
}

.debug-output {
  background: #f8fafc;
  padding: 15px;
  border-radius: 4px;
  max-height: 400px;
  overflow-y: auto;
}

.debug-output pre {
  font-size: 12px;
  white-space: pre-wrap;
}

.debug-toggle {
  margin-bottom: 20px;
}

.debug-devices {
  margin-top: 10px;
  padding: 10px;
  background: #f8fafc;
  border-radius: 4px;
  border: 1px solid #e5e7eb;
}

.debug-devices ul {
  margin: 5px 0;
  padding-left: 20px;
}

.debug-devices li {
  margin-bottom: 5px;
  font-size: 12px;
}
</style>
