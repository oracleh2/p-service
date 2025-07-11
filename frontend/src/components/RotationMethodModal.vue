// frontend/src/components/RotationMethodModal.vue - ИСПРАВЛЕННАЯ ВЕРСИЯ С ТАЙМАУТОМ

<template>
  <div v-if="isVisible" class="fixed inset-0 bg-gray-500 bg-opacity-75 flex items-center justify-center z-50" @click="closeModal">
    <div class="bg-white rounded-lg max-w-md w-full mx-4 shadow-xl" @click.stop>
      <!-- Modal Header -->
      <div class="px-6 py-4 border-b border-gray-200">
        <div class="flex items-center justify-between">
          <h3 class="text-lg font-medium text-gray-900">
            Rotate IP - {{ deviceInfo.modem_id }}
          </h3>
          <button @click="closeModal" class="text-gray-400 hover:text-gray-600">
            <XMarkIcon class="h-6 w-6" />
          </button>
        </div>
        <p class="text-sm text-gray-500 mt-1">
          {{ formatDeviceType(deviceInfo.modem_type) }} • {{ deviceInfo.interface }}
        </p>
        <!-- USB Modem Warning -->
        <div v-if="deviceInfo.modem_type === 'usb_modem'" class="mt-2 p-2 bg-amber-50 border border-amber-200 rounded-md">
          <div class="flex">
            <ClockIcon class="h-4 w-4 text-amber-400 mt-0.5" />
            <div class="ml-2">
              <p class="text-xs text-amber-800">
                USB модемы требуют 30-45 секунд для ротации IP
              </p>
            </div>
          </div>
        </div>
      </div>

      <!-- Device Status -->
      <div class="px-6 py-3 bg-gray-50">
        <div class="flex items-center justify-between text-sm">
          <span class="text-gray-600">Current Status:</span>
          <span :class="getStatusBadgeClass(deviceInfo.status)"
                class="px-2 py-1 rounded-full text-xs font-medium">
            {{ deviceInfo.status }}
          </span>
        </div>
        <div class="flex items-center justify-between text-sm mt-2">
          <span class="text-gray-600">Current IP:</span>
          <span class="font-mono text-gray-900">{{ deviceInfo.external_ip || 'N/A' }}</span>
        </div>
      </div>

      <!-- Progress Indicator for Rotation -->
      <div v-if="isRotating" class="px-6 py-4 bg-blue-50 border-t border-blue-200">
        <div class="flex items-center">
          <div class="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-600"></div>
          <div class="ml-3 flex-1">
            <p class="text-sm font-medium text-blue-900">
              {{ rotationProgress.message }}
            </p>
            <div class="mt-1 bg-blue-200 rounded-full h-1.5">
              <div
                class="bg-blue-600 h-1.5 rounded-full transition-all duration-1000"
                :style="{ width: `${rotationProgress.percent}%` }"
              ></div>
            </div>
            <p class="text-xs text-blue-700 mt-1">
              Прошло: {{ Math.floor(rotationProgress.elapsed / 1000) }}с
              <span v-if="deviceInfo.modem_type === 'usb_modem'">
                / ~40с
              </span>
            </p>
          </div>
        </div>
      </div>

      <!-- Loading State -->
      <div v-if="loadingMethods" class="px-6 py-8">
        <div class="flex items-center justify-center">
          <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <span class="ml-3 text-gray-600">Loading rotation methods...</span>
        </div>
      </div>

      <!-- Rotation Methods -->
      <div v-else-if="availableMethods.length > 0" class="px-6 py-4">
        <h4 class="text-sm font-medium text-gray-900 mb-3">Choose rotation method:</h4>

        <div class="space-y-3">
          <div
            v-for="method in availableMethods"
            :key="method.method"
            :class="[
              'border rounded-lg p-3 cursor-pointer transition-all duration-200',
              selectedMethod === method.method
                ? 'border-blue-500 bg-blue-50 ring-2 ring-blue-200'
                : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
            ]"
            @click="selectedMethod = method.method"
          >
            <div class="flex items-start">
              <input
                type="radio"
                :value="method.method"
                v-model="selectedMethod"
                :id="`method-${method.method}`"
                class="mt-0.5 h-4 w-4 text-blue-600 border-gray-300 focus:ring-blue-500"
              />
              <div class="ml-3 flex-1">
                <label
                  :for="`method-${method.method}`"
                  class="text-sm font-medium text-gray-900 cursor-pointer flex items-center"
                >
                  {{ method.name }}
                  <span v-if="method.recommended"
                        class="ml-2 px-2 py-0.5 bg-green-100 text-green-800 text-xs rounded-full font-medium">
                    Recommended
                  </span>
                  <span v-if="method.method === 'usb_reboot'"
                        class="ml-2 px-2 py-0.5 bg-blue-100 text-blue-800 text-xs rounded-full font-medium">
                    ~40s
                  </span>
                </label>
                <p class="text-xs text-gray-500 mt-1">{{ method.description }}</p>
                <div class="flex items-center mt-2">
                  <span class="text-xs text-gray-400">Risk level:</span>
                  <span :class="getRiskLevelClass(method.risk_level)"
                        class="ml-1 text-xs font-medium">
                    {{ formatRiskLevel(method.risk_level) }}
                  </span>
                  <span v-if="method.time_estimate" class="ml-3 text-xs text-gray-400">
                    Time: {{ method.time_estimate }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- No Methods Available -->
      <div v-else class="px-6 py-8 text-center">
        <ExclamationTriangleIcon class="mx-auto h-12 w-12 text-gray-400" />
        <h3 class="mt-2 text-sm font-medium text-gray-900">No rotation methods available</h3>
        <p class="mt-1 text-sm text-gray-500">
          This device type doesn't support IP rotation or methods couldn't be loaded.
        </p>
      </div>

      <!-- Error State -->
      <div v-if="errorMessage" class="px-6 py-4 bg-red-50 border-t border-red-200">
        <div class="flex">
          <ExclamationTriangleIcon class="h-5 w-5 text-red-400" />
          <div class="ml-3">
            <p class="text-sm text-red-800">{{ errorMessage }}</p>
          </div>
        </div>
      </div>

      <!-- Modal Footer -->
      <div class="px-6 py-4 border-t border-gray-200 bg-gray-50 rounded-b-lg">
        <div class="flex justify-between items-center">
          <button @click="testMethod"
                  :disabled="!selectedMethod || isProcessing"
                  class="btn btn-sm btn-secondary">
            <BeakerIcon class="h-4 w-4 mr-1" />
            {{ isTesting ? 'Testing...' : 'Test Method' }}
          </button>

          <div class="flex space-x-3">
            <button @click="closeModal" :disabled="isRotating" class="btn btn-sm btn-secondary">
              Cancel
            </button>
            <button @click="executeRotation"
                    :disabled="!selectedMethod || isProcessing"
                    class="btn btn-sm btn-primary">
              <ArrowPathIcon class="h-4 w-4 mr-1" :class="{ 'animate-spin': isRotating }" />
              {{ getRotationButtonText() }}
            </button>
          </div>
        </div>
      </div>

      <!-- Test Results -->
      <div v-if="testResult" class="px-6 py-4 border-t border-gray-200">
        <div class="bg-gray-50 rounded-lg p-3">
          <h5 class="text-sm font-medium text-gray-900 mb-2">Test Result:</h5>
          <div class="space-y-2 text-sm">
            <div class="flex justify-between">
              <span class="text-gray-600">Status:</span>
              <span :class="testResult.success ? 'text-green-600' : 'text-red-600'" class="font-medium">
                {{ testResult.success ? 'Success' : 'Failed' }}
              </span>
            </div>
            <div class="flex justify-between">
              <span class="text-gray-600">Execution Time:</span>
              <span class="text-gray-900">{{ testResult.execution_time_seconds }}s</span>
            </div>
            <div v-if="testResult.ip_changed !== undefined" class="flex justify-between">
              <span class="text-gray-600">IP Changed:</span>
              <span :class="testResult.ip_changed ? 'text-green-600' : 'text-yellow-600'" class="font-medium">
                {{ testResult.ip_changed ? 'Yes' : 'No' }}
              </span>
            </div>
            <div v-if="testResult.new_ip_after" class="flex justify-between">
              <span class="text-gray-600">New IP:</span>
              <span class="font-mono text-gray-900">{{ testResult.new_ip_after }}</span>
            </div>
            <div v-if="testResult.result_message" class="mt-2">
              <p class="text-xs text-gray-600">{{ testResult.result_message }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, watch } from 'vue'
import {
  XMarkIcon,
  ArrowPathIcon,
  BeakerIcon,
  ExclamationTriangleIcon,
  ClockIcon
} from '@heroicons/vue/24/outline'
import api from '@/utils/api'

export default {
  name: 'RotationMethodModal',
  components: {
    XMarkIcon,
    ArrowPathIcon,
    BeakerIcon,
    ExclamationTriangleIcon,
    ClockIcon
  },
  props: {
    isVisible: {
      type: Boolean,
      default: false
    },
    deviceInfo: {
      type: Object,
      required: true
    }
  },
  emits: ['close', 'rotation-success'],
  setup(props, { emit }) {
    const availableMethods = ref([])
    const selectedMethod = ref('')
    const loadingMethods = ref(false)
    const isRotating = ref(false)
    const isTesting = ref(false)
    const errorMessage = ref('')
    const testResult = ref(null)

    // Прогресс ротации
    const rotationProgress = ref({
      message: 'Initializing rotation...',
      percent: 0,
      elapsed: 0
    })

    let rotationTimer = null
    let progressTimer = null

    const isProcessing = computed(() => isRotating.value || isTesting.value)

    // Получение правильного device_id
    const getDeviceId = () => {
      return props.deviceInfo?.modem_id ||
             props.deviceInfo?.device_id ||
             props.deviceInfo?.id ||
             ''
    }

    // Текст кнопки ротации
    const getRotationButtonText = () => {
      if (!isRotating.value) return 'Rotate IP'

      if (props.deviceInfo?.modem_type === 'usb_modem') {
        return 'USB Reboot... (~40s)'
      }

      return 'Rotating...'
    }

    // Симуляция прогресса для USB модемов
    const startRotationProgress = () => {
      if (props.deviceInfo?.modem_type !== 'usb_modem') return

      const startTime = Date.now()
      const expectedDuration = 40000 // 40 секунд для USB модемов

      rotationProgress.value = {
        message: 'Starting USB reboot...',
        percent: 0,
        elapsed: 0
      }

      progressTimer = setInterval(() => {
        const elapsed = Date.now() - startTime
        const percent = Math.min((elapsed / expectedDuration) * 100, 95)

        let message = 'Starting USB reboot...'
        if (elapsed > 5000) message = 'Disabling USB device...'
        if (elapsed > 10000) message = 'Enabling USB device...'
        if (elapsed > 20000) message = 'Waiting for reconnection...'
        if (elapsed > 30000) message = 'Verifying IP change...'

        rotationProgress.value = {
          message,
          percent,
          elapsed
        }
      }, 1000)
    }

    const stopRotationProgress = () => {
      if (progressTimer) {
        clearInterval(progressTimer)
        progressTimer = null
      }

      rotationProgress.value = {
        message: 'Completed',
        percent: 100,
        elapsed: rotationProgress.value.elapsed
      }
    }

    // Создание API клиента с увеличенным таймаутом
    const createApiClientWithTimeout = (timeoutMs = 70000) => {
      // Создаем отдельный экземпляр axios с увеличенным таймаутом
      const axios = require('axios')
      return axios.create({
        baseURL: api.defaults.baseURL,
        timeout: timeoutMs,
        headers: api.defaults.headers
      })
    }

    // Загрузка методов ротации
    const loadRotationMethods = async () => {
      const deviceId = getDeviceId()
      if (!deviceId) {
        console.error('No device ID found in deviceInfo:', props.deviceInfo)
        errorMessage.value = 'Device ID не найден'
        return
      }

      try {
        loadingMethods.value = true
        errorMessage.value = ''

        console.log('Loading rotation methods for device:', deviceId)

        const response = await api.get(`/admin/devices/${deviceId}/rotation-methods`)

        availableMethods.value = response.data.available_methods || []

        // Выбираем рекомендуемый метод по умолчанию
        const recommended = availableMethods.value.find(m => m.recommended)
        if (recommended) {
          selectedMethod.value = recommended.method
        } else if (availableMethods.value.length > 0) {
          selectedMethod.value = availableMethods.value[0].method
        }

        console.log('Available methods loaded:', availableMethods.value)

      } catch (error) {
        console.error('Failed to load rotation methods:', error)

        if (error.response?.status === 404) {
          errorMessage.value = 'Устройство не найдено или методы ротации недоступны'
        } else if (error.response?.status === 500) {
          errorMessage.value = 'Ошибка сервера при загрузке методов ротации'
        } else {
          errorMessage.value = 'Не удалось загрузить методы ротации'
        }
      } finally {
        loadingMethods.value = false
      }
    }

    // Тестирование метода ротации
    const testMethod = async () => {
      if (!selectedMethod.value) return

      const deviceId = getDeviceId()
      if (!deviceId) {
        errorMessage.value = 'Device ID не найден'
        return
      }

      try {
        isTesting.value = true
        testResult.value = null
        errorMessage.value = ''

        console.log('Testing rotation method:', selectedMethod.value, 'for device:', deviceId)

        // Используем увеличенный таймаут для тестирования
        const apiClient = createApiClientWithTimeout(70000)
        const response = await apiClient.post(`/admin/devices/${deviceId}/test-rotation`, {
          method: selectedMethod.value
        })

        testResult.value = response.data
        console.log('Test result:', response.data)

      } catch (error) {
        console.error('Test rotation failed:', error)

        if (error.code === 'ECONNABORTED') {
          errorMessage.value = 'Тест занял слишком много времени. Это нормально для USB модемов.'
        } else if (error.response?.status === 404) {
          errorMessage.value = 'Устройство не найдено'
        } else if (error.response?.status === 500) {
          errorMessage.value = 'Ошибка сервера при тестировании ротации'
        } else {
          errorMessage.value = 'Тестирование ротации завершилось с ошибкой: ' + (error.response?.data?.detail || error.message)
        }
      } finally {
        isTesting.value = false
      }
    }

    // Выполнение ротации IP
    const executeRotation = async () => {
      if (!selectedMethod.value) return

      const deviceId = getDeviceId()
      if (!deviceId) {
        errorMessage.value = 'Device ID не найден'
        return
      }

      try {
        isRotating.value = true
        errorMessage.value = ''

        // Запускаем индикатор прогресса для USB модемов
        startRotationProgress()

        console.log('Executing rotation with method:', selectedMethod.value, 'for device:', deviceId)

        const requestBody = selectedMethod.value ?
          { force_method: selectedMethod.value } :
          {}

        // Определяем таймаут в зависимости от типа устройства
        const timeoutMs = props.deviceInfo?.modem_type === 'usb_modem' ? 70000 : 35000

        const apiClient = createApiClientWithTimeout(timeoutMs)
        const response = await apiClient.post(`/admin/devices/${deviceId}/rotate`, requestBody)

        console.log('Rotation response:', response.data)

        stopRotationProgress()

        if (response.data.success) {
          emit('rotation-success', {
            device_id: deviceId,
            method: selectedMethod.value,
            new_ip: response.data.new_ip,
            old_ip: response.data.old_ip,
            message: response.data.message,
            ip_changed: response.data.ip_changed
          })
          closeModal()
        } else {
          errorMessage.value = response.data.message || 'Ротация завершилась с ошибкой'
        }

      } catch (error) {
        console.error('Rotation failed:', error)
        stopRotationProgress()

        if (error.code === 'ECONNABORTED') {
          // Таймаут - это может быть нормально для USB модемов
          if (props.deviceInfo?.modem_type === 'usb_modem') {
            errorMessage.value = 'Ротация заняла более 70 секунд. Проверьте статус устройства через несколько минут.'
          } else {
            errorMessage.value = 'Ротация заняла слишком много времени'
          }
        } else if (error.response?.status === 404) {
          errorMessage.value = 'Устройство не найдено'
        } else if (error.response?.status === 500) {
          errorMessage.value = 'Ошибка сервера при выполнении ротации'
        } else {
          errorMessage.value = 'Ротация завершилась с ошибкой: ' + (error.response?.data?.detail || error.message)
        }
      } finally {
        isRotating.value = false
      }
    }

    const closeModal = () => {
      // Останавливаем таймеры
      if (rotationTimer) {
        clearTimeout(rotationTimer)
        rotationTimer = null
      }

      stopRotationProgress()

      emit('close')
      // Reset state
      selectedMethod.value = ''
      testResult.value = null
      errorMessage.value = ''
    }

    // Utility functions
    const formatDeviceType = (type) => {
      const types = {
        'android': 'Android Device',
        'usb_modem': 'USB Modem',
        'raspberry_pi': 'Raspberry Pi',
        'network_device': 'Network Device'
      }
      return types[type] || type
    }

    const formatRiskLevel = (level) => {
      const levels = {
        'low': 'Low',
        'medium': 'Medium',
        'high': 'High'
      }
      return levels[level] || level
    }

    const getRiskLevelClass = (level) => {
      const classes = {
        'low': 'text-green-600',
        'medium': 'text-yellow-600',
        'high': 'text-red-600'
      }
      return classes[level] || 'text-gray-600'
    }

    const getStatusBadgeClass = (status) => {
      const classes = {
        'online': 'bg-green-100 text-green-800',
        'offline': 'bg-red-100 text-red-800',
        'busy': 'bg-yellow-100 text-yellow-800'
      }
      return classes[status] || 'bg-gray-100 text-gray-800'
    }

    // Загружаем методы при открытии модального окна
    watch(() => props.isVisible, (newValue) => {
      if (newValue) {
        console.log('Modal opened with device info:', props.deviceInfo)
        loadRotationMethods()
      }
    })

    return {
      availableMethods,
      selectedMethod,
      loadingMethods,
      isRotating,
      isTesting,
      isProcessing,
      errorMessage,
      testResult,
      rotationProgress,
      testMethod,
      executeRotation,
      closeModal,
      formatDeviceType,
      formatRiskLevel,
      getRiskLevelClass,
      getStatusBadgeClass,
      getDeviceId,
      getRotationButtonText
    }
  }
}
</script>

<style scoped>
.btn {
  @apply inline-flex items-center px-3 py-2 border text-sm font-medium rounded-md focus:outline-none focus:ring-2 focus:ring-offset-2;
}

.btn-sm {
  @apply px-2.5 py-1.5 text-xs;
}

.btn-primary {
  @apply border-transparent text-white bg-blue-600 hover:bg-blue-700 focus:ring-blue-500;
}

.btn-secondary {
  @apply border-gray-300 text-gray-700 bg-white hover:bg-gray-50 focus:ring-blue-500;
}

.btn:disabled {
  @apply opacity-50 cursor-not-allowed;
}
</style>
