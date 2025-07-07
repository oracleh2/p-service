<!-- frontend/src/components/RotationMethodModal.vue -->
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
                </label>
                <p class="text-xs text-gray-500 mt-1">{{ method.description }}</p>
                <div class="flex items-center mt-2">
                  <span class="text-xs text-gray-400">Risk level:</span>
                  <span :class="getRiskLevelClass(method.risk_level)"
                        class="ml-1 text-xs font-medium">
                    {{ formatRiskLevel(method.risk_level) }}
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
            <button @click="closeModal" class="btn btn-sm btn-secondary">
              Cancel
            </button>
            <button @click="executeRotation"
                    :disabled="!selectedMethod || isProcessing"
                    class="btn btn-sm btn-primary">
              <ArrowPathIcon class="h-4 w-4 mr-1" :class="{ 'animate-spin': isRotating }" />
              {{ isRotating ? 'Rotating...' : 'Rotate IP' }}
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
import { ref, computed, watch, onMounted } from 'vue'
import {
  XMarkIcon,
  ArrowPathIcon,
  BeakerIcon,
  ExclamationTriangleIcon
} from '@heroicons/vue/24/outline'
import api from '@/utils/api'

export default {
  name: 'RotationMethodModal',
  components: {
    XMarkIcon,
    ArrowPathIcon,
    BeakerIcon,
    ExclamationTriangleIcon
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

    const isProcessing = computed(() => isRotating.value || isTesting.value)

    // Load available rotation methods when modal opens
    const loadRotationMethods = async () => {
      if (!props.deviceInfo?.modem_id) return

      try {
        loadingMethods.value = true
        errorMessage.value = ''

        const response = await api.get(`/admin/devices/${props.deviceInfo.modem_id}/rotation-methods`)

        availableMethods.value = response.data.available_methods || []

        // Select recommended method by default
        const recommended = availableMethods.value.find(m => m.recommended)
        if (recommended) {
          selectedMethod.value = recommended.method
        } else if (availableMethods.value.length > 0) {
          selectedMethod.value = availableMethods.value[0].method
        }

      } catch (error) {
        console.error('Failed to load rotation methods:', error)
        errorMessage.value = 'Failed to load rotation methods'
      } finally {
        loadingMethods.value = false
      }
    }

    // Test selected rotation method
    const testMethod = async () => {
      if (!selectedMethod.value) return

      try {
        isTesting.value = true
        testResult.value = null
        errorMessage.value = ''

        const response = await api.post(`/admin/devices/${props.deviceInfo.modem_id}/test-rotation`, {
          method: selectedMethod.value
        })

        testResult.value = response.data

      } catch (error) {
        console.error('Test rotation failed:', error)
        errorMessage.value = 'Test rotation failed: ' + (error.response?.data?.detail || error.message)
      } finally {
        isTesting.value = false
      }
    }

    // Execute IP rotation
    const executeRotation = async () => {
      if (!selectedMethod.value) return

      try {
        isRotating.value = true
        errorMessage.value = ''

        const response = await api.post(`/admin/devices/${props.deviceInfo.modem_id}/rotate`, {
          force_method: selectedMethod.value
        })

        if (response.data.success) {
          emit('rotation-success', {
            device_id: props.deviceInfo.modem_id,
            method: selectedMethod.value,
            new_ip: response.data.new_ip,
            message: response.data.message
          })
          closeModal()
        } else {
          errorMessage.value = response.data.message || 'Rotation failed'
        }

      } catch (error) {
        console.error('Rotation failed:', error)
        errorMessage.value = 'Rotation failed: ' + (error.response?.data?.detail || error.message)
      } finally {
        isRotating.value = false
      }
    }

    const closeModal = () => {
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

    // Load methods when modal becomes visible
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
      isProcessing,
      errorMessage,
      testResult,
      testMethod,
      executeRotation,
      closeModal,
      formatDeviceType,
      formatRiskLevel,
      getRiskLevelClass,
      getStatusBadgeClass
    }
  }
}
</script>
