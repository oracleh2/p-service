// frontend/src/utils/api.js - ОБНОВЛЕННАЯ ВЕРСИЯ С ТАЙМАУТОМ

import axios from 'axios'

// Создаем основной экземпляр API
const api = axios.create({
  baseURL: process.env.VUE_APP_API_URL || 'http://192.168.1.50:8000',
  timeout: 30000, // Стандартный таймаут 30 секунд
  headers: {
    'Content-Type': 'application/json',
  },
})

// Создаем экземпляр API с увеличенным таймаутом для ротации
const apiLongTimeout = axios.create({
  baseURL: process.env.VUE_APP_API_URL || 'http://192.168.1.50:8000',
  timeout: 70000, // Увеличенный таймаут 70 секунд для ротации USB модемов
  headers: {
    'Content-Type': 'application/json',
  },
})

// Интерсептор для добавления токена авторизации
const addAuthToken = (config) => {
  const token = localStorage.getItem('authToken')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
}

// Интерсептор для обработки ошибок
const handleResponseError = (error) => {
  if (error.response?.status === 401) {
    localStorage.removeItem('authToken')
    window.location.href = '/login'
  }
  return Promise.reject(error)
}

// Применяем интерсепторы к обоим экземплярам
[api, apiLongTimeout].forEach(instance => {
  instance.interceptors.request.use(addAuthToken)
  instance.interceptors.response.use(
    response => response,
    handleResponseError
  )
})

// Функция для создания API клиента с кастомным таймаутом
export const createApiClient = (timeoutMs = 30000) => {
  const customApi = axios.create({
    baseURL: process.env.VUE_APP_API_URL || 'http://192.168.1.50:8000',
    timeout: timeoutMs,
    headers: {
      'Content-Type': 'application/json',
    },
  })

  customApi.interceptors.request.use(addAuthToken)
  customApi.interceptors.response.use(
    response => response,
    handleResponseError
  )

  return customApi
}

// Специализированные функции для ротации с автоматическим выбором таймаута
const rotationApi = {
  // Тестирование ротации (может занять до 60 секунд)
  testRotation: (deviceId, method) => {
    return apiLongTimeout.post(`/admin/devices/${deviceId}/test-rotation`, { method })
  },

  // Выполнение ротации (может занять до 70 секунд для USB модемов)
  executeRotation: (deviceId, forceMethod = null) => {
    const data = forceMethod ? { force_method: forceMethod } : {}
    return apiLongTimeout.post(`/admin/devices/${deviceId}/rotate`, data)
  },

  // USB перезагрузка (гарантированно занимает 30-45 секунд)
  usbReboot: (deviceId) => {
    return apiLongTimeout.post(`/admin/devices/${deviceId}/usb-reboot`)
  },

  // Получение методов ротации (быстрый запрос)
  getRotationMethods: (deviceId) => {
    return api.get(`/admin/devices/${deviceId}/rotation-methods`)
  },

  // Ротация всех устройств (может занять очень много времени)
  rotateAllDevices: () => {
    const extendedTimeout = createApiClient(180000) // 3 минуты
    return extendedTimeout.post('/admin/devices/rotate-all')
  }
}

// Специализированные функции для диагностики с увеличенным таймаутом
const diagnosticsApi = {
  // Диагностика USB устройства
  getUsbDiagnostics: (deviceId) => {
    return apiLongTimeout.get(`/admin/devices/${deviceId}/usb-diagnostics`)
  },

  // Проверка здоровья устройства
  getDeviceHealth: (deviceId) => {
    return apiLongTimeout.get(`/admin/devices/${deviceId}/health`)
  },

  // Диагностика проблем устройства
  diagnoseDevice: (deviceId) => {
    return apiLongTimeout.post(`/admin/devices/${deviceId}/diagnose`)
  },

  // Тестирование соединения устройства
  testConnection: (deviceId) => {
    return apiLongTimeout.get(`/admin/devices/${deviceId}/connection-test`)
  }
}

// Добавляем специальные методы к основному API объекту
api.rotation = rotationApi
api.diagnostics = diagnosticsApi
api.createClient = createApiClient
api.longTimeout = apiLongTimeout

// Логирование запросов в режиме разработки
if (process.env.NODE_ENV === 'development') {
  [api, apiLongTimeout].forEach(instance => {
    instance.interceptors.request.use(request => {
      console.log('🚀 API Request:', {
        method: request.method?.toUpperCase(),
        url: request.url,
        timeout: request.timeout,
        data: request.data
      })
      return request
    })

    instance.interceptors.response.use(
      response => {
        console.log('✅ API Response:', {
          status: response.status,
          url: response.config.url,
          duration: response.config.metadata?.endTime - response.config.metadata?.startTime
        })
        return response
      },
      error => {
        console.error('❌ API Error:', {
          status: error.response?.status,
          url: error.config?.url,
          message: error.message,
          timeout: error.code === 'ECONNABORTED'
        })
        return Promise.reject(error)
      }
    )
  })
}

export default api

// Дополнительные утилиты для работы с таймаутами
export const timeoutUtils = {
  // Рекомендуемые таймауты для разных операций
  timeouts: {
    fast: 5000,          // 5 секунд - быстрые запросы
    standard: 30000,     // 30 секунд - стандартные запросы
    rotation: 70000,     // 70 секунд - ротация IP
    bulk: 180000,        // 3 минуты - массовые операции
    discovery: 120000    // 2 минуты - обнаружение устройств
  },

  // Получение рекомендуемого таймаута для операции
  getRecommendedTimeout: (operation, deviceType = null) => {
    const { timeouts } = timeoutUtils

    switch (operation) {
      case 'rotation':
        return deviceType === 'usb_modem' ? timeouts.rotation : timeouts.standard
      case 'test_rotation':
        return timeouts.rotation
      case 'discovery':
        return timeouts.discovery
      case 'bulk_rotation':
        return timeouts.bulk
      case 'diagnostics':
        return timeouts.rotation
      default:
        return timeouts.standard
    }
  },

  // Создание API клиента с рекомендуемым таймаутом
  createClientForOperation: (operation, deviceType = null) => {
    const timeout = timeoutUtils.getRecommendedTimeout(operation, deviceType)
    return createApiClient(timeout)
  }
}

// Экспорт для использования в компонентах
export { api as apiClient, apiLongTimeout, rotationApi, diagnosticsApi }
