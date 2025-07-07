<!-- frontend/src/components/EnhancedRotationModal.vue -->
<template>
  <div v-if="isVisible" class="modal-overlay" @click="closeModal">
    <div class="modal-content" @click.stop>
      <div class="modal-header">
        <h3>Ротация IP устройства</h3>
        <button @click="closeModal" class="modal-close">×</button>
      </div>

      <div class="modal-body">
        <!-- Информация об устройстве -->
        <div class="device-info">
          <h4>{{ deviceInfo.name || deviceInfo.device_id }}</h4>
          <div class="device-details">
            <span class="device-type">{{ formatDeviceType(deviceInfo.device_type) }}</span>
            <span :class="['status', getStatusClass(deviceInfo.status)]">
              {{ deviceInfo.status }}
            </span>
          </div>
          <div class="current-ip">
            <strong>Текущий IP:</strong>
            <code>{{ deviceInfo.current_external_ip || 'Неизвестен' }}</code>
          </div>
        </div>

        <!-- Выбор метода ротации -->
        <div class="rotation-method-section">
          <h4>Метод ротации</h4>

          <div v-if="loadingMethods" class="loading">
            Загрузка методов ротации...
          </div>

          <div v-else-if="availableMethods.length > 0" class="methods-list">
            <div
              v-for="method in availableMethods"
              :key="method.method"
              :class="['method-option', {
                'selected': selectedMethod === method.method,
                'recommended': method.recommended
              }]"
              @click="selectedMethod = method.method"
            >
              <div class="method-header">
                <input
                  type="radio"
                  :value="method.method"
                  v-model="selectedMethod"
                  :id="`method-${method.method}`"
                />
                <label :for="`method-${method.method}`" class="method-name">
                  {{ method.name }}
                  <span v-if="method.recommended" class="recommended-badge">Рекомендуется</span>
                </label>
              </div>
              <div class="method-description">{{ method.description }}</div>
              <div :class="['risk-level', `risk-${method.risk_level}`]">
                Риск: {{ formatRiskLevel(method.risk_level) }}
              </div>
            </div>
          </div>

          <div v-else class="no-methods">
            Методы ротации недоступны для этого типа устройства
          </div>
        </div>

        <!-- Результат последней ротации -->
        <div v-if="lastRotationResult" class="rotation-result">
          <h4>Результат последней ротации</h4>
          <div :class="['result-status', lastRotationResult.success ? 'success' : 'error']">
            <strong>Статус:</strong>
            {{ lastRotationResult.success ? 'Успешно' : 'Ошибка' }}
          </div>
          <div class="result-details">
            <div><strong>Время выполнения:</strong> {{ lastRotationResult.execution_time_seconds }}с</div>
            <div v-if="lastRotationResult.current_ip_before">
              <strong>IP до ротации:</strong> {{ lastRotationResult.current_ip_before }}
            </div>
            <div v-if="lastRotationResult.new_ip_after">
              <strong>IP после ротации:</strong> {{ lastRotationResult.new_ip_after }}
            </div>
            <div v-if="lastRotationResult.ip_changed !== undefined">
              <strong>IP изменился:</strong>
              <span :class="lastRotationResult.ip_changed ? 'success' : 'warning'">
                {{ lastRotationResult.ip_changed ? 'Да' : 'Нет' }}
              </span>
            </div>
            <div class="result-message">{{ lastRotationResult.result_message }}</div>
          </div>
        </div>
      </div>

      <div class="modal-footer">
        <button @click="testRotation" :disabled="isRotating || !selectedMethod" class="btn-test">
          <span v-if="isTesting">🧪 Тестирование...</span>
          <span v-else>🧪 Тестировать</span>
        </button>

        <button @click="performRotation" :disabled="isRotating || !selectedMethod" class="btn-rotate">
          <span v-if="isRotating">🔄 Ротация...</span>
          <span v-else>🔄 Выполнить ротацию</span>
        </button>

        <button @click="closeModal" class="btn-cancel">Отмена</button>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, reactive, watch, onMounted } from 'vue'
import api from '@/utils/api'

export default {
  name: 'EnhancedRotationModal',
  props: {
    deviceInfo: {
      type: Object,
      required: true
    },
    isVisible: {
      type: Boolean,
      default: false
    }
  },
  emits: ['close', 'rotation-completed'],
  setup(props, { emit }) {
    const availableMethods = ref([])
    const selectedMethod = ref('')
    const loadingMethods = ref(false)
    const isRotating = ref(false)
    const isTesting = ref(false)
    const lastRotationResult = ref(null)

    // Загрузка доступных методов ротации
    const loadRotationMethods = async () => {
      if (!props.deviceInfo?.device_id) return

      try {
        loadingMethods.value = true
        const response = await api.get(`/admin/devices/${props.deviceInfo.device_id}/rotation-methods`)

        availableMethods.value = response.data.available_methods || []

        // Выбираем рекомендуемый метод по умолчанию
        const recommended = availableMethods.value.find(m => m.recommended)
        if (recommended) {
          selectedMethod.value = recommended.method
        } else if (availableMethods.value.length > 0) {
          selectedMethod.value = availableMethods.value[0].method
        }

      } catch (error) {
        console.error('Failed to load rotation methods:', error)
      } finally {
        loadingMethods.value = false
      }
    }

    // Тестирование ротации
    const testRotation = async () => {
      if (!selectedMethod.value) return

      try {
        isTesting.value = true
        lastRotationResult.value = null

        const response = await api.post(`/admin/devices/${props.deviceInfo.device_id}/test-rotation`, {
          method: selectedMethod.value
        })

        lastRotationResult.value = response.data

        // Показываем уведомление
        if (response.data.success && response.data.ip_changed) {
          showNotification('Тест ротации успешен! IP изменился.', 'success')
        } else if (response.data.success && !response.data.ip_changed) {
          showNotification('Ротация выполнена, но IP не изменился. Попробуйте другой метод.', 'warning')
        } else {
          showNotification('Тест ротации завершился с ошибкой.', 'error')
        }

      } catch (error) {
        console.error('Test rotation failed:', error)
        showNotification('Ошибка при тестировании ротации', 'error')
      } finally {
        isTesting.value = false
      }
    }

    // Выполнение ротации
    const performRotation = async () => {
      if (!selectedMethod.value) return

      try {
        isRotating.value = true

        const response = await api.post(`/admin/devices/${props.deviceInfo.device_id}/rotate`, {
          force_method: selectedMethod.value
        })

        if (response.data.success) {
          showNotification(`Ротация завершена успешно! Новый IP: ${response.data.new_ip || 'получается...'}`, 'success')

          // Обновляем информацию об устройстве
          emit('rotation-completed', {
            device_id: props.deviceInfo.device_id,
            new_ip: response.data.new_ip,
            method: selectedMethod.value
          })

          // Закрываем модальное окно через небольшую задержку
          setTimeout(() => {
            closeModal()
          }, 2000)
        } else {
          showNotification(`Ротация завершилась с ошибкой: ${response.data.message}`, 'error')
        }

      } catch (error) {
        console.error('Rotation failed:', error)
        const errorMessage = error.response?.data?.detail || 'Неизвестная ошибка'
        showNotification(`Ошибка ротации: ${errorMessage}`, 'error')
      } finally {
        isRotating.value = false
      }
    }

    const closeModal = () => {
      emit('close')
      // Сброс состояния
      lastRotationResult.value = null
      selectedMethod.value = ''
    }

    const formatDeviceType = (type) => {
      const types = {
        'android': 'Android устройство',
        'usb_modem': 'USB модем',
        'raspberry_pi': 'Raspberry Pi',
        'network_device': 'Сетевое устройство'
      }
      return types[type] || type
    }

    const formatRiskLevel = (level) => {
      const levels = {
        'low': 'Низкий',
        'medium': 'Средний',
        'high': 'Высокий'
      }
      return levels[level] || level
    }

    const getStatusClass = (status) => {
      return {
        'online': 'status-online',
        'offline': 'status-offline',
        'busy': 'status-busy'
      }[status] || 'status-unknown'
    }

    const showNotification = (message, type) => {
      // Здесь можно использовать toast-уведомления
      console.log(`${type.toUpperCase()}: ${message}`)
    }

    // Загружаем методы при открытии модального окна
    watch(() => props.isVisible, (newValue) => {
      if (newValue) {
        loadRotationMethods()
      }
    })

    return {
      availableMethods,
      selectedMethod,
      loadingMethods,
      isRotating,
      isTesting,
      lastRotationResult,
      testRotation,
      performRotation,
      closeModal,
      formatDeviceType,
      formatRiskLevel,
      getStatusClass
    }
  }
}
</script>

<style scoped>
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

.modal-content {
  background: white;
  border-radius: 8px;
  max-width: 600px;
  width: 90%;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid #e5e7eb;
}

.modal-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.modal-close {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #6b7280;
}

.modal-body {
  padding: 20px;
}

.device-info {
  background: #f9fafb;
  padding: 16px;
  border-radius: 6px;
  margin-bottom: 20px;
}

.device-info h4 {
  margin: 0 0 8px 0;
  font-size: 16px;
  font-weight: 600;
}

.device-details {
  display: flex;
  gap: 12px;
  margin-bottom: 8px;
}

.device-type {
  background: #e5e7eb;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.status {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.status-online { background: #d1fae5; color: #065f46; }
.status-offline { background: #fee2e2; color: #991b1b; }
.status-busy { background: #fef3c7; color: #92400e; }

.current-ip code {
  background: #f3f4f6;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: monospace;
}

.rotation-method-section h4 {
  margin: 0 0 16px 0;
  font-size: 16px;
  font-weight: 600;
}

.methods-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.method-option {
  border: 2px solid #e5e7eb;
  border-radius: 6px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s;
}

.method-option:hover {
  border-color: #3b82f6;
}

.method-option.selected {
  border-color: #3b82f6;
  background: #eff6ff;
}

.method-option.recommended {
  border-color: #10b981;
}

.method-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.method-name {
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
}

.recommended-badge {
  background: #10b981;
  color: white;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
}

.method-description {
  color: #6b7280;
  font-size: 14px;
  margin-bottom: 8px;
}

.risk-level {
  font-size: 12px;
  font-weight: 500;
}

.risk-low { color: #10b981; }
.risk-medium { color: #f59e0b; }
.risk-high { color: #ef4444; }

.rotation-result {
  background: #f9fafb;
  padding: 16px;
  border-radius: 6px;
  margin-top: 20px;
}

.rotation-result h4 {
  margin: 0 0 12px 0;
  font-size: 16px;
  font-weight: 600;
}

.result-status {
  margin-bottom: 12px;
  font-weight: 500;
}

.result-status.success { color: #10b981; }
.result-status.error { color: #ef4444; }

.result-details {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 14px;
}

.success { color: #10b981; }
.warning { color: #f59e0b; }

.result-message {
  margin-top: 8px;
  padding: 8px;
  background: #f3f4f6;
  border-radius: 4px;
  font-style: italic;
  color: #6b7280;
}

.modal-footer {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  padding: 20px;
  border-top: 1px solid #e5e7eb;
}

.btn-test, .btn-rotate, .btn-cancel {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s;
}

.btn-test {
  background: #f59e0b;
  color: white;
}

.btn-test:hover:not(:disabled) {
  background: #d97706;
}

.btn-rotate {
  background: #3b82f6;
  color: white;
}

.btn-rotate:hover:not(:disabled) {
  background: #2563eb;
}

.btn-cancel {
  background: #6b7280;
  color: white;
}

.btn-cancel:hover {
  background: #4b5563;
}

button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.loading, .no-methods {
  text-align: center;
  padding: 20px;
  color: #6b7280;
  font-style: italic;
}
</style>
