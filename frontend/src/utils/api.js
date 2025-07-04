// frontend/src/utils/api.js
import axios from 'axios'
import { useAuthStore } from '@/stores/auth'
import { useToast } from 'vue-toastification'

// Create axios instance
const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Request interceptor
api.interceptors.request.use(
  (config) => {
    const authStore = useAuthStore()

    // Add auth token if available
    if (authStore.token) {
      config.headers.Authorization = `Bearer ${authStore.token}`
    }

    // Add timestamp to prevent caching
    if (config.method === 'get') {
      config.params = {
        ...config.params,
        _t: Date.now()
      }
    }

    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor
api.interceptors.response.use(
  (response) => {
    return response
  },
  (error) => {
    const authStore = useAuthStore()
    const toast = useToast()

    // Handle different error status codes
    if (error.response) {
      const { status, data } = error.response

      switch (status) {
        case 401:
          // Unauthorized - clear auth and redirect to login
          authStore.logout()
          window.location.href = '/login'
          break

        case 403:
          // Forbidden
          toast.error('Access denied. You do not have permission to perform this action.')
          break

        case 404:
          // Not found
          toast.error('Resource not found.')
          break

        case 422:
          // Validation error
          if (data.detail) {
            if (Array.isArray(data.detail)) {
              // FastAPI validation errors
              const errorMessages = data.detail.map(err => err.msg).join(', ')
              toast.error(`Validation error: ${errorMessages}`)
            } else {
              toast.error(`Validation error: ${data.detail}`)
            }
          } else {
            toast.error('Validation error occurred.')
          }
          break

        case 429:
          // Rate limit
          toast.error('Too many requests. Please try again later.')
          break

        case 500:
          // Server error
          toast.error('Server error occurred. Please try again later.')
          break

        case 503:
          // Service unavailable
          toast.error('Service temporarily unavailable. Please try again later.')
          break

        default:
          // Generic error
          const message = data.detail || data.message || 'An unexpected error occurred'
          toast.error(message)
      }
    } else if (error.request) {
      // Network error
      toast.error('Network error. Please check your connection and try again.')
    } else {
      // Other error
      toast.error('An unexpected error occurred.')
    }

    return Promise.reject(error)
  }
)

export default api
