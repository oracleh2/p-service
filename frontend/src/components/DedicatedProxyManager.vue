<!-- frontend/src/components/DedicatedProxyManager.vue - ОЧИЩЕННАЯ ВЕРСИЯ БЕЗ ОТЛАДКИ -->
<template>
    <div class="dedicated-proxy-manager">
        <div class="header">
            <h2>Индивидуальные прокси устройств</h2>
            <button @click="showCreateModal = true" class="btn-primary">
                Создать прокси
            </button>
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
                        <button @click="editProxy(proxy)" class="btn-info">
                            Редактировать
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
                            <option v-for="device in availableDevices" :key="device.modem_id || device.id"
                                    :value="device.modem_id || device.id">
                                {{ device.device_info || device.name || device.modem_id || device.id }}
                                ({{ device.status }})
                            </option>
                        </select>

                        <!-- Подсказка если нет устройств -->
                        <div v-if="availableDevices.length === 0" class="no-devices-help">
                            <p class="form-help error">
                                ❌ Нет доступных устройств для создания прокси.
                            </p>
                            <p class="form-help">
                                Возможные причины:
                                <br>• Устройства не обнаружены системой
                                <br>• Все устройства уже имеют индивидуальные прокси
                                <br>• Устройства не синхронизированы с базой данных
                            </p>
                            <div class="help-actions">
                                <router-link to="/device-debug" class="debug-link">
                                    🔧 Перейти к отладке устройств →
                                </router-link>
                            </div>
                        </div>
                    </div>

                    <div class="form-group">
                        <label>Порт (опционально):</label>
                        <input
                            v-model.number="newProxy.port"
                            type="number"
                            min="6001"
                            max="7000"
                            placeholder="Автоматически (6001-7000)"
                        >
                        <p class="form-help">Если не указан, будет выбран автоматически из диапазона 6001-7000</p>
                    </div>

                    <div class="form-group">
                        <label>Логин (опционально):</label>
                        <input
                            v-model="newProxy.username"
                            type="text"
                            placeholder="Будет сгенерирован автоматически"
                        >
                    </div>

                    <div class="form-group">
                        <label>Пароль (опционально):</label>
                        <input
                            v-model="newProxy.password"
                            type="text"
                            placeholder="Будет сгенерирован автоматически"
                        >
                    </div>

                    <div class="modal-actions">
                        <button type="button" @click="closeCreateModal" class="btn-secondary">
                            Отмена
                        </button>
                        <button type="submit" class="btn-primary" :disabled="!newProxy.device_id || loading">
                            {{ loading ? 'Создание...' : 'Создать' }}
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
                        <!-- Проверяем структуру данных и используем правильный путь -->
                        <div v-if="usageExamples.usage_examples">
                            <div class="example-section">
                                <h4>cURL - Проверка IP</h4>
                                <pre><code>{{
                                        usageExamples.usage_examples.curl_check_ip?.example || 'Пример недоступен'
                                    }}</code></pre>
                                <button v-if="usageExamples.usage_examples.curl_check_ip?.example"
                                        @click="copyToClipboard(usageExamples.usage_examples.curl_check_ip.example)"
                                        class="btn-copy">
                                    Копировать
                                </button>
                            </div>

                            <div class="example-section">
                                <h4>cURL с заголовком авторизации</h4>
                                <pre><code>{{
                                        usageExamples.usage_examples.curl_with_auth_header?.example || 'Пример недоступен'
                                    }}</code></pre>
                                <button v-if="usageExamples.usage_examples.curl_with_auth_header?.example"
                                        @click="copyToClipboard(usageExamples.usage_examples.curl_with_auth_header.example)"
                                        class="btn-copy">
                                    Копировать
                                </button>
                            </div>

                            <div class="example-section">
                                <h4>cURL - User-Agent</h4>
                                <pre><code>{{
                                        usageExamples.usage_examples.curl_user_agent?.example || 'Пример недоступен'
                                    }}</code></pre>
                                <button v-if="usageExamples.usage_examples.curl_user_agent?.example"
                                        @click="copyToClipboard(usageExamples.usage_examples.curl_user_agent.example)"
                                        class="btn-copy">
                                    Копировать
                                </button>
                            </div>

                            <div class="example-section">
                                <h4>cURL - Все заголовки</h4>
                                <pre><code>{{
                                        usageExamples.usage_examples.curl_headers?.example || 'Пример недоступен'
                                    }}</code></pre>
                                <button v-if="usageExamples.usage_examples.curl_headers?.example"
                                        @click="copyToClipboard(usageExamples.usage_examples.curl_headers.example)"
                                        class="btn-copy">
                                    Копировать
                                </button>
                            </div>

                            <div class="example-section">
                                <h4>Python requests</h4>
                                <pre><code>{{
                                        usageExamples.usage_examples.python_requests?.example || 'Пример недоступен'
                                    }}</code></pre>
                                <button v-if="usageExamples.usage_examples.python_requests?.example"
                                        @click="copyToClipboard(usageExamples.usage_examples.python_requests.example)"
                                        class="btn-copy">
                                    Копировать
                                </button>
                            </div>

                            <div class="example-section">
                                <h4>JavaScript/Node.js</h4>
                                <pre><code>{{
                                        usageExamples.usage_examples.javascript_node?.example || 'Пример недоступен'
                                    }}</code></pre>
                                <button v-if="usageExamples.usage_examples.javascript_node?.example"
                                        @click="copyToClipboard(usageExamples.usage_examples.javascript_node.example)"
                                        class="btn-copy">
                                    Копировать
                                </button>
                            </div>

                            <div class="example-section">
                                <h4>PHP</h4>
                                <pre><code>{{ usageExamples.usage_examples.php?.example || 'Пример недоступен' }}</code></pre>
                                <button v-if="usageExamples.usage_examples.php?.example"
                                        @click="copyToClipboard(usageExamples.usage_examples.php.example)"
                                        class="btn-copy">
                                    Копировать
                                </button>
                            </div>

                            <div class="example-section">
                                <h4>wget</h4>
                                <pre><code>{{
                                        usageExamples.usage_examples.wget?.example || 'Пример недоступен'
                                    }}</code></pre>
                                <button v-if="usageExamples.usage_examples.wget?.example"
                                        @click="copyToClipboard(usageExamples.usage_examples.wget.example)"
                                        class="btn-copy">
                                    Копировать
                                </button>
                            </div>

                            <div class="example-section">
                                <h4>Настройки браузера</h4>
                                <div class="browser-config">
                                    <div><strong>Тип:</strong>
                                        {{ usageExamples.usage_examples.browser_config?.example?.type || 'HTTP' }}
                                    </div>
                                    <div><strong>Хост:</strong> {{ usageExamples.proxy_info?.host || 'N/A' }}</div>
                                    <div><strong>Порт:</strong> {{ usageExamples.proxy_info?.port || 'N/A' }}</div>
                                    <div><strong>Логин:</strong> {{ usageExamples.proxy_info?.username || 'N/A' }}</div>
                                    <div><strong>Пароль:</strong> {{ usageExamples.proxy_info?.password || 'N/A' }}
                                    </div>
                                    <div><strong>Примечание:</strong> {{
                                            usageExamples.usage_examples.browser_config?.example?.note || 'Включите аутентификацию прокси в настройках браузера'
                                        }}
                                    </div>
                                </div>
                            </div>

                            <!-- Команды для тестирования -->
                            <div v-if="usageExamples.usage_examples.testing_commands?.examples" class="example-section">
                                <h4>Команды тестирования</h4>
                                <div v-for="test in usageExamples.usage_examples.testing_commands.examples"
                                     :key="test.name" class="test-command">
                                    <h5>{{ test.name }}</h5>
                                    <pre><code>{{ test.command }}</code></pre>
                                    <button @click="copyToClipboard(test.command)" class="btn-copy">
                                        Копировать
                                    </button>
                                </div>
                            </div>
                        </div>

                        <!-- Если данные не пришли в ожидаемом формате -->
                        <div v-else class="error-state">
                            <p>Ошибка загрузки примеров использования</p>
                            <p>Полученные данные:</p>
                            <pre><code>{{ JSON.stringify(usageExamples, null, 2) }}</code></pre>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Модальное окно редактирования прокси -->
        <div v-if="showEditModal" class="modal-overlay" @click="closeEditModal">
            <div class="modal" @click.stop>
                <div class="modal-header">
                    <h3>Редактировать прокси</h3>
                    <button @click="closeEditModal" class="modal-close">×</button>
                </div>

                <form @submit.prevent="updateProxy" class="modal-body">
                    <div class="form-group">
                        <label>Устройство:</label>
                        <input :value="editingProxy?.device_name || editingProxy?.device_id" disabled>
                    </div>

                    <div class="form-group">
                        <label>Порт:</label>
                        <input
                            v-model.number="editProxyData.port"
                            type="number"
                            min="6000"
                            max="7000"
                            required
                        >
                        <p class="form-help">Порт должен быть в диапазоне 6000-7000 и уникальным</p>
                    </div>

                    <div class="form-group">
                        <label>Логин:</label>
                        <input
                            v-model="editProxyData.username"
                            type="text"
                            required
                        >
                    </div>

                    <div class="form-group">
                        <label>Пароль:</label>
                        <input
                            v-model="editProxyData.password"
                            type="text"
                            required
                        >
                    </div>

                    <div class="modal-actions">
                        <button type="button" @click="closeEditModal" class="btn-secondary">
                            Отмена
                        </button>
                        <button type="submit" class="btn-primary" :disabled="loading">
                            {{ loading ? 'Сохранение...' : 'Сохранить' }}
                        </button>
                    </div>
                </form>
            </div>
        </div>

        <!-- Уведомления об ошибках -->
        <div v-if="errorMessage" class="error-notification">
            <div class="error-content">
                <strong>Ошибка:</strong> {{ errorMessage }}
                <button @click="errorMessage = ''" class="error-close">×</button>
            </div>
        </div>

        <!-- Уведомления об успехе -->
        <div v-if="successMessage" class="success-notification">
            <div class="success-content">
                <strong>Успешно:</strong> {{ successMessage }}
                <button @click="successMessage = ''" class="success-close">×</button>
            </div>
        </div>
    </div>
</template>

<script>
import {ref, onMounted, reactive} from 'vue'
import {useProxyStore} from '../stores/proxy'
import {useDeviceStore} from '../stores/devices'
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
        const errorMessage = ref('')
        const successMessage = ref('')

        const newProxy = reactive({
            device_id: '',
            port: null,
            username: '',
            password: ''
        })

        const showEditModal = ref(false)
        const editingProxy = ref(null)
        const editProxyData = reactive({
            port: null,
            username: '',
            password: ''
        })

        // Редактирование прокси
        const editProxy = (proxy) => {
            editingProxy.value = proxy
            Object.assign(editProxyData, {
                port: proxy.port,
                username: proxy.username,
                password: proxy.password
            })
            showEditModal.value = true
        }

        const updateProxy = async () => {
            if (loading.value || !editingProxy.value) return

            try {
                loading.value = true
                console.log('🎯 Updating dedicated proxy:', editingProxy.value.device_id, editProxyData)

                const result = await proxyStore.updateDedicatedProxy(editingProxy.value.device_id, editProxyData)
                console.log('✅ Proxy updated successfully:', result)

                await loadProxies()
                closeEditModal()

                showSuccess(`Прокси успешно обновлен! Новый порт: ${result.port}`)

            } catch (error) {
                console.error('❌ Error updating proxy:', error)

                let errorMsg = 'Неизвестная ошибка'
                if (error.response) {
                    if (error.response.status === 409) {
                        errorMsg = 'Указанный порт уже используется'
                    } else if (error.response.status === 404) {
                        errorMsg = 'Прокси не найден'
                    } else {
                        errorMsg = error.response.data?.detail || `HTTP ${error.response.status}`
                    }
                } else {
                    errorMsg = error.message || 'Ошибка сети'
                }

                showError(errorMsg)
            } finally {
                loading.value = false
            }
        }

        const closeEditModal = () => {
            showEditModal.value = false
            editingProxy.value = null
            Object.assign(editProxyData, {
                port: null,
                username: '',
                password: ''
            })
        }

        // Загрузка данных
        const loadProxies = async () => {
            try {
                const response = await proxyStore.getDedicatedProxies()
                proxies.value = response.proxies
            } catch (error) {
                console.error('Error loading proxies:', error)
                showError('Не удалось загрузить список прокси')
            }
        }

        const loadAvailableDevices = async () => {
            try {
                console.log('🔍 Loading available devices...')

                // Используем fetchModems вместо getDevices
                const devices = await deviceStore.fetchModems()
                console.log('✅ Loaded devices:', devices)

                // Убеждаемся что получили массив
                const devicesArray = Array.isArray(devices) ? devices : []
                console.log('📦 Devices array:', devicesArray)

                // Фильтрация устройств без прокси
                const proxyDeviceIds = new Set(proxies.value.map(p => p.device_id))
                console.log('📋 Existing proxy device IDs:', proxyDeviceIds)

                // Используем modem_id или id для сравнения
                availableDevices.value = devicesArray.filter(d => {
                    const deviceId = d.modem_id || d.id
                    const hasProxy = proxyDeviceIds.has(deviceId)
                    console.log(`📱 Device ${deviceId}: hasProxy = ${hasProxy}`)
                    return !hasProxy
                })

                console.log('✅ Available devices after filter:', availableDevices.value)
                console.log('📊 Total available devices count:', availableDevices.value.length)

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
                    showError('Не удалось загрузить список устройств')
                }
            }
        }

        // Создание прокси
        const createProxy = async () => {
            if (loading.value) return

            try {
                loading.value = true
                console.log('🎯 Creating dedicated proxy with data:', newProxy)

                const proxyData = {
                    device_id: newProxy.device_id,
                    ...(newProxy.port && {port: newProxy.port}),
                    ...(newProxy.username && {username: newProxy.username}),
                    ...(newProxy.password && {password: newProxy.password})
                }

                console.log('📡 Sending request to API:', proxyData)

                const result = await proxyStore.createDedicatedProxy(proxyData)
                console.log('✅ Proxy created successfully:', result)

                await loadProxies()
                await loadAvailableDevices()
                closeCreateModal()

                // Показываем успешное уведомление
                showSuccess(`Прокси успешно создан! Порт: ${result.port}, Логин: ${result.username}`)

            } catch (error) {
                console.error('❌ Error creating proxy:', error)

                // Детальная диагностика ошибки
                let errorMsg = 'Неизвестная ошибка'

                if (error.response) {
                    console.error('📊 Response status:', error.response.status)
                    console.error('📊 Response data:', error.response.data)

                    if (error.response.status === 500) {
                        errorMsg = `Ошибка сервера: ${error.response.data?.detail || 'Внутренняя ошибка сервера'}`
                    } else if (error.response.status === 409) {
                        errorMsg = 'У этого устройства уже есть индивидуальный прокси'
                    } else if (error.response.status === 404) {
                        errorMsg = 'Устройство не найдено'
                    } else {
                        errorMsg = error.response.data?.detail || `HTTP ${error.response.status}`
                    }
                } else if (error.request) {
                    errorMsg = 'Ошибка сети - сервер не отвечает'
                } else {
                    errorMsg = error.message || 'Неизвестная ошибка'
                }

                showError(errorMsg)

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
            } finally {
                loading.value = false
            }
        }

        // Удаление прокси
        const removeProxy = async (deviceId) => {
            if (!confirm('Удалить индивидуальный прокси для этого устройства?')) {
                return
            }

            try {
                loading.value = true
                await proxyStore.removeDedicatedProxy(deviceId)
                await loadProxies()
                await loadAvailableDevices()
                showSuccess('Прокси успешно удален')
            } catch (error) {
                console.error('Error removing proxy:', error)
                showError('Ошибка удаления прокси: ' + (error.response?.data?.detail || error.message))
            } finally {
                loading.value = false
            }
        }

        // Смена учетных данных
        const regenerateCredentials = async (deviceId) => {
            if (!confirm('Сгенерировать новые учетные данные? Старые перестанут работать.')) {
                return
            }

            try {
                loading.value = true
                const result = await proxyStore.regenerateProxyCredentials(deviceId)
                await loadProxies()
                showSuccess(`Учетные данные обновлены! Новый логин: ${result.new_username}`)
            } catch (error) {
                console.error('Error regenerating credentials:', error)
                showError('Ошибка смены учетных данных: ' + (error.response?.data?.detail || error.message))
            } finally {
                loading.value = false
            }
        }

        // Показ примеров использования
        const showUsageExamples = async (proxy) => {
            try {
                loading.value = true
                const examples = await proxyStore.getUsageExamples(proxy.device_id)
                usageExamples.value = examples
                showUsageModal.value = true
            } catch (error) {
                console.error('Error loading usage examples:', error)
                showError('Ошибка загрузки примеров использования')
            } finally {
                loading.value = false
            }
        }

        // Утилиты
        const copyToClipboard = async (text) => {
            try {
                await navigator.clipboard.writeText(text)
                showSuccess('Скопировано в буфер обмена!')
            } catch (error) {
                console.error('Error copying to clipboard:', error)
                showError('Не удалось скопировать в буфер обмена')
            }
        }

        const togglePassword = (deviceId) => {
            showPasswords[deviceId] = !showPasswords[deviceId]
        }

        const getDeviceStatusClass = (status) => {
            switch (status) {
                case 'online':
                    return 'badge-success'
                case 'offline':
                    return 'badge-error'
                case 'busy':
                    return 'badge-warning'
                default:
                    return 'badge-gray'
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

        const closeUsageModal = () => {
            showUsageModal.value = false
            usageExamples.value = null
        }

        // Показ уведомлений
        const showError = (message) => {
            errorMessage.value = message
            setTimeout(() => {
                errorMessage.value = ''
            }, 10000) // Скрыть через 10 секунд
        }

        const showSuccess = (message) => {
            successMessage.value = message
            setTimeout(() => {
                successMessage.value = ''
            }, 5000) // Скрыть через 5 секунд
        }

        // Инициализация
        onMounted(async () => {
            loading.value = true
            try {
                await loadProxies()
                await loadAvailableDevices()
            } finally {
                loading.value = false
            }
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
            errorMessage,
            successMessage,
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
            editProxy,
            showEditModal,
            editProxyData,
            closeEditModal
        }
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

.badge-success {
    background: #d1fae5;
    color: #065f46;
}

.badge-warning {
    background: #fef3c7;
    color: #92400e;
}

.badge-error {
    background: #fee2e2;
    color: #991b1b;
}

.badge-gray {
    background: #f3f4f6;
    color: #6b7280;
}

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

.btn-primary, .btn-secondary, .btn-warning, .btn-danger {
    padding: 8px 16px;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 500;
    transition: all 0.2s;
}

.btn-primary {
    background: #3b82f6;
    color: white;
}

.btn-secondary {
    background: #6b7280;
    color: white;
}

.btn-warning {
    background: #f59e0b;
    color: white;
}

.btn-danger {
    background: #ef4444;
    color: white;
}

.btn-primary:hover {
    background: #2563eb;
}

.btn-secondary:hover {
    background: #4b5563;
}

.btn-warning:hover {
    background: #d97706;
}

.btn-danger:hover {
    background: #dc2626;
}

.btn-primary:disabled {
    background: #9ca3af;
    cursor: not-allowed;
}

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

.no-devices-help {
    margin-top: 10px;
    padding: 15px;
    background: #fef2f2;
    border: 1px solid #fecaca;
    border-radius: 6px;
}

.help-actions {
    margin-top: 10px;
}

.debug-link {
    color: #3b82f6;
    text-decoration: none;
    font-weight: 500;
    padding: 8px 12px;
    background: #eff6ff;
    border-radius: 4px;
    display: inline-block;
    transition: all 0.2s;
}

.debug-link:hover {
    background: #dbeafe;
    color: #2563eb;
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

.error-notification, .success-notification {
    position: fixed;
    top: 20px;
    right: 20px;
    max-width: 400px;
    z-index: 1100;
    border-radius: 6px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.error-notification {
    background: #fee2e2;
    border: 1px solid #fecaca;
}

.success-notification {
    background: #d1fae5;
    border: 1px solid #a7f3d0;
}

.error-content, .success-content {
    padding: 12px 16px;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
}

.error-content {
    color: #991b1b;
}

.success-content {
    color: #065f46;
}

.error-close, .success-close {
    background: none;
    border: none;
    font-size: 18px;
    cursor: pointer;
    margin-left: 12px;
    flex-shrink: 0;
}

.error-close {
    color: #991b1b;
}

.success-close {
    color: #065f46;
}

.btn-info {
    background: #06b6d4;
    color: white;
}

.btn-info:hover {
    background: #0891b2;
}

.test-command {
  margin-bottom: 16px;
  border-left: 3px solid #3b82f6;
  padding-left: 12px;
}

.test-command h5 {
  margin: 0 0 8px 0;
  font-size: 14px;
  font-weight: 600;
  color: #374151;
}

.error-state {
  padding: 20px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 6px;
  color: #991b1b;
}

.error-state pre {
  background: #fff;
  border: 1px solid #e5e7eb;
  margin-top: 10px;
  max-height: 200px;
  overflow-y: auto;
}

</style>
